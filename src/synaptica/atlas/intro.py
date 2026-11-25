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

**More differences** (:data:`MORE`, v248). Sofía asked for a wider comparison that does not
push the 3D brain off the first screen (sheet rows 11 and 15). A second text, drafted the
same way from four more pinned sections (one per subject she listed that Wikipedia
compares: new neurons, rodents as models, the neocortex, the whiskers), shown in a fold
below the brains; its own card (``intro-more``), so the short introduction already in her
queue keeps its hash. Each part has its own sections, fact ids, prompts and key in
``intro.json``.
"""

from __future__ import annotations

import datetime as dt
import json
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
from synaptica.wiki import LICENCE, fetch_section, write_json

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
# v248, read on 2026-11-25: one section per subject of hers that compares human and rodent.
PINNED_MORE = (
    Pinned("neurogenesis", "Adult neurogenesis", "Rodents", 1384312363),
    Pinned("animal-model", "Animal model", "Challenges and criticisms", 1385166639),
    Pinned("neocortex", "Neocortex", "Evolution", 1381668011),
    Pinned("whiskers", "Whiskers", "Neuroscience", 1385846757),
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


SPEC_MORE = wikidraft.Spec(
    subject="TOPIC", facts_prompt="intro_more_facts", write_prompt="intro_more_write_en",
    facts_schema=IntroFacts, sections={"more": "more differences between the two brains"},
    # Comparisons only (v248, after the first draft): «general» facts (oxidative stress of
    # new neurons, why the neocortex grew) made sentences that compare nothing.
    kinds={"more": ("comparison",)}, min_facts={"more": 4}, max_words=160,
)  # fmt: skip


@dataclass(frozen=True)
class Part:
    key: str  # its section in SPEC and its key in intro.json
    item_id: str
    title_es: str
    pinned: tuple[Pinned, ...]
    spec: wikidraft.Spec
    prefixes: str  # fact ids per section: a1…, b1…


INTRO = Part(SECTION, ITEM_ID, TITLE_ES, PINNED, SPEC, "abc")
MORE = Part("more", "intro-more", "Humano y rata · Más diferencias", PINNED_MORE, SPEC_MORE,
            "defg")  # fmt: skip
PARTS = (INTRO, MORE)


def read_json(path: Path, key: str) -> dict[str, Any]:
    """``key`` of a JSON file, {} when the file or the key is not there yet (an
    ``intro.json`` from before «more differences»)."""
    return json.loads(path.read_text("utf-8")).get(key, {}) if path.exists() else {}


def source_id(p: Pinned) -> str:
    return f"wikipedia-en-atlas-intro-{p.id}"


def update(
    client: httpx.Client,
    *,
    path: Path | None = None,
    throttle: Throttle | None = None,
    part: Part = INTRO,
) -> tuple[int, list[str]]:
    """Store the text of each pinned section of ``part`` (kept when already stored at its
    revision; the other part's sections are left as they are). Returns how many were
    fetched and what failed."""
    path = path or SOURCES
    stored = read_json(path, "sections")
    throttle = throttle or Throttle(1)
    mine = {p.id for p in part.pinned}
    out: dict[str, Any] = {k: v for k, v in stored.items() if k not in mine}
    fetched, failed = 0, []
    for p in part.pinned:
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


def _ready(sections: dict[str, Any], part: Part = INTRO) -> bool:
    return all((sections.get(p.id) or {}).get("revid") == p.revid for p in part.pinned)


def write(
    llm: LLM,
    *,
    redraft: bool = False,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
    part: Part = INTRO,
) -> str:
    """Draft the introduction (or ``part``) and return its status. Not asked again when
    already drafted from the same revisions (``redraft`` to ask anyway); ``missing_sources`` before
    ``syn atlas intro-sources``; ``model_error`` saves nothing."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sections = read_json(sources_path or SOURCES, "sections")
    if not _ready(sections, part):
        return "missing_sources"
    revids = {p.id: p.revid for p in part.pinned}
    old = read_json(path, part.key)
    if old and old.get("revids") == revids and not redraft:
        return "unchanged"
    verified: list[dict[str, str]] = []
    rejected: list[str] = []
    try:
        for prefix, p in zip(part.prefixes, part.pinned, strict=True):
            got, rej = wikidraft.facts(
                llm, part.spec, NAME, sections[p.id]["text"], prefix=prefix,
                header=f"SECTION «{p.heading}» OF THE ARTICLE «{p.title}»",
            )  # fmt: skip
            verified += [f | {"source": p.id} for f in got]
            rejected += rej
        joined = "\n\n".join(wikidraft.plain(sections[p.id]["text"]) for p in part.pinned)
        sec = wikidraft.section(llm, part.spec, NAME, part.key, verified, joined)
    except LLMOutputError:
        return "model_error"
    record = {
        "revids": revids, "generator": llm.label, "prompts": part.spec.prompts(),
        "generated_at": now.isoformat(timespec="seconds"),
        "facts": [{k: f[k] for k in ("id", "statement", "kind", "source")} for f in verified],
        "rejected": rejected, part.key: sec,
    }  # fmt: skip
    records = {q.key: read_json(path, q.key) for q in PARTS} | {part.key: record}
    write_json(path, {
        "note": "Draft of Neuro Atlas's introduction (LLM, checked against the sections in "
        "atlas/intro_sources.json). Not published: it waits for Sofía's approval. Written by "
        "`syn atlas intro-write`; do not edit by hand.",
        **{k: v for k, v in records.items() if v},  # the other part kept as it is
    })  # fmt: skip
    return sec["status"]


# ---- her review and what the site shows ---------------------------------------------


def review_items(path: Path | None = None, sources_path: Path | None = None) -> list[ReviewItem]:
    """Her review items (the introduction, then «more differences»), each when its draft
    passed and its sections are stored at the revisions it was drafted from; each sentence
    cites the sections of the facts it uses."""
    return [i for part in PARTS if (i := _item(part, path, sources_path)) is not None]


def _item(part: Part, path: Path | None, sources_path: Path | None) -> ReviewItem | None:
    rec = read_json(path or TEXTS, part.key)
    sections = read_json(sources_path or SOURCES, "sections")
    revids = {p.id: p.revid for p in part.pinned}
    if not rec or not _ready(sections, part) or rec.get("revids") != revids:
        return None
    sec = rec.get(part.key) or {}
    if sec.get("status") != "drafted":
        return None
    src = {p.id: wikidraft.wiki_source(source_id(p), sections[p.id], p.heading)
           for p in part.pinned}  # fmt: skip
    of = {f["id"]: f["source"] for f in rec["facts"]}

    def cites(s: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(src[of[i]].id for i in s["fact_ids"]))

    lines = {lang: [Sentence(text=s["text"], cites=cites(s)) for s in sec[lang]]
             for lang in ("es", "en")}  # fmt: skip
    used = {c for s in lines["en"] + lines["es"] for c in s.cites}
    content = TextContent(es=lines["es"], en=lines["en"],
                          sources=[s for s in src.values() if s.id in used])  # fmt: skip
    return ReviewItem(item_type=ItemType.ATLAS, item_id=part.item_id, title_es=part.title_es,
                      content=content)  # fmt: skip


def source_texts(items: list[ReviewItem], sources_path: Path | None = None) -> dict[str, str]:
    """The section each source of her intro item cites, at its pinned revision (to check
    her edits: numbers, names, 8 copied words)."""
    sections = read_json(sources_path or SOURCES, "sections")
    by_id = {source_id(p): sections.get(p.id) or {} for q in PARTS for p in q.pinned}
    out = {}
    for item in items:
        if item.item_type is not ItemType.ATLAS or item.item_id not in {q.item_id for q in PARTS}:
            continue
        if not isinstance(item.content, TextContent):
            continue
        for s in item.content.sources:
            entry = by_id.get(s.id) or {}
            if entry.get("url") == s.url:
                out[s.id] = wikidraft.plain(entry["text"])
    return out


def published(
    review_dir: Path | None,
    path: Path | None = None,
    sources_path: Path | None = None,
    part: Part = INTRO,
) -> dict[str, Any] | None:
    """What the Neuro Atlas page shows of ``part``: only her approved or corrected text,
    with every section it cites; None until then."""
    item = _item(part, path, sources_path)
    if item is None:
        return None
    shown = wikidraft.published([item], review_dir).get(part.item_id)
    if shown is None:
        return None
    assert isinstance(item.content, TextContent)
    sources = [{"url": s.url, "title": s.label.split("«")[1].split("»")[0],
                "heading": s.label.split("«")[2].split("»")[0]}
               for s in item.content.sources]  # fmt: skip
    return {**shown, "sources": sources}
