"""S5 · Groq free tier: which chat models exist today and their real limits.

``GET /models`` lists the models; one tiny chat request per chat model returns the
``x-ratelimit-*`` headers. Groq documents ``*-requests`` as requests per day and
``*-tokens`` as tokens per minute. Results (never the key) go to
``results/groq_limits.json``. Run from the repo root:

    uv run --env-file .env python spikes/s5/groq_limits.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import httpx

from synaptica.config import USER_AGENT

BASE = "https://api.groq.com/openai/v1"
OUT = Path(__file__).parent / "results" / "groq_limits.json"
NOT_CHAT = ("whisper", "orpheus", "prompt-guard", "tts", "distil")


def main() -> None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY is not set (add it to .env)")
    headers = {"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT}
    out: dict[str, object] = {"measured_at": dt.datetime.now(dt.UTC).isoformat(), "models": {}}
    with httpx.Client(timeout=60, headers=headers) as c:
        listed = c.get(f"{BASE}/models").raise_for_status().json()["data"]
        for m in sorted(listed, key=lambda m: m["id"]):
            info = {k: m.get(k) for k in ("owned_by", "active", "context_window",
                                         "max_completion_tokens")}  # fmt: skip
            if not any(word in m["id"] for word in NOT_CHAT):
                r = c.post(f"{BASE}/chat/completions", json={
                    "model": m["id"], "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with the word OK."}],
                })  # fmt: skip
                info["status"] = r.status_code
                info["headers"] = {
                    k: v for k, v in sorted(r.headers.items()) if k.startswith("x-ratelimit")
                }
                if r.status_code >= 400:
                    info["error"] = r.text[:300]
                time.sleep(2.5)
            out["models"][m["id"]] = info
            print(m["id"], info.get("status", "-"), info.get("headers", ""))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
