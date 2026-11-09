"""Shared helpers for the S1 source spike (throwaway code, not part of the package).

Each script downloads about 10 items from one source, prints what matters for
docs/fuentes.md (status, rate-limit headers, volume) and saves the responses as fixtures
in tests/fixtures/<source>/. Run from the repo root:

    uv run --env-file .env python spikes/s1/<source>.py

Fixtures never keep abstracts, descriptions or article text: the repository is public and
that text belongs to the publisher (CLAUDE.md: no abstracts are published). They are
replaced by REDACTED, keeping the rest of the structure for the Phase 1 parsers.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import USER_AGENT, project_root

FIXTURES = project_root() / "tests" / "fixtures"
REDACTED = "[REDACTED in fixture: publisher text, not redistributed]"

# Keys whose values are publisher text, in any JSON response.
TEXT_KEYS = {"abstract", "abstracttext", "abstract_inverted_index", "description", "summary"}
# XML/HTML elements whose content is publisher text (PubMed, RSS, Atom).
TEXT_TAGS = ("AbstractText", "description", "content:encoded", "summary", "content", "abstract")

RATE_HEADERS = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-rate-limit-limit",
                "x-rate-limit-interval", "x-concurrency-limit", "retry-after")  # fmt: skip


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )


def get(c: httpx.Client, url: str, pause: float = 0.5, **kwargs: Any) -> httpx.Response:
    """GET in series with a pause, printing status and rate-limit headers."""
    r = c.get(url, **kwargs)
    shown = {h: r.headers[h] for h in RATE_HEADERS if h in r.headers}
    url = r.url.copy_remove_param("api_key")  # never print a key
    kind = r.headers.get("content-type", "?")[:40]
    print(f"  {r.status_code} {kind} {len(r.content):>8} B  {url}  {shown or ''}")
    time.sleep(pause)
    return r


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if k.lower() in TEXT_KEYS and v else redact_json(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_json(v) for v in value]
    return value


def redact_xml(text: str) -> str:
    for tag in TEXT_TAGS:
        pattern = rf"(<{re.escape(tag)}\b[^>]*>)(.*?)(</{re.escape(tag)}>)"
        text = re.sub(pattern, rf"\g<1>{REDACTED}\g<3>", text, flags=re.DOTALL)
    return text


def save_json(source: str, name: str, data: Any) -> Path:
    path = FIXTURES / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_json(data), ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"  -> {path.relative_to(project_root())}")
    return path


def save_text(source: str, name: str, text: str) -> Path:
    path = FIXTURES / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact_xml(text), "utf-8")
    print(f"  -> {path.relative_to(project_root())}")
    return path
