"""Drafts of Neuro Lab's texts, «what it lets us see» and «limits», for each technique
(B2-4, Aday's option A of v202; step 8 of the plan of 2026-11-17).

The chain and its checks live in :mod:`synaptica.narrative.wikidraft` (shared with Neuro
Atlas since v211): facts with quotes from the technique's Wikipedia lead
(:mod:`synaptica.lab.sources`), an English paragraph per section and its Spanish. A
section with too few verified facts, or whose text fails, is not written: the page keeps
its gap. Nothing here is published: the drafts go to ``texts.json`` next to this module
and from there to Sofía's queue; only her approval puts them on the site.

Since v214, a technique whose lead gave no «limits» facts and whose sources hold a
section on them (``limits_en``, :mod:`synaptica.lab.sources`) gets its «limits» written
from that section alone: its facts get ids ``l1``…, her card cites the section, and its
«what it lets us see» is not asked again (it is already in her queue).

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
from synaptica.llm import LLM, LLMOutputError
from synaptica.narrative import wikidraft
from synaptica.review.models import ItemType, ReviewItem, TextContent
from synaptica.wiki import read_json, write_json

TEXTS = Path(__file__).with_name("texts.json")
SECTIONS = ("what", "limit")


class LabFact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the lead")
    kind: Literal["what", "limit", "other"]


class LabFacts(BaseModel):
    facts: list[LabFact]


SPEC = wikidraft.Spec(
    subject="TECHNIQUE", facts_prompt="lab_facts", write_prompt="lab_write_en",
    facts_schema=LabFacts, sections={"what": "what it lets us see", "limit": "limits"},
    kinds={"what": ("what",), "limit": ("limit",)}, min_facts={"what": 2, "limit": 1},
)  # fmt: skip


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
        old, extra = texts.get(tid), _section(sources[tid])
        same = bool(old) and old.get("revid") == en_src["revid"]
        if same and extra and _wants_limits(old, extra):
            try:
                _draft_limits(llm, tech["name_en"], old, extra)
            except LLMOutputError:
                status[tid] = {"limit": "model_error"}
                continue
            old["limit"] |= {"generator": llm.label,
                             "generated_at": now.isoformat(timespec="seconds")}  # fmt: skip
            status[tid] = {"limit": old["limit"]["status"]}
            continue
        if same and not only:
            continue
        try:
            drafted = wikidraft.draft(llm, SPEC, tech["name_en"], en_src["lead"])
            if extra and _wants_limits(drafted, extra):
                _draft_limits(llm, tech["name_en"], drafted, extra)
        except LLMOutputError:  # nothing saved for it: asked again on the next run
            status[tid] = dict.fromkeys(SECTIONS, "model_error")
            continue
        texts[tid] = {"revid": en_src["revid"], "source": en_src["url"],
                      "source_es": ((sources[tid].get("es") or {}).get("url")),
                      "generator": llm.label, "prompts": SPEC.prompts(),
                      "generated_at": now.isoformat(timespec="seconds"), **drafted}  # fmt: skip
        status[tid] = {k: drafted[k]["status"] for k in SECTIONS}
    _save(path, texts)
    return status


def _save(path: Path, texts: dict[str, Any]) -> None:
    write_json(path, {
        "note": "Drafts of Neuro Lab's texts (LLM, checked against each technique's Wikipedia "
        "lead in lab/sources.json). Not published: each waits for Sofía's approval. Written "
        "by `syn lab write`; do not edit by hand.",
        "techniques": {t["id"]: texts[t["id"]] for t in techniques() if t["id"] in texts},
    })  # fmt: skip


def spanish_again(
    llm: LLM | None,
    *,
    only: list[str] | None = None,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, dict[str, str]]:
    """The sections whose English passed and whose Spanish failed (v223): checked again
    with today's checks, and with ``llm`` their Spanish asked again (1 or 2 calls each).
    Returns technique -> section -> status."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sources = read_json(sources_path or SOURCES, "techniques")
    texts = read_json(path, "techniques")
    status: dict[str, dict[str, str]] = {}
    for tech in techniques():
        tid, rec = tech["id"], texts.get(tech["id"])
        en_src = (sources.get(tid) or {}).get("en") or {}
        if (only and tid not in only) or not rec or rec.get("revid") != en_src.get("revid"):
            continue
        for key in SECTIONS:
            sec = rec.get(key) or {}
            if sec.get("status") != "failed_es":
                continue
            try:
                new = wikidraft.retry_es(llm, sec)
            except LLMOutputError:
                status.setdefault(tid, {})[key] = "model_error"
                continue
            if new.get("es") != sec.get("es") and llm is not None:
                new |= {"es_generator": llm.label,
                        "es_generated_at": now.isoformat(timespec="seconds")}  # fmt: skip
            rec[key] = {k: v for k, v in sec.items() if k not in new and k not in
                        ("problems", "es")} | new  # fmt: skip
            status.setdefault(tid, {})[key] = new["status"]
    _save(path, texts)
    return status


def english_again(
    llm: LLM,
    *,
    only: list[str] | None = None,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, dict[str, str]]:
    """The sections whose English failed (v232), asked again alone with today's prompts:
    the other section of the technique is not touched (it may be in her queue, and its
    hash must not change). Its facts are taken again from the same source, with ids of
    their own (``r1``…), because the stored facts keep no quote, and without the quote the
    checks could not see a caution («potentially») that the statement left out. Returns
    technique -> section -> status."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sources = read_json(sources_path or SOURCES, "techniques")
    texts = read_json(path, "techniques")
    status: dict[str, dict[str, str]] = {}
    for tech in techniques():
        tid, rec = tech["id"], texts.get(tech["id"])
        en_src = (sources.get(tid) or {}).get("en") or {}
        if (only and tid not in only) or not rec or rec.get("revid") != en_src.get("revid"):
            continue
        failed = [k for k in SECTIONS if (rec.get(k) or {}).get("status") == "failed_en"]
        for key in failed:
            extra = _section(sources[tid]) if rec[key].get("section") else None
            source = extra["text"] if extra else en_src["lead"]
            header = f"SECTION «{extra['heading']}» OF THE ARTICLE" if extra else "LEAD"
            try:
                verified, rejected = wikidraft.facts(llm, SPEC, tech["name_en"], source,
                                                     prefix="r", header=header)  # fmt: skip
                sec = wikidraft.section(llm, SPEC, tech["name_en"], key, verified,
                                        wikidraft.plain(source))  # fmt: skip
            except LLMOutputError:
                status.setdefault(tid, {})[key] = "model_error"
                continue
            rec["facts"] = [f for f in rec["facts"] if not f["id"].startswith("r")] + [
                {k: f[k] for k in ("id", "statement", "kind")} for f in verified]  # fmt: skip
            rec["rejected_again"] = rejected
            rec[key] = sec | ({"section": extra["heading"]} if extra else {}) | {
                "prompts": SPEC.prompts(), "generator": llm.label,
                "generated_at": now.isoformat(timespec="seconds")}  # fmt: skip
            status.setdefault(tid, {})[key] = sec["status"]
    _save(path, texts)
    return status


def _section(entry: dict[str, Any]) -> dict[str, Any] | None:
    """The stored «limits» section, only at the revision of the English lead."""
    extra, en = entry.get("limits_en"), entry.get("en") or {}
    return extra if extra and extra.get("revid") == en.get("revid") else None


def _wants_limits(rec: dict[str, Any], extra: dict[str, Any]) -> bool:
    """The lead gave no «limits» and this section was not tried yet (a section that failed
    is not asked again on every run: it would cost quota for the same answer)."""
    limit = rec.get("limit") or {}
    return limit.get("status") == "too_few_facts" and limit.get("section") != extra["heading"]


def _draft_limits(llm: LLM, name: str, rec: dict[str, Any], extra: dict[str, Any]) -> None:
    """«Limits» from the section alone (its facts ``l1``…), into ``rec``."""
    header = f"SECTION «{extra['heading']}» OF THE ARTICLE"
    verified, rejected = wikidraft.facts(llm, SPEC, name, extra["text"], prefix="l",
                                         header=header)  # fmt: skip
    sec = wikidraft.section(llm, SPEC, name, "limit", verified, wikidraft.plain(extra["text"]))
    rec["facts"] = [f for f in rec["facts"] if not f["id"].startswith("l")] + [
        {k: f[k] for k in ("id", "statement", "kind")} for f in verified]  # fmt: skip
    rec["rejected_limits"] = rejected
    rec["limit"] = sec | {"section": extra["heading"]}


# ---- her review and what the site shows (B2-4, v210) ---------------------------------

SECTION_ES = {"what": "Qué permite ver", "limit": "Límites"}


def review_items(path: Path | None = None, sources_path: Path | None = None) -> list[ReviewItem]:
    """Her review items: one per drafted section, in the order of the technique table.
    A draft from an older revision of its lead than ``sources.json`` holds is left out
    (its quotes would no longer be checkable) until ``syn lab write`` drafts it again."""
    texts = read_json(path or TEXTS, "techniques")
    sources = read_json(sources_path or SOURCES, "techniques")
    out = []
    for tech in techniques():
        tid = tech["id"]
        rec, entry = texts.get(tid), (sources.get(tid) or {}).get("en") or {}
        if not rec or not entry.get("accepted") or entry.get("revid") != rec.get("revid"):
            continue
        for kind in SECTIONS:
            sec = rec.get(kind) or {}
            if sec.get("status") != "drafted":
                continue
            src = wikidraft.wiki_source(f"wikipedia-en-lab-{tid}", entry, entry.get("section"))
            if heading := sec.get("section"):  # from a section: only while it is stored
                extra = _section(sources[tid])
                if not extra or extra["heading"] != heading:
                    continue
                src = wikidraft.wiki_source(f"wikipedia-en-lab-{tid}-limits", entry, heading)
            out.append(wikidraft.section_item(
                ItemType.LAB, f"{tid}-{kind}", f"{tech['name_es']} · {SECTION_ES[kind]}",
                sec, src))  # fmt: skip
    return out


def source_texts(items: list[ReviewItem], sources_path: Path | None = None) -> dict[str, str]:
    """The lead (or section) each Neuro Lab item cites, only at the revision it cites (to
    check her edits: numbers, names, 8 copied words)."""
    sources = read_json(sources_path or SOURCES, "techniques")
    out = {}
    for item in items:
        if item.item_type is not ItemType.LAB or not isinstance(item.content, TextContent):
            continue
        tid = item.item_id.rsplit("-", 1)[0]
        entry = (sources.get(tid) or {}).get("en") or {}
        extra = _section(sources.get(tid) or {})
        for s in item.content.sources:
            if not entry.get("accepted") or entry.get("url") != s.url:
                continue
            if s.id.endswith("-limits"):
                if extra:
                    out[s.id] = wikidraft.plain(extra["text"])
            else:
                out[s.id] = wikidraft.plain(entry["lead"])
    return out


def published(
    review_dir: Path | None, path: Path | None = None, sources_path: Path | None = None
) -> dict[str, dict[str, dict[str, Any]]]:
    """Technique -> section -> what the site shows (:func:`wikidraft.published`)."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    shown = wikidraft.published(review_items(path, sources_path), review_dir)
    for item_id, text in shown.items():
        tid, kind = item_id.rsplit("-", 1)
        out.setdefault(tid, {})[kind] = text
    return out
