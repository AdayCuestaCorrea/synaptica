"""Drafts of a site's fixed texts from a Wikipedia lead, with the summaries' chain and checks
(generalized in v211 from :mod:`synaptica.lab.texts`, B2-4, so that Neuro Lab's techniques
and Neuro Atlas's regions share one chain; Aday's option of 2026-11-18).

1. facts from the lead (the spec's facts prompt), each with a verbatim quote and a kind,
   kept only if :func:`checks.check_fact` passes;
2. per section, an English paragraph from the facts of its kinds (the spec's writing
   prompt) that passes :func:`checks.check_text` (every sentence cites facts; numbers and
   names from them; no 8 words copied from the lead; no overclaims), one retry with the
   failures as feedback;
3. its Spanish (``adapt_es``), aligned, without new claims, and spelled right.

A section with too few verified facts, or whose text fails, is not written: the page keeps
its gap. Nothing here is published: each caller saves its drafts unpublished, sends them
to Sofía's queue and shows only what she approved (:func:`published`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synaptica.llm import LLM, prompt
from synaptica.narrative.checks import (
    check_alignment,
    check_claims_es,
    check_fact,
    check_spelling_es,
    check_text,
)
from synaptica.narrative.write import ATTEMPTS, Summary, _public, adapt_es
from synaptica.review.models import ItemType, ReviewItem, Sentence, Source, TextContent

PUBLISHED = ("approved", "edited")  # her approval, or her correction that passed (or kept)


@dataclass(frozen=True)
class Spec:
    """What changes from one kind of page to another; the chain does not."""

    subject: str  # the header of the prompts: «TECHNIQUE», «REGION»
    facts_prompt: str
    write_prompt: str
    facts_schema: type[BaseModel]  # ``facts``: a list with ``statement``, ``quote``, ``kind``
    sections: dict[str, str]  # section -> its label for the writer
    kinds: dict[str, tuple[str, ...]]  # section -> the fact kinds it is written from
    min_facts: dict[str, int]  # fewer verified facts: no text, the gap stays
    min_words: int = 20
    max_words: int = 100

    def prompts(self) -> dict[str, str]:
        return {n: prompt(n)[1] for n in (self.facts_prompt, self.write_prompt, "adapt_es")}


def facts(
    llm: LLM, spec: Spec, name: str, lead: str, *, prefix: str = "f", header: str = "LEAD"
) -> tuple[list[dict[str, str]], list[str]]:
    """Verified facts ``[{id, statement, kind, quote}]`` and why the others were dropped.
    ``lead`` may be another stretch of the article (``header`` names it, ``prefix`` keeps
    its fact ids apart from the lead's)."""
    system, _ = prompt(spec.facts_prompt)
    out = llm.complete_json(system, f"{spec.subject}: {name}\n\n{header}:\n{lead}",
                            spec.facts_schema, max_tokens=1_000)  # fmt: skip
    kept, rejected = [], []
    for f in out.facts:  # type: ignore[attr-defined]
        if reason := check_fact(f.statement, f.quote, lead):
            rejected.append(reason.split(":")[0])  # never a copied run
            continue
        kept.append({"id": f"{prefix}{len(kept) + 1}", "statement": f.statement.strip(),
                     "kind": f.kind, "quote": f.quote})  # fmt: skip
    return kept, rejected


def _english(llm: LLM, spec: Spec, name: str, section: str, mine: list[dict[str, str]],
             feedback: list[str]) -> list[tuple[str, list[str]]]:  # fmt: skip
    system, _ = prompt(spec.write_prompt)
    lines = [f"{spec.subject}: {name}", f"SECTION: {spec.sections[section]}", "",
             "VERIFIED FACTS:", *(f"{f['id']} {f['statement']}" for f in mine)]  # fmt: skip
    if feedback:
        lines += ["", "Your previous answer failed these automatic checks. Fix every one:",
                  *feedback]  # fmt: skip
    out = llm.complete_json(system, "\n".join(lines), Summary, max_tokens=600)
    return [(s.text.strip(), s.fact_ids) for s in out.sentences]


def section(llm: LLM, spec: Spec, name: str, kind: str, verified: list[dict[str, str]],
            lead: str) -> dict[str, Any]:  # fmt: skip
    """One section in both languages, or why there is none."""
    mine = [f for f in verified if f["kind"] in spec.kinds[kind]]
    if len(mine) < spec.min_facts[kind]:
        return {"status": "too_few_facts", "facts": len(mine)}
    support = {f["id"]: f"{f['statement']} {f['quote']}" for f in mine}
    feedback: list[str] = []
    en: list[tuple[str, list[str]]] = []
    for _ in range(ATTEMPTS):
        en = _english(llm, spec, name, kind, mine, feedback)
        report = check_text(en, support, [lead], min_words=spec.min_words,
                            max_words=spec.max_words)  # fmt: skip
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


def draft(llm: LLM, spec: Spec, name: str, lead: str) -> dict[str, Any]:
    """Facts and every section of one subject. Raises :class:`LLMOutputError` when the
    model fails: the caller saves nothing for it, and it is asked again on the next run."""
    verified, rejected = facts(llm, spec, name, lead)
    record: dict[str, Any] = {
        "facts": [{k: f[k] for k in ("id", "statement", "kind")} for f in verified],
        "rejected": rejected,
    }
    for kind in spec.sections:
        record[kind] = section(llm, spec, name, kind, verified, lead)
    return record


# ---- her review and what the site shows ---------------------------------------------


def wiki_source(source_id: str, entry: dict[str, Any], section: str | None = None) -> Source:
    """The English Wikipedia lead an item cites (or ``section`` of it), at its revision."""
    part = f", sección «{section}»" if section else ""
    label = f"Wikipedia en inglés: «{entry['title']}»{part} (revisión {entry['revid']})"
    return Source(id=source_id, url=entry["url"], label=label)


def section_item(item_type: ItemType, item_id: str, title_es: str, sec: dict[str, Any],
                 src: Source) -> ReviewItem:  # fmt: skip
    """Her review item for one drafted section, every sentence citing the lead."""
    lines = {lang: [Sentence(text=s["text"], cites=[src.id]) for s in sec[lang]]
             for lang in ("es", "en")}  # fmt: skip
    content = TextContent(es=lines["es"], en=lines["en"], sources=[src])
    return ReviewItem(item_type=item_type, item_id=item_id, title_es=title_es, content=content)


def published(items: list[ReviewItem], review_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Item id -> what the site shows: only what she approved or corrected, at the version
    on the table today (the hash). ``en`` is None while her Spanish-only correction waits
    for its English."""
    from synaptica.review.apply import read_log, state

    if review_dir is None or not review_dir.exists():
        return {}
    events = read_log(review_dir)
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        st = state(item, events)
        if st.status not in PUBLISHED or st.reviewed_at is None:
            continue
        content = st.text or item.content
        assert isinstance(content, TextContent)
        text = {lang: " ".join(s.text for s in getattr(content, lang)) for lang in ("es", "en")}
        if st.awaiting_en:
            text["en"] = None
        src = item.content.sources[0]  # type: ignore[union-attr]
        out[item.item_id] = {
            **text, "mark": "kept" if st.kept_reason else st.status,
            "reviewed_at": st.reviewed_at.date().isoformat(),
            "source": {"url": src.url, "title": src.label.split("«")[1].split("»")[0]},
        }  # fmt: skip
    return out
