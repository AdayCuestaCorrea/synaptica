"""Drafts of Neuro Atlas's region texts, «what it is and what it does», one per rat ↔ human
pair (Aday's options of 2026-11-18, v212: one section; the chain shared with Neuro Lab).

The chain and its checks are :mod:`synaptica.narrative.wikidraft`, with the Wikipedia
lead of each pair in ``sources.json`` (:mod:`synaptica.atlas.sources`) as the source:
facts with quotes, an English paragraph and its Spanish. Facts of kind ``clinical`` are
never written: health content on the site goes only through Sofía's lists (the diseases of
each region wait for her, sheet row 16), and the site never speaks of treatments.

Nothing here is published: the drafts go to ``texts.json`` next to this module and from
there to Sofía's queue (``ItemType.ATLAS``, ``waxholm-<id>`` as her search-terms cards);
only her approval puts them on the region pages. By hand (``syn atlas write --provider
groq``), never in the daily pipeline, and only with Aday's OK for each run.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from synaptica.atlas.sources import SOURCES
from synaptica.llm import LLM, LLMOutputError
from synaptica.narrative import wikidraft
from synaptica.review.models import ItemType, ReviewItem, TextContent
from synaptica.wiki import read_json, write_json

TEXTS = Path(__file__).with_name("texts.json")
SECTION = "about"


class AtlasFact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the lead")
    kind: Literal["anatomy", "function", "clinical", "other"]


class AtlasFacts(BaseModel):
    facts: list[AtlasFact]


SPEC = wikidraft.Spec(
    subject="REGION", facts_prompt="atlas_facts", write_prompt="atlas_write_en",
    facts_schema=AtlasFacts, sections={SECTION: "what it is and what it does"},
    kinds={SECTION: ("anatomy", "function")}, min_facts={SECTION: 2},
)  # fmt: skip


def pairs() -> list[dict[str, Any]]:
    """The pairs of pairs.toml, in its order (the order of her queue)."""
    text = (resources.files("synaptica.atlas") / "pairs.toml").read_text("utf-8")
    return tomllib.loads(text)["pair"]


def item_id(pair: dict[str, Any]) -> str:
    return f"waxholm-{pair['waxholm']}"


def write(
    llm: LLM,
    *,
    only: list[str] | None = None,
    sources_path: Path | None = None,
    path: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, str]:
    """Draft the pairs with an accepted English lead (``only``: these kinds), keep the rest
    of ``texts.json`` and return pair kind -> status. A pair already drafted from the same
    revision is not asked again (it would cost quota)."""
    path = path or TEXTS
    now = now or dt.datetime.now(dt.UTC)
    sources = read_json(sources_path or SOURCES, "pairs")
    texts = read_json(path, "pairs")
    status: dict[str, str] = {}
    for pair in pairs():
        kind = pair["kind"]
        leads = (sources.get(kind) or {}).get("leads") or {}
        en_src = leads.get("en") or {}
        if (only and kind not in only) or not en_src.get("accepted"):
            continue
        old = texts.get(kind)
        if old and old.get("revid") == en_src["revid"] and not only:
            continue
        try:
            drafted = wikidraft.draft(llm, SPEC, en_src["title"], en_src["lead"])
        except LLMOutputError:  # nothing saved for it: asked again on the next run
            status[kind] = "model_error"
            continue
        texts[kind] = {"revid": en_src["revid"], "source": en_src["url"],
                       "source_es": (leads.get("es") or {}).get("url"),
                       "generator": llm.label, "prompts": SPEC.prompts(),
                       "generated_at": now.isoformat(timespec="seconds"), **drafted}  # fmt: skip
        status[kind] = drafted[SECTION]["status"]
    write_json(path, {
        "note": "Drafts of Neuro Atlas's region texts (LLM, checked against each pair's "
        "Wikipedia lead in atlas/sources.json). Not published: each waits for Sofía's "
        "approval. Written by `syn atlas write`; do not edit by hand.",
        "pairs": {p["kind"]: texts[p["kind"]] for p in pairs() if p["kind"] in texts},
    })  # fmt: skip
    return status


# ---- her review and what the site shows ---------------------------------------------


def _title_es(leads: dict[str, Any]) -> str:
    es = leads.get("es") or {}
    title = es["title"] if es.get("accepted") and es.get("title") else leads["en"]["title"]
    return re.sub(r"\s*\([^)]*\)$", "", title)  # «Hipocampo (anatomía)» -> «Hipocampo»


def review_items(path: Path | None = None, sources_path: Path | None = None) -> list[ReviewItem]:
    """Her review items: one per drafted pair, in the order of pairs.toml. A draft from an
    older revision of its lead than ``sources.json`` holds is left out (its quotes would no
    longer be checkable) until ``syn atlas write`` drafts it again."""
    texts = read_json(path or TEXTS, "pairs")
    sources = read_json(sources_path or SOURCES, "pairs")
    out = []
    for pair in pairs():
        kind = pair["kind"]
        rec = texts.get(kind)
        leads = (sources.get(kind) or {}).get("leads") or {}
        entry = leads.get("en") or {}
        if not rec or not entry.get("accepted") or entry.get("revid") != rec.get("revid"):
            continue
        sec = rec.get(SECTION) or {}
        if sec.get("status") != "drafted":
            continue
        src = wikidraft.wiki_source(f"wikipedia-en-atlas-{item_id(pair)}", entry)
        title = f"{_title_es(leads)} · Qué es y qué hace"
        out.append(wikidraft.section_item(ItemType.ATLAS, item_id(pair), title, sec, src))
    return out


def source_texts(items: list[ReviewItem], sources_path: Path | None = None) -> dict[str, str]:
    """The lead each Neuro Atlas text item cites, only at the revision it cites (to check
    her edits: numbers, names, 8 copied words)."""
    sources = read_json(sources_path or SOURCES, "pairs")
    kind_of = {item_id(p): p["kind"] for p in pairs()}
    out = {}
    for item in items:
        if item.item_type is not ItemType.ATLAS or not isinstance(item.content, TextContent):
            continue
        kind = kind_of.get(item.item_id)
        entry = ((sources.get(kind) or {}).get("leads") or {}).get("en") or {}
        for s in item.content.sources:
            if entry.get("accepted") and entry.get("url") == s.url:
                out[s.id] = wikidraft.plain(entry["lead"])
    return out


def published(
    review_dir: Path | None, path: Path | None = None, sources_path: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Pair kind -> what its region pages show (:func:`wikidraft.published`)."""
    kind_of = {item_id(p): p["kind"] for p in pairs()}
    shown = wikidraft.published(review_items(path, sources_path), review_dir)
    return {kind_of[i]: text for i, text in shown.items()}
