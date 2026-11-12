"""Step 3 of a summary: an independent judge from another model family reads the
abstract and both texts before they are published (plan, step 19; decision D4).

Adapted from spike S5 ``spikes/s5/pipeline.py`` (``Verdict`` and part 4 of
``run_article``) with the v2 prompt after Sofía's review. As in S5, a summary is
published only when the judge passes it: the deterministic checks cannot see a wrong
design, a causal reading of an association or an animal result told as human, and in
S5 the judge caught three such errors that the checks let through. A rejected text goes
to ``derived/texts_review/`` with the judge's reason, and the site shows the fallback.

``spanish_natural`` (1-5) does not block: it is kept in the text record to order Sofía's
review queue. The judge must be of another family than the writer (Qwen writes,
gpt-oss judges): a model is not a check of itself.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from synaptica.llm import LLM, prompt
from synaptica.narrative.write import text_path
from synaptica.store import _atomic_write

FAMILIES = ("gpt-oss", "qwen", "llama", "gemma", "mistral", "deepseek", "kimi", "claude")


class Verdict(BaseModel):
    faithful: bool
    no_overclaim: bool
    no_medical_advice: bool
    spanish_matches: bool
    passed: bool
    reason: str = ""
    # Not a gate: orders Sofía's queue (judge-v2, after her S5 review).
    spanish_natural: int = Field(ge=1, le=5, description="1-5, how natural the Spanish reads")


def family(label: str) -> str | None:
    """Model family from a label such as ``groq/openai/gpt-oss-120b``."""
    lowered = label.lower()
    return next((f for f in FAMILIES if f in lowered), None)


def same_family(a: str, b: str) -> bool:
    fa, fb = family(a), family(b)
    return fa is not None and fa == fb


def _load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _dump(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=1) + "\n")


def is_judged(record: dict[str, Any]) -> bool:
    verdict = record.get("judge")
    return bool(verdict and verdict["prompt_version"] == prompt("judge")[1])


def pending(study_id: str, derived_root: Path | None = None) -> dict[str, dict] | None:
    """The verified texts of a study waiting for the judge (``en`` always, ``es`` when it
    passed its checks), or None when there is nothing to judge."""
    en = _load(text_path(study_id, "en", verified=True, derived_root=derived_root))
    if en is None or is_judged(en):
        return None
    texts = {"en": en}
    if es := _load(text_path(study_id, "es", verified=True, derived_root=derived_root)):
        texts["es"] = es
    return texts


def judge_study(
    judge: LLM,
    study: dict[str, Any],
    abstract: str,
    texts: dict[str, dict[str, Any]],
    *,
    derived_root: Path | None = None,
    now: dt.datetime | None = None,
) -> Verdict:
    """Ask the judge and record its verdict in each text; a failed verdict moves the
    texts to ``texts_review``."""
    if same_family(judge.label, texts["en"]["generator"]):
        raise ValueError(f"judge {judge.label} is of the writer's family "
                         f"({texts['en']['generator']})")  # fmt: skip
    system, version = prompt("judge")
    lines = [f"EN {i}. {s['text']}" for i, s in enumerate(texts["en"]["sentences"], 1)]
    if "es" in texts:
        lines += [f"ES {i}. {s['text']}" for i, s in enumerate(texts["es"]["sentences"], 1)]
    else:
        lines.append("(No Spanish version: judge spanish_matches as true.)")
    verdict = judge.complete_json(
        system,
        f"TITLE: {study['title']}\n\nABSTRACT:\n{abstract}\n\nSUMMARY:\n" + "\n".join(lines),
        Verdict,
        max_tokens=800,
    )
    stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    record = {**verdict.model_dump(), "generator": judge.label, "prompt_version": version,
              "judged_at": stamp}  # fmt: skip
    for lang, text in texts.items():
        text = {**text, "judge": record}
        if verdict.passed:
            _dump(text_path(study["study_id"], lang, verified=True, derived_root=derived_root),
                  text)  # fmt: skip
            continue
        # The reason may quote the abstract: keep only the first sentence, unquoted.
        reason = re.sub(r'["\u201c\u201d].*?["\u201c\u201d]', "…", verdict.reason)
        reason = reason.split(". ")[0]
        text = {**text, "status": "rejected_by_judge",
                "problems": [f"judge: {reason}".rstrip()]}  # fmt: skip
        _dump(text_path(study["study_id"], lang, verified=False, derived_root=derived_root),
              text)  # fmt: skip
        text_path(study["study_id"], lang, verified=True, derived_root=derived_root).unlink()
    return verdict
