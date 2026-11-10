"""S5 · Review sheet for Sofía: the S5 summaries, blind, with the judge's verdict hidden.

For each of the 10 articles it shows two summaries: the local Qwen 9B (the initial load)
and Qwen 27B on Groq (the daily runs), in a fixed pseudo-random order and without
saying which is which. The study itself is linked on PubMed: no abstract goes into the
page. Sofía answers in the page and copies her answers to send them to Aday. The key
(which version is which model) goes to ``results/review_key.json``. Run from the repo root:

    uv run --group spike-s5 python spikes/s5/review_page.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from pipeline import fetch_articles  # noqa: E402

RUNS = {
    "local-qwen3.5-9b": "run_ollama-paleo-qwen3.5-9b-groq-openai-gpt-oss-120b.json",
    "groq-qwen3.8-27b": "run_groq-qwen-qwen3.8-27b-groq-openai-gpt-oss-120b.json",
}
# The judge answers in English; the reasons shown to Sofía, in Spanish.
REASONS_ES = {
    "Summary incorrectly states the study was in humans": (
        "El resumen dice que el estudio se hizo en humanos, y no es así."
    ),
    "Controls are described as healthy people, which is not stated in the abstract": (
        "Describe a los controles como personas sanas, y el abstract no lo dice."
    ),
    "Overstates safety beyond the study's reassurance": (
        "Exagera la seguridad: afirma más de lo que el estudio permite concluir."
    ),
}
OUT = HERE / "review" / "revision-sofia.html"
TEMPLATE = HERE / "review" / "template.html"


def main() -> None:
    titles = {a["pmid"]: a["title"] for a in fetch_articles()}
    rows = {
        model: {a["pmid"]: a for a in json.loads((HERE / "results" / f).read_text())["articles"]}
        for model, f in RUNS.items()
    }
    items, key = [], {}
    for pmid in rows["groq-qwen3.8-27b"]:
        models = list(RUNS)
        if int(hashlib.sha256(pmid.encode()).hexdigest(), 16) % 2:
            models.reverse()
        versions = []
        for n, model in enumerate(models, start=1):
            row = rows[model][pmid]
            if "es" not in row:  # did not get through the checks: nothing to review
                continue
            judge = row.get("judge") or {}
            versions.append({
                "id": f"v{n}",
                "es": row["es"],
                "en": row["en"],
                "judge_passed": judge.get("passed"),
                "judge_reason": REASONS_ES.get(judge.get("reason", ""), judge.get("reason", "")),
            })  # fmt: skip
            key[f"{pmid}-v{n}"] = model
        items.append({"pmid": pmid, "title": titles[pmid], "versions": versions})
    html = TEMPLATE.read_text("utf-8").replace(
        "/*DATA*/[]", json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    )
    OUT.write_text(html, encoding="utf-8")
    (HERE / "results" / "review_key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(items)} articles, {sum(len(i['versions']) for i in items)} summaries -> {OUT}")


if __name__ == "__main__":
    main()
