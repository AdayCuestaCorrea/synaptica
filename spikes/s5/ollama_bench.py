"""S5 · Ollama throughput on the local GPU: tokens/s of the Qwen models Paleo uses.

Uses the native ``/api/chat`` (it reports ``eval_count``/``eval_duration`` and the prompt
evaluation separately), thinking off, a fixed prompt of the size of a real summary call
(about 1500 input tokens: an invented study text, no publisher text) and 3 repetitions
after one warm-up call that loads the model. Each run starts with a different line
so the prompt is evaluated again, not reused from Ollama's cache. Run from the repo root:

    uv run python spikes/s5/ollama_bench.py
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import subprocess
from pathlib import Path

import httpx

MODELS = ("paleo-qwen3.5-9b", "paleo-qwen3.5-4b")
REPEATS = 3
URL = "http://localhost:11434/api/chat"
OUT = Path(__file__).parent / "results" / "ollama_bench.json"

# Invented filler of realistic length; no real abstract is used for the benchmark.
STUDY = " ".join(
    f"In experiment {i}, the team recorded neurons in the hippocampus of adult mice while "
    f"they explored a maze, and found that activity patterns during rest replayed the "
    f"routes taken before, more often after a reward than after no reward."
    for i in range(1, 31)
)
PROMPT = (
    "Summarize the following invented study for a general audience in 4 sentences, "
    'about 100 words, as JSON {"sentences": [..]}.\n\n' + STUDY
)


def run(client: httpx.Client, model: str, n: int) -> dict[str, float]:
    r = client.post(URL, json={
        "model": model, "stream": False, "think": False, "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
        # A different first line each run, so Ollama cannot reuse the cached prompt.
        "messages": [{"role": "user", "content": f"Run {model} #{n}.\n{PROMPT}"}],
    })  # fmt: skip
    r.raise_for_status()
    b = r.json()
    return {
        "prompt_tokens": b["prompt_eval_count"],
        "prompt_tok_s": b["prompt_eval_count"] / (b["prompt_eval_duration"] / 1e9),
        "output_tokens": b["eval_count"],
        "output_tok_s": b["eval_count"] / (b["eval_duration"] / 1e9),
        "total_s": b["total_duration"] / 1e9,
    }


def main() -> None:
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip
    results: dict[str, object] = {"measured_at": dt.datetime.now(dt.UTC).isoformat(), "gpu": gpu}
    with httpx.Client(timeout=600) as client:
        for model in MODELS:
            run(client, model, 0)  # warm-up: loads the model into VRAM
            runs = [run(client, model, n) for n in range(1, REPEATS + 1)]
            summary = {k: round(statistics.median(r[k] for r in runs), 1) for k in runs[0]}
            print(model, summary)
            results[model] = {"median": summary, "runs": runs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
