"""Drafts of Neuro Lab's texts, «what it lets us see» and «limits», for each technique
(B2-4, Aday's option A of v202; step 8 of the plan of 2026-11-17).

The same chain and checks as the study summaries (:mod:`synaptica.narrative`), with the
Wikipedia lead of :mod:`synaptica.lab.sources` as the source:

1. facts from the lead (prompt ``lab_facts``), each with a verbatim quote and its kind
   (``what``, ``limit``, ``other``), kept only if :func:`checks.check_fact` passes;
2. per section, an English paragraph from its facts (``lab_write_en``) that passes
   :func:`checks.check_text` (every sentence cites facts; numbers and names from them; no
   8 words copied from the lead; no overclaims), one retry with the failures as feedback;
3. its Spanish (``adapt_es``), aligned, without new claims, and spelled right.

A section with too few verified facts, or whose text fails, is not written: the page
keeps its gap. Nothing here is published: the drafts go to ``texts.json`` next to this
module and from there to Sofía's queue; only her approval puts them on the site.

By hand (``syn lab write --provider groq``), never in the daily pipeline, and only with
Aday's OK for each run (CLAUDE.md: no LLM without it).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from synaptica.lab.sources import SOURCES
from synaptica.lab.studies import techniques
from synaptica.llm import LLM, LLMOutputError, prompt
from synaptica.narrative.checks import (
    check_alignment,
    check_claims_es,
    check_fact,
    check_spelling_es,
    check_text,
)
from synaptica.narrative.write import ATTEMPTS, Summary, _public, adapt_es
from synaptica.wiki import read_json, write_json

TEXTS = Path(__file__).with_name("texts.json")
SECTIONS = ("what", "limit")
MIN_FACTS = {"what": 2, "limit": 1}  # fewer verified facts: no text, the gap stays
MIN_WORDS, MAX_WORDS = 20, 100


class LabFact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the lead")
    kind: Literal["what", "limit", "other"]


class LabFacts(BaseModel):
    facts: list[LabFact]


def facts(llm: LLM, tech: dict[str, Any], lead: str) -> tuple[list[dict[str, str]], list[str]]:
    """Verified facts ``[{id, statement, kind, quote}]`` and why the others were dropped."""
    system, _ = prompt("lab_facts")
    out = llm.complete_json(system, f"TECHNIQUE: {tech['name_en']}\n\nLEAD:\n{lead}", LabFacts,
                            max_tokens=1_000)  # fmt: skip
    kept, rejected = [], []
    for f in out.facts:
        if reason := check_fact(f.statement, f.quote, lead):
            rejected.append(reason.split(":")[0])  # never a copied run
            continue
        kept.append({"id": f"f{len(kept) + 1}", "statement": f.statement.strip(),
                     "kind": f.kind, "quote": f.quote})  # fmt: skip
    return kept, rejected


def _english(llm: LLM, tech: dict[str, Any], section: str, mine: list[dict[str, str]],
             feedback: list[str]) -> list[tuple[str, list[str]]]:  # fmt: skip
    system, _ = prompt("lab_write_en")
    label = "what it lets us see" if section == "what" else "limits"
    lines = [f"TECHNIQUE: {tech['name_en']}", f"SECTION: {label}", "", "VERIFIED FACTS:",
             *(f"{f['id']} {f['statement']}" for f in mine)]  # fmt: skip
    if feedback:
        lines += ["", "Your previous answer failed these automatic checks. Fix every one:",
                  *feedback]  # fmt: skip
    out = llm.complete_json(system, "\n".join(lines), Summary, max_tokens=600)
    return [(s.text.strip(), s.fact_ids) for s in out.sentences]


def section(llm: LLM, tech: dict[str, Any], kind: str, verified: list[dict[str, str]],
            lead: str) -> dict[str, Any]:  # fmt: skip
    """One section in both languages, or why there is none."""
    mine = [f for f in verified if f["kind"] == kind]
    if len(mine) < MIN_FACTS[kind]:
        return {"status": "too_few_facts", "facts": len(mine)}
    support = {f["id"]: f"{f['statement']} {f['quote']}" for f in mine}
    feedback: list[str] = []
    en: list[tuple[str, list[str]]] = []
    for _ in range(ATTEMPTS):
        en = _english(llm, tech, kind, mine, feedback)
        report = check_text(en, support, [lead], min_words=MIN_WORDS, max_words=MAX_WORDS)
        feedback = report.summary()
        if report.passed:
            break
    if feedback:
        return {"status": "failed_en", "problems": _public(feedback)}
    en_texts = [t for t, _ in en]
    es: list[str] = []
    for _ in range(ATTEMPTS):
        es = adapt_es(llm, en_texts, feedback)
        feedback = [*check_alignment(en_texts, es), *check_claims_es(en_texts, es),
                    *check_spelling_es(en_texts, es)]  # fmt: skip
        if not feedback:
            break
    if feedback:
        return {"status": "failed_es", "problems": _public(feedback),
                "en": [{"text": t, "fact_ids": f} for t, f in en]}  # fmt: skip
    ids = [f for _, f in en]  # the Spanish cites what its English sentence cites
    return {
        "status": "drafted",
        "en": [{"text": t, "fact_ids": f} for t, f in en],
        "es": [{"text": t, "fact_ids": f} for t, f in zip(es, ids, strict=True)],
    }


def write(
    llm: LLM,
    *,
    only: list[str] | None = None,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, dict[str, str]]:
    """Draft the techniques with an accepted English lead (``only``: these ids), keep the
    rest of ``texts.json`` and return technique -> section -> status. A technique already
    drafted from the same revision is not asked again (it would cost quota)."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sources = read_json(sources_path or SOURCES, "techniques")
    texts = read_json(path, "techniques")
    status: dict[str, dict[str, str]] = {}
    for tech in techniques():
        tid = tech["id"]
        en_src = (sources.get(tid) or {}).get("en") or {}
        if (only and tid not in only) or not en_src.get("accepted"):
            continue
        old = texts.get(tid)
        if old and old.get("revid") == en_src["revid"] and not only:
            continue
        try:
            verified, rejected = facts(llm, tech, en_src["lead"])
        except LLMOutputError:  # nothing saved for it: asked again on the next run
            status[tid] = dict.fromkeys(SECTIONS, "model_error")
            continue
        record = {"revid": en_src["revid"], "source": en_src["url"],
                  "source_es": ((sources[tid].get("es") or {}).get("url")),
                  "generator": llm.label,
                  "prompts": {n: prompt(n)[1] for n in ("lab_facts", "lab_write_en", "adapt_es")},
                  "generated_at": now.isoformat(timespec="seconds"),
                  "facts": [{k: f[k] for k in ("id", "statement", "kind")} for f in verified],
                  "rejected": rejected}  # fmt: skip
        try:
            for kind in SECTIONS:
                record[kind] = section(llm, tech, kind, verified, en_src["lead"])
        except LLMOutputError:
            status[tid] = dict.fromkeys(SECTIONS, "model_error")
            continue
        texts[tid] = record
        status[tid] = {k: record[k]["status"] for k in SECTIONS}
    write_json(path, {
        "note": "Drafts of Neuro Lab's texts (LLM, checked against each technique's Wikipedia "
        "lead in lab/sources.json). Not published: each waits for Sofía's approval. Written "
        "by `syn lab write`; do not edit by hand.",
        "techniques": {t["id"]: texts[t["id"]] for t in techniques() if t["id"] in texts},
    })  # fmt: skip
    return status
