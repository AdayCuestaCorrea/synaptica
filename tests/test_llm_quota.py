"""The daily cap of our own counter (RateLimiter): it stops before calling the provider."""

import datetime as dt
import json

import pytest

from synaptica.llm import MODEL_LIMITS, Limits, QuotaExhausted, RateLimiter

# Per-minute limits high enough never to wait; the day is what is tested.
LIMITS = Limits(
    requests_per_minute=1_000, tokens_per_minute=10_000, requests_per_day=3, tokens_per_day=1_000
)
MODEL = "openai/gpt-oss-120b"


def limiter(path, day):
    return RateLimiter(LIMITS, path, clock=lambda: 0.0, sleep=lambda s: None, today=lambda: day)


def test_tokens_per_day_stop_before_the_call_and_survive_a_new_run(tmp_path):
    path = tmp_path / "usage.json"
    today = dt.date(2026, 11, 14)
    first = limiter(path, today)
    first.acquire(MODEL, 400)
    first.record(MODEL, 400)
    first.acquire(MODEL, 500)
    first.record(MODEL, 500)
    # A new run the same day (another process) reads what the first one spent.
    second = limiter(path, today)
    second.acquire(MODEL, 100)  # 900 + 100 = 1000: exactly the cap is allowed
    with pytest.raises(QuotaExhausted):
        second.acquire(MODEL, 101)
    # Each model has its own quota.
    second.acquire("qwen/qwen3.8-27b", 1_000)


def test_requests_per_day_stop_too(tmp_path):
    lim = limiter(tmp_path / "usage.json", dt.date(2026, 11, 14))
    for _ in range(3):
        lim.acquire(MODEL, 1)
        lim.record(MODEL, 1)
    with pytest.raises(QuotaExhausted):
        lim.acquire(MODEL, 1)


def test_the_count_starts_again_the_next_utc_day(tmp_path):
    path = tmp_path / "usage.json"
    full = limiter(path, dt.date(2026, 11, 14))
    full.acquire(MODEL, 1_000)
    full.record(MODEL, 1_000)
    with pytest.raises(QuotaExhausted):
        full.acquire(MODEL, 1)
    limiter(path, dt.date(2026, 11, 15)).acquire(MODEL, 1_000)


# --- output tokens per minute (OTPM), v143 ---------------------------------------------

OTPM = Limits(
    requests_per_minute=1_000,
    tokens_per_minute=100_000,
    requests_per_day=1_000,
    tokens_per_day=1_000_000,
    output_tokens_per_minute=1_000,
)


def test_otpm_paces_the_reserved_max_tokens_within_a_minute(tmp_path):
    now = [0.0]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    lim = RateLimiter(OTPM, tmp_path / "usage.json", clock=lambda: now[0], sleep=sleep,
                      today=lambda: dt.date(2026, 11, 14))  # fmt: skip
    for _ in range(2):  # 500 + 500 reserved: exactly the cap, no wait
        lim.acquire(MODEL, 100, 500)
        lim.record(MODEL, 100, 500)
    assert waits == []
    lim.acquire(MODEL, 100, 500)  # a third one waits for the minute to pass
    assert waits and now[0] >= 60


def test_a_call_above_the_otpm_cap_is_refused_before_asking(tmp_path):
    lim = RateLimiter(OTPM, tmp_path / "usage.json", clock=lambda: 0.0, sleep=lambda s: None)
    with pytest.raises(ValueError, match="output tokens/minute"):
        lim.acquire(MODEL, 100, 1_500)


def test_qwen_on_groq_cuts_max_tokens_to_its_cap(tmp_path, monkeypatch):
    import httpx

    from synaptica.llm import LLM
    from synaptica.news.neuro import BatchDecisions

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    asked = []

    def groq(request):
        asked.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"items": []}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })  # fmt: skip

    llm = LLM("groq", "qwen/qwen3.8-27b", client=httpx.Client(transport=httpx.MockTransport(groq)),
              cache_dir=tmp_path / "llm",
              limiter=RateLimiter(MODEL_LIMITS["qwen/qwen3.8-27b"], tmp_path / "usage.json",
                                  clock=lambda: 0.0, sleep=lambda s: None))  # fmt: skip
    llm.complete_json("system", "user", BatchDecisions, max_tokens=4_000)
    assert asked == [1_000]


def test_request_too_large_is_not_retried():
    import httpx

    from synaptica.llm import HttpError, post_json

    calls = []

    def groq(request):
        calls.append(1)
        return httpx.Response(
            429,
            text='{"error":{"message":"Request too large for model '
            '`qwen/qwen3.8-27b` ... (OTPM): Limit 1000, Requested 1500"}}',
        )

    with pytest.raises(HttpError, match="Request too large"):
        post_json(httpx.Client(transport=httpx.MockTransport(groq)), "https://x/chat", {},
                  headers={})  # fmt: skip
    assert calls == [1]  # no backoff loop: waiting cannot make it fit
