"""The daily cap of our own counter (RateLimiter): it stops before calling the provider."""

import datetime as dt

import pytest

from synaptica.llm import Limits, QuotaExhausted, RateLimiter

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
