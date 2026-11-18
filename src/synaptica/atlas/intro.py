"""Neuro Atlas's introduction, «human and rat: how to read the pairs» (step 6 of the plan
of 2026-11-18; Aday: the LLM drafts it and Sofía corrects it in her queue; its three
sources, his choice of 2026-11-18, v221).

No Wikipedia article compares the two brains, so the facts come from three sections of
three English articles, each pinned to a revision (:data:`PINNED`). ``syn atlas
intro-sources`` stores their text in ``intro_sources.json``; ``syn atlas intro-write``
runs the shared chain (:mod:`synaptica.narrative.wikidraft`) on each section, with its
own fact ids (``a1``, ``b1``, ``c1``), writes one paragraph from them all, and every
sentence cites the sections of the facts it uses. Clinical facts are never written, as
in the region texts.

Nothing here is published: the draft goes to ``intro.json`` and from there to Sofía's
queue (``ItemType.ATLAS``, item ``intro``, first among the Atlas texts from 2026-11-25);
only her approval puts it on the Neuro Atlas page. By hand, never in the pipeline, and
the LLM only with Aday's OK.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from synaptica.http import Throttle
from synaptica.llm import LLM, LLMOutputError
from synaptica.narrative import wikidraft
from synaptica.review.models import ItemType, ReviewItem, Sentence, TextContent
from synaptica.store import utc_today
from synaptica.wiki import LICENCE, fetch_section, read_json, write_json

SOURCES = Path(__file__).with_name("intro_sources.json")
TEXTS = Path(__file__).with_name("intro.json")
ITEM_ID = "intro"
SECTION = "intro"
NAME = "The human brain and the rat brain"
TITLE_ES = "Humano y rata · Cómo leer las parejas"


@dataclass(frozen=True)
class Pinned:
    id: str
    title: str
    heading: str
    revid: int


# Measured in step 6a (2026-11-18): the three sections that compare the two brains.
PINNED = (
    Pinned("gyrification", "Gyrification", "Variation across species", 1369639458),
    Pinned("human-brain", "Human brain", "Comparative anatomy", 1386315509),
    Pinned("brain-size", "Brain size", "Other animals", 1385820400),
)


class IntroFact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the section")
    kind: Literal["comparison", "general", "clinical", "other"]


class IntroFacts(BaseModel):
    facts: list[IntroFact]


SPEC = wikidraft.Spec(
    subject="TOPIC", facts_prompt="intro_facts", write_prompt="intro_write_en",
    facts_schema=IntroFacts, sections={SECTION: "human and rat: how to read the pairs"},
    kinds={SECTION: ("comparison", "general")}, min_facts={SECTION: 3}, max_words=120,
)  # fmt: skip


def source_id(p: Pinned) -> str:
    return f"wikipedia-en-atlas-intro-{p.id}"


def update(
    client: httpx.Client, *, path: Path | None = None, throttle: Throttle | None = None
) -> tuple[int, list[str]]:
    """Store the text of each pinned section (kept when already stored at its revision).
    Returns how many were fetched and what failed."""
    path = path or SOURCES
    stored = read_json(path, "sections")
    throttle = throttle or Throttle(1)
    out: dict[str, Any] = {}
    fetched, failed = 0, []
    for p in PINNED:
        old = stored.get(p.id) or {}
        if old.get("revid") == p.revid and old.get("heading") == p.heading:
            out[p.id] = old
            continue
        text = fetch_section(client, "en", p.revid, p.heading, throttle)
        if not text:
            failed.append(f"{p.id}: no section «{p.heading}» in revision {p.revid}")
            continue
        out[p.id] = {"title": p.title, "heading": p.heading, "revid": p.revid,
                     "url": f"https://en.wikipedia.org/w/index.php?oldid={p.revid}",
                     "retrieved": utc_today().isoformat(), "text": text}  # fmt: skip
        fetched += 1
    write_json(path, {
        "note": "Sections of English Wikipedia the Neuro Atlas introduction is drafted from, "
        "each at a pinned revision. Written by `syn atlas intro-sources`; do not edit by hand.",
        "licence": LICENCE, "sections": out,
    })  # fmt: skip
    return fetched, failed


def _ready(sections: dict[str, Any]) -> bool:
    return all((sections.get(p.id) or {}).get("revid") == p.revid for p in PINNED)


def write(
    llm: LLM,
    *,
    redraft: bool = False,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Draft the introduction and return its status. Not asked again when already drafted
    from the same revisions (``redraft`` to ask anyway); ``missing_sources`` before
    ``syn atlas intro-sources``; ``model_error`` saves nothing."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sections = read_json(sources_path or SOURCES, "sections")
    if not _ready(sections):
        return "missing_sources"
    revids = {p.id: p.revid for p in PINNED}
    old = read_json(path, "intro")
    if old and old.get("revids") == revids and not redraft:
        return "unchanged"
    verified: list[dict[str, str]] = []
    rejected: list[str] = []
    try:
        for prefix, p in zip("abc", PINNED, strict=True):
            got, rej = wikidraft.facts(
                llm, SPEC, NAME, sections[p.id]["text"], prefix=prefix,
                header=f"SECTION «{p.heading}» OF THE ARTICLE «{p.title}»",
            )  # fmt: skip
            verified += [f | {"source": p.id} for f in got]
            rejected += rej
        joined = "\n\n".join(wikidraft.plain(sections[p.id]["text"]) for p in PINNED)
        sec = wikidraft.section(llm, SPEC, NAME, SECTION, verified, joined)
    except LLMOutputError:
        return "model_error"
    record = {
        "revids": revids, "generator": llm.label, "prompts": SPEC.prompts(),
        "generated_at": now.isoformat(timespec="seconds"),
        "facts": [{k: f[k] for k in ("id", "statement", "kind", "source")} for f in verified],
        "rejected": rejected, SECTION: sec,
    }  # fmt: skip
    write_json(path, {
        "note": "Draft of Neuro Atlas's introduction (LLM, checked against the sections in "
        "atlas/intro_sources.json). Not published: it waits for Sofía's approval. Written by "
        "`syn atlas intro-write`; do not edit by hand.",
        "intro": record,
    })  # fmt: skip
    return sec["status"]


# ---- her review and what the site shows ---------------------------------------------


def review_items(path: Path | None = None, sources_path: Path | None = None) -> list[ReviewItem]:
    """Her review item, when the draft passed and its sections are stored at the revisions
    it was drafted from; each sentence cites the sections of the facts it uses."""
    rec = read_json(path or TEXTS, "intro")
    sections = read_json(sources_path or SOURCES, "sections")
    if not rec or not _ready(sections) or rec.get("revids") != {p.id: p.revid for p in PINNED}:
        return []
    sec = rec.get(SECTION) or {}
    if sec.get("status") != "drafted":
        return []
    src = {p.id: wikidraft.wiki_source(source_id(p), sections[p.id], p.heading) for p in PINNED}
    of = {f["id"]: f["source"] for f in rec["facts"]}

    def cites(s: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(src[of[i]].id for i in s["fact_ids"]))

    lines = {lang: [Sentence(text=s["text"], cites=cites(s)) for s in sec[lang]]
             for lang in ("es", "en")}  # fmt: skip
    used = {c for s in lines["en"] + lines["es"] for c in s.cites}
    content = TextContent(es=lines["es"], en=lines["en"],
                          sources=[s for s in src.values() if s.id in used])  # fmt: skip
    return [ReviewItem(item_type=ItemType.ATLAS, item_id=ITEM_ID, title_es=TITLE_ES,
                       content=content)]  # fmt: skip


def source_texts(items: list[ReviewItem], sources_path: Path | None = None) -> dict[str, str]:
    """The section each source of her intro item cites, at its pinned revision (to check
    her edits: numbers, names, 8 copied words)."""
    sections = read_json(sources_path or SOURCES, "sections")
    by_id = {source_id(p): sections.get(p.id) or {} for p in PINNED}
    out = {}
    for item in items:
        if item.item_type is not ItemType.ATLAS or item.item_id != ITEM_ID:
            continue
        if not isinstance(item.content, TextContent):
            continue
        for s in item.content.sources:
            entry = by_id.get(s.id) or {}
            if entry.get("url") == s.url:
                out[s.id] = wikidraft.plain(entry["text"])
    return out


def published(
    review_dir: Path | None, path: Path | None = None, sources_path: Path | None = None
) -> dict[str, Any] | None:
    """What the Neuro Atlas page shows: only her approved or corrected text, with every
    section it cites; None until then."""
    items = review_items(path, sources_path)
    shown = wikidraft.published(items, review_dir).get(ITEM_ID)
    if shown is None:
        return None
    (item,) = items
    assert isinstance(item.content, TextContent)
    sources = [{"url": s.url, "title": s.label.split("«")[1].split("»")[0],
                "heading": s.label.split("«")[2].split("»")[0]}
               for s in item.content.sources]  # fmt: skip
    return {**shown, "sources": sources}
