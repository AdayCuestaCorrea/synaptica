"""Step 2 of a summary: English prose from the verified facts, then Spanish sentence by
sentence, both checked (plan, step 16).

Adapted from spike S5 ``spikes/s5/pipeline.py`` (``write_en``, ``adapt_es`` and parts 2 and 3
of ``run_article``) and paleo-atlas ``src/paleo/narrative/write.py`` (``_save``,
``is_up_to_date``, the ``texts`` / ``texts_review`` folders). A text that fails its
checks gets one more attempt with the list of problems, as in S5; if it fails again it
goes to ``derived/texts_review/`` and the site shows the fallback text
(:mod:`synaptica.narrative.fallback`). No Spanish is written from a failed English text.

A failed text is committed to the ``data`` branch, so its problems never quote the
copied run, and a text that failed the anti-copy check keeps no sentences at all.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.narrative.checks import (
    N_GRAM,
    TextReport,
    check_alignment,
    check_claims_es,
    check_spelling_es,
    check_text,
)
from synaptica.narrative.facts import slug
from synaptica.store import _atomic_write

ATTEMPTS = 2  # S5: one retry with the failures as feedback


class Sentence(BaseModel):
    text: str
    fact_ids: list[str] = Field(description="ids of the facts this sentence relies on")


class Summary(BaseModel):
    sentences: list[Sentence]


class Adapted(BaseModel):
    index: int = Field(description="index of the English sentence, starting at 1")
    text: str = Field(description="the Spanish version of that sentence")


class AdaptedText(BaseModel):
    sentences: list[Adapted]


def text_path(
    study_id: str, lang: str, *, verified: bool, derived_root: Path | None = None
) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / ("texts" if verified else "texts_review") / f"{slug(study_id)}.{lang}.json"


def facts_hash(facts: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]


def prompt_versions() -> dict[str, str]:
    return {"en": prompt("write_en")[1], "es": prompt("adapt_es")[1]}


def is_up_to_date(facts_doc: dict[str, Any], derived_root: Path | None = None) -> bool:
    """Both texts (or a failed English one) written from these facts and prompts."""
    key, current = facts_doc["study_id"], facts_hash(facts_doc["facts"])
    versions = prompt_versions()

    def same(lang: str, verified: bool) -> bool:
        path = text_path(key, lang, verified=verified, derived_root=derived_root)
        if not path.exists():
            return False
        stored = json.loads(path.read_text(encoding="utf-8"))
        return stored["facts_hash"] == current and stored["prompt_version"] == versions[lang]

    if same("en", False):
        return True  # English failed with these facts and prompt: asking again costs quota
    return same("en", True) and (same("es", True) or same("es", False))


def _public(problems: list[str]) -> list[str]:
    """Problems without the quoted text (it may hold a run copied from the abstract)."""
    return [re.sub(r" \('.*?'\)|: '.*'$", "", p) for p in problems]


def write_en(
    llm: LLM,
    facts: dict[str, str],
    feedback: list[str],
    prompt_name: str = "write_en",
    *,
    fact_lines: list[str] | None = None,
) -> list[tuple[str, list[str]]]:
    """English sentences with their fact ids. ``fact_lines`` replaces the plain list of
    facts (the weekly summary groups them by study)."""
    system = prompt(prompt_name)[0]
    lines = ["VERIFIED FACTS:", *(fact_lines or [f"{k} {v}" for k, v in facts.items()])]
    if feedback:
        lines += ["", "Your previous answer failed these automatic checks. Fix every one:",
                  *feedback,
                  "A number must be written exactly as in a cited fact or dropped; a name must "
                  "appear in the facts; a copied run of words must be rephrased."]  # fmt: skip
    out = llm.complete_json(system, "\n".join(lines), Summary, max_tokens=2_500)
    return [(s.text.strip(), s.fact_ids) for s in out.sentences]


def adapt_es(llm: LLM, en: list[str], feedback: list[str]) -> list[str]:
    system = prompt("adapt_es")[0]
    lines = ["FRASES EN INGLÉS:", *(f"{i}. {t}" for i, t in enumerate(en, start=1))]
    if feedback:
        lines += ["", "Tu respuesta anterior no pasó estas comprobaciones. Corrígelas todas:",
                  *feedback]  # fmt: skip
    out = llm.complete_json(system, "\n".join(lines), AdaptedText, max_tokens=1_500)
    by_index = {s.index: s.text.strip() for s in out.sentences}
    return [by_index.get(i, "") for i in range(1, len(en) + 1)]


def _save(
    facts_doc: dict[str, Any],
    lang: str,
    *,
    verified: bool,
    llm: LLM,
    sentences: list[tuple[str, list[str]]],
    problems: list[str],
    word_count: int | None,
    derived_root: Path | None,
    now: dt.datetime,
) -> None:
    key = facts_doc["study_id"]
    copied = any(f"copies {N_GRAM}+ words" in p for p in problems)
    record = {
        "study_id": key,
        "lang": lang,
        "status": "verified" if verified else "failed",
        "generator": llm.label,
        "prompt_version": prompt_versions()[lang],
        "facts_hash": facts_hash(facts_doc["facts"]),
        "generated_at": now.isoformat(timespec="seconds"),
        "word_count": word_count,
        "problems": _public(problems),
        "sentences": [] if copied else [{"text": t, "fact_ids": f} for t, f in sentences],
    }
    path = text_path(key, lang, verified=verified, derived_root=derived_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    if verified:  # a verified text retires the failed one it replaces
        text_path(key, lang, verified=False, derived_root=derived_root).unlink(missing_ok=True)


def write_study(
    llm: LLM,
    facts_doc: dict[str, Any],
    quotes: dict[str, str],
    abstract: str,
    *,
    derived_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, str]:
    """Write and check both texts; returns ``{"en": status, "es": status}`` (``es`` is
    missing when the English text failed)."""
    now = now or dt.datetime.now(dt.UTC)
    facts = facts_doc["facts"]
    # The writer sees subject and statement; the checks also accept what the quote says.
    shown = {f["id"]: f"[{f['subject']}] {f['statement']}" for f in facts}
    support = {f["id"]: f"{f['statement']} {quotes.get(f['id'], '')}" for f in facts}
    feedback: list[str] = []
    en: list[tuple[str, list[str]]] = []
    report: TextReport | None = None
    for _ in range(ATTEMPTS):
        en = write_en(llm, shown, feedback)
        report = check_text(en, support, [abstract])
        feedback = report.summary()
        if report.passed:
            break
    assert report is not None
    _save(facts_doc, "en", verified=report.passed, llm=llm, sentences=en, problems=feedback,
          word_count=report.word_count, derived_root=derived_root, now=now)  # fmt: skip
    if not report.passed:
        return {"en": "failed"}
    en_texts = [t for t, _ in en]
    feedback, es = [], []
    for _ in range(ATTEMPTS):
        es = adapt_es(llm, en_texts, feedback)
        feedback = [*check_alignment(en_texts, es), *check_claims_es(en_texts, es),
                    *check_spelling_es(en_texts, es)]  # fmt: skip
        if not feedback:
            break
    es_sentences = [(t, f) for t, (_, f) in zip(es, en, strict=True)]  # same facts as EN
    _save(facts_doc, "es", verified=not feedback, llm=llm, sentences=es_sentences,
          problems=feedback, word_count=None, derived_root=derived_root, now=now)  # fmt: skip
    return {"en": "verified", "es": "failed" if feedback else "verified"}


def recheck_es(path: Path, derived_root: Path | None = None,
               now: dt.datetime | None = None) -> str:  # fmt: skip
    """Run today's Spanish checks again on a failed Spanish text, with no model call
    (``syn recheck``, step 20: the checks had false positives). Returns ``verified``
    (moved to ``texts/``), ``failed`` (problems updated), or ``stale`` when its English is
    not verified with the same facts and prompts any more (``syn write`` redoes it)."""
    record = json.loads(path.read_text(encoding="utf-8"))
    key = record["study_id"]
    en_path = text_path(key, "en", verified=True, derived_root=derived_root)
    en = json.loads(en_path.read_text(encoding="utf-8")) if en_path.exists() else None
    versions = prompt_versions()
    if (en is None or en["facts_hash"] != record["facts_hash"]
            or record["prompt_version"] != versions["es"]
            or en["prompt_version"] != versions["en"] or not record["sentences"]):  # fmt: skip
        return "stale"
    en_texts = [s["text"] for s in en["sentences"]]
    es = [s["text"] for s in record["sentences"]]
    problems = [*check_alignment(en_texts, es), *check_claims_es(en_texts, es),
                *check_spelling_es(en_texts, es)]  # fmt: skip
    stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    record = {**record, "problems": _public(problems), "rechecked_at": stamp}
    if problems:
        _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
        return "failed"
    record["status"] = "verified"
    target = text_path(key, "es", verified=True, derived_root=derived_root)
    _atomic_write(target, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    path.unlink()
    return "verified"
