"""Step 1 of a summary: verified facts from a study's abstract (plan, step 16).

Adapted from spike S5 ``spikes/s5/pipeline.py`` (``run_article``, part 1) and paleo-atlas
``src/paleo/narrative/facts.py`` (prompt version, hash of the sources, one file per
item). The model returns facts in its own words, each with a verbatim quote of the
abstract; :func:`synaptica.narrative.checks.check_fact` keeps only the facts whose quote
is in the abstract, whose numbers are in the quote and that do not copy the wording.

Where it goes: the statements are our own words and go to ``derived/facts/<study>.json``
(committed to the ``data`` branch, so a text can be traced to its facts). The quotes are
publisher text, so they stay in ``cache/narrative/quotes/<study>.json`` with the
abstracts; the writing step needs them for its checks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.narrative.checks import check_fact
from synaptica.store import _atomic_write

MIN_FACTS = 3  # fewer than this: no summary, the site keeps the fallback text


class Fact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the abstract")
    subject: Literal["humans", "animals", "cells_or_tissue", "computational", "other"]


class Extraction(BaseModel):
    facts: list[Fact]


def slug(study_id: str) -> str:
    """File name of a study: its DOI or ``pmid:…`` with anything unsafe as ``_``."""
    return re.sub(r"[^a-z0-9._-]+", "_", study_id.lower())


def facts_path(study_id: str, derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / "facts" / f"{slug(study_id)}.json"


def quotes_path(study_id: str, cache_root: Path | None = None) -> Path:
    root = cache_root if cache_root is not None else get_paths().cache
    return root / "narrative" / "quotes" / f"{slug(study_id)}.json"


def abstract_hash(abstract: str) -> str:
    return hashlib.sha256(abstract.encode()).hexdigest()[:16]


def load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def is_up_to_date(study_id: str, abstract: str, derived_root: Path | None = None) -> bool:
    """Facts already extracted from this abstract with the current prompt."""
    doc = load(facts_path(study_id, derived_root))
    return bool(
        doc
        and doc["abstract_hash"] == abstract_hash(abstract)
        and doc["prompt_version"] == prompt("extract_facts")[1]
    )


def extract_facts(
    llm: LLM,
    study: dict[str, Any],
    abstract: str,
    *,
    origin: str,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Ask for facts, keep the verified ones and save both files. ``status`` is ``ok``
    or ``too_few`` (fewer than :data:`MIN_FACTS` verified)."""
    system, version = prompt("extract_facts")
    answer = llm.complete_json(
        system, f"TITLE: {study['title']}\n\nABSTRACT:\n{abstract}", Extraction, max_tokens=2_000
    )
    facts, quotes, rejected = [], {}, []
    for fact in answer.facts:
        if reason := check_fact(fact.statement, fact.quote, abstract):
            rejected.append(reason.split(":")[0])  # never the copied run itself
            continue
        fid = f"f{len(facts) + 1}"
        facts.append({"id": fid, "statement": fact.statement.strip(), "subject": fact.subject})
        quotes[fid] = fact.quote
    doc = {
        "study_id": study["study_id"],
        "status": "ok" if len(facts) >= MIN_FACTS else "too_few",
        "abstract_from": origin,
        "abstract_hash": abstract_hash(abstract),
        "prompt_version": version,
        "generator": llm.label,
        "generated_at": (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds"),
        "facts": facts,
        "rejected": rejected,
    }
    for path, content in ((facts_path(study["study_id"], derived_root), doc),
                          (quotes_path(study["study_id"], cache_root), quotes)):  # fmt: skip
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(content, ensure_ascii=False, indent=1) + "\n")
    return doc
