"""Provider-agnostic LLM client (OpenAI-compatible chat API): Ollama locally, Groq in CI.

Copied from spike S5 ``spikes/s5/llm.py``, itself adapted from paleo-atlas
``src/paleo/llm.py`` (same author, AGPL in both; decision D2). Moved to the package for
the Phase 1 steps that call a model (13: neuroscience filter; 14a: classification; 15:
grouping; 16: summaries). Changes from S5: the cache lives in ``data/cache/llm/`` under
``SYN_DATA_DIR`` (never committed), and nothing spike-specific.

Kept from Paleo and S5: structured output validated with pydantic, a per-minute/per-day
rate limiter whose daily usage is persisted (so runs on the same day share the free
quota), a content cache (same prompt + model -> disk, so a text is generated once per
change), per-model ``extra_body`` (Qwen and gpt-oss switch reasoning differently) and the
``x-ratelimit-*`` headers of the last response. API keys come from the environment only
and are never printed. Tests use a fake client (``FakeLLM``), never a real model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from synaptica.config import USER_AGENT, get_paths

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4  # rough estimate before a call; the response reports exact usage


def prompt(name: str) -> tuple[str, str]:
    """(text, version) of ``synaptica/prompts/<name>.md`` (copied from paleo-atlas
    ``narrative/facts.py``): the first line is ``<!-- version: … -->``."""
    text = resources.files("synaptica.prompts").joinpath(f"{name}.md").read_text("utf-8")
    first = text.splitlines()[0]
    version = first.removeprefix("<!-- version:").removesuffix("-->").strip()
    return text.split("\n", 1)[1].strip(), version


class QuotaExhausted(RuntimeError):
    """The daily token or request quota of a model is used up."""


class LLMOutputError(RuntimeError):
    """The model did not return valid JSON for the requested schema."""


class HttpError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code


@dataclass(frozen=True)
class Limits:
    requests_per_minute: int
    tokens_per_minute: int
    requests_per_day: int
    tokens_per_day: int


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key_env: tuple[str, ...] = ()
    limits: Limits | None = None  # None = local, no quota
    extra_body: dict[str, Any] = field(default_factory=dict)

    def api_key(self) -> str | None:
        for var in self.api_key_env:
            if value := os.environ.get(var):
                return value
        return None


# Groq free tier per chat model, from console.groq.com/docs/rate-limits (2026-11-10);
# groq_limits.py checks them against the response headers.
GROQ_FREE = Limits(
    requests_per_minute=30, tokens_per_minute=8_000, requests_per_day=1_000, tokens_per_day=200_000
)

PROVIDERS: dict[str, Provider] = {
    "ollama": Provider(
        "ollama",
        os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        # Qwen models "think" by default in Ollama; we only want the answer.
        extra_body={"reasoning_effort": "none"},
    ),
    "groq": Provider(
        "groq",
        "https://api.groq.com/openai/v1",
        api_key_env=("GROQ_API_KEY",),
        limits=GROQ_FREE,
        extra_body={"reasoning_effort": "low"},
    ),
}

# Model-specific overrides of the provider's extra_body.
MODEL_EXTRA: dict[str, dict[str, Any]] = {
    # Qwen on Groq accepts "none" | "default" instead of low/medium/high.
    "qwen/qwen3.8-27b": {"reasoning_effort": "none"},
}


# --------------------------------------------------------------------------- http


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    retries: int = 4,
) -> httpx.Response:
    """POST JSON; retry 429/5xx with backoff (honouring ``retry-after``), raise other 4xx."""
    for attempt in range(retries + 1):
        try:
            r = client.post(url, json=payload, headers=headers)
        except httpx.TransportError as exc:
            if attempt == retries:
                raise HttpError(0, str(exc)) from exc
            time.sleep(2**attempt)
            continue
        if r.status_code < 400:
            return r
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == retries:
                raise HttpError(r.status_code, r.text[:500])
            wait = float(r.headers.get("retry-after") or 2**attempt)
            log.warning("HTTP %s, retrying in %.1fs", r.status_code, wait)
            time.sleep(min(wait, 120))
            continue
        raise HttpError(r.status_code, r.text[:500])
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------- quota


class RateLimiter:
    """Per-model request/token budget: waits per minute, stops per day (as in Paleo)."""

    def __init__(
        self,
        limits: Limits,
        usage_path: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        today: Callable[[], dt.date] = lambda: dt.datetime.now(dt.UTC).date(),
    ) -> None:
        self.limits = limits
        self.usage_path = usage_path
        self.clock = clock
        self.sleep = sleep
        self.today = today
        self._window: deque[tuple[float, int]] = deque()

    def _load(self) -> dict[str, Any]:
        if self.usage_path.exists():
            return json.loads(self.usage_path.read_text(encoding="utf-8"))
        return {}

    def _day(self, model: str) -> dict[str, int]:
        usage = self._load().get(self.today().isoformat(), {})
        return usage.get(model, {"requests": 0, "tokens": 0})

    def acquire(self, model: str, estimated_tokens: int) -> None:
        if estimated_tokens > self.limits.tokens_per_minute:
            raise ValueError(
                f"{model}: a single call of ~{estimated_tokens} tokens exceeds the "
                f"{self.limits.tokens_per_minute} tokens/minute limit; split the input"
            )
        day = self._day(model)
        if (
            day["requests"] + 1 > self.limits.requests_per_day
            or day["tokens"] + estimated_tokens > self.limits.tokens_per_day
        ):
            raise QuotaExhausted(f"{model}: daily quota used ({day['tokens']} tokens)")
        while True:
            now = self.clock()
            while self._window and now - self._window[0][0] >= 60:
                self._window.popleft()
            tokens = sum(t for _, t in self._window)
            if (
                len(self._window) < self.limits.requests_per_minute
                and tokens + estimated_tokens <= self.limits.tokens_per_minute
            ):
                return
            self.sleep(max(0.5, 60 - (now - self._window[0][0])))

    def record(self, model: str, tokens: int) -> None:
        self._window.append((self.clock(), tokens))
        usage = self._load()
        day = usage.setdefault(self.today().isoformat(), {}).setdefault(
            model, {"requests": 0, "tokens": 0}
        )
        day["requests"] += 1
        day["tokens"] += tokens
        for key in sorted(usage)[:-7]:
            del usage[key]
        _atomic_write(self.usage_path, json.dumps(usage, indent=1) + "\n")


# --------------------------------------------------------------------------- client


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_json(content: str) -> Any:
    """JSON from a model answer, tolerating fences, <think> blocks and leading prose."""
    text = _FENCE.sub("", _THINK.sub("", content).strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise
        return json.loads(text[start:])


@dataclass
class CallStats:
    calls: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def snapshot(self) -> CallStats:
        return CallStats(**vars(self))

    def since(self, before: CallStats) -> dict[str, float]:
        return {k: round(getattr(self, k) - getattr(before, k), 2) for k in vars(self)}


class LLM:
    """Chat client for one provider and model, returning validated JSON."""

    def __init__(
        self,
        provider: str | Provider,
        model: str,
        *,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        limiter: RateLimiter | None = None,
        temperature: float = 0.2,
        timeout: float = 600.0,
    ) -> None:
        self.provider = PROVIDERS[provider] if isinstance(provider, str) else provider
        self.model = model
        self.temperature = temperature
        cache_root = get_paths().cache
        self.cache_dir = cache_dir if cache_dir is not None else cache_root / "llm"
        if limiter is None and self.provider.limits is not None:
            limiter = RateLimiter(self.provider.limits, cache_root / "llm_usage.json")
        self.limiter = limiter
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout), headers={"User-Agent": USER_AGENT}
        )
        self.stats = CallStats()
        self.last_headers: dict[str, str] = {}
        self._schema_mode = "json_schema"  # downgraded to json_object if unsupported

    @property
    def label(self) -> str:
        return f"{self.provider.name}/{self.model}"

    def _cache_path(self, payload: dict[str, Any]) -> Path:
        key = json.dumps(
            {"provider": self.provider.name, **payload}, sort_keys=True, ensure_ascii=False
        )
        return self.cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key_env:
            key = self.provider.api_key()
            if not key:
                names = " or ".join(self.provider.api_key_env)
                raise RuntimeError(f"Missing API key for {self.provider.name}: set {names}")
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _response_format(self, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        if self._schema_mode == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": False},
            }
        return {"type": "json_object"}

    def complete_json[T: BaseModel](
        self,
        system: str,
        user: str,
        output: type[T],
        *,
        max_tokens: int = 2_000,
        use_cache: bool = True,
    ) -> T:
        """Ask for an answer matching ``output`` (a pydantic model) and validate it."""
        schema = output.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": f"{system}\n\nAnswer with JSON matching this schema:\n"
                f"{json.dumps(schema, ensure_ascii=False)}",
            },
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            **self.provider.extra_body,
            **MODEL_EXTRA.get(self.model, {}),
        }
        cache_key = {k: payload[k] for k in ("model", "messages", "temperature", "max_tokens")}
        cache_path = self._cache_path(cache_key)
        if use_cache and cache_path.exists():
            self.stats.cached += 1
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            # Cached answers still count their original tokens, so the spike's per-summary
            # figures do not depend on whether the cache was warm.
            usage = cached.get("usage") or {}
            self.stats.prompt_tokens += usage.get("prompt_tokens", 0)
            self.stats.completion_tokens += usage.get("completion_tokens", 0)
            self.stats.seconds += cached.get("seconds", 0.0)
            return output.model_validate(parse_json(cached["content"]))

        payload["response_format"] = self._response_format(output.__name__, schema)
        for attempt in range(2):
            try:
                content, usage, seconds = self._answer(payload, messages)
                result = output.model_validate(parse_json(content))
                break
            except (json.JSONDecodeError, ValidationError, HttpError) as exc:
                if isinstance(exc, HttpError) and "json_validate_failed" not in str(exc):
                    raise
                if attempt:
                    raise LLMOutputError(f"{self.label}: invalid output ({exc})") from exc
                log.warning("%s: invalid output, retrying with more tokens (%s)", self.label, exc)
                payload["max_tokens"] = max_tokens * 2
        record = {
            "model": self.label,
            "created": dt.datetime.now(dt.UTC).isoformat(),
            "usage": usage,
            "seconds": round(seconds, 3),
        }
        _atomic_write(cache_path, json.dumps({**record, "content": content}, ensure_ascii=False))
        return result

    def _answer(
        self, payload: dict[str, Any], messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, int], float]:
        estimated = (
            sum(len(m["content"]) for m in messages) // CHARS_PER_TOKEN + payload["max_tokens"]
        )
        if self.limiter:
            self.limiter.acquire(self.model, estimated)
        started = time.monotonic()
        body = self._post(payload)
        seconds = time.monotonic() - started
        usage = body.get("usage") or {}
        self.stats.seconds += seconds
        self.stats.calls += 1
        self.stats.prompt_tokens += usage.get("prompt_tokens", 0)
        self.stats.completion_tokens += usage.get("completion_tokens", 0)
        if self.limiter:
            self.limiter.record(self.model, usage.get("total_tokens", estimated))
        content = body["choices"][0]["message"].get("content") or ""
        return content, usage, seconds

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.provider.base_url}/chat/completions"
        try:
            r = post_json(self.client, url, payload, headers=self._headers())
        except HttpError as exc:
            if exc.status_code == 400 and "json_validate_failed" in str(exc):
                raise
            if exc.status_code == 400 and self._schema_mode == "json_schema":
                log.warning("%s: json_schema not accepted, falling back to json_object", self.label)
                self._schema_mode = "json_object"
                payload["response_format"] = {"type": "json_object"}
                r = post_json(self.client, url, payload, headers=self._headers())
            else:
                raise
        self.last_headers = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit")}
        return r.json()
