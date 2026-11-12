"""Is it neuroscience? The filter for the general sources (plan, step 13).

Neuro journals (Nature Neuroscience, Nature Reviews Neuroscience, Neuron) and neuro feeds
(ScienceDaily Neuroscience, The Conversation's neuroscience topics) are neuroscience by
their scope in the seeds, and so are the studies that come from neuro queries (PubMed,
Europe PMC, bioRxiv/medRxiv categories). What is left are the items of the **general**
sources: Nature, Science, Science Advances and Cell, and SINC's *Noticias*. For each one,
rules first and the LLM only when there is no data (Aday's decision, plan v53):

1. **OpenAlex** (by DOI): primary topic in the field Neuroscience (28) or the subfield
   Neurology (2728) → neuroscience.
2. **OpenAlex** knows the work and none of its topics is in those → not neuroscience.
3. Otherwise (no DOI, as in news; not in OpenAlex yet; or neuro only as a secondary
   topic) → the LLM, in batches of :data:`BATCH`, from the headline and the feed's
   summary when its licence lets us keep it. Without an LLM the item stays undecided and
   is not shown.

The plan also named MeSH. It is not a rule here, measured on 2026-11-12: we keep MeSH
descriptor IDs without their tree, so "nervous system" cannot be told from them, and
the stand-in "the DOI came in through our PubMed neuro query" was wrong in 4 of 6 items
(metamaterials, adipocytes, electronic hair: the query is broad on purpose, with words
such as "neural" and "synap*"). Those items go to the LLM instead.

Decisions go to ``derived/news/neuro.json`` (our own data, committed to the ``data``
branch like Paleo's ``derived/news/labels.json``), one row per item with its ``basis``.
Rule rows are recomputed every run; an LLM answer is kept while the item's input and the
prompt version do not change, so the CI never asks twice. Adapted from paleo-atlas
``src/paleo/news/classify.py`` (batches, input hash, prompt version).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synaptica.config import get_paths
from synaptica.ingest import journals, news, openalex
from synaptica.llm import LLM, prompt
from synaptica.store import _atomic_write, utc_today

BATCH = 20
LOOKBACK_DAYS = 90  # items still listed in the feeds
NEURO_FIELD = "28"
NEURO_SUBFIELDS = {"2728"}  # Neurology, inside Medicine


class ItemDecision(BaseModel):
    index: int
    neuro: bool


class BatchDecisions(BaseModel):
    items: list[ItemDecision]


@dataclass
class NeuroResult:
    items: int = 0
    by_basis: dict[str, int] | None = None
    llm_asked: int = 0
    undecided: int = 0


def decisions_path(derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / "news" / "neuro.json"


def load_decisions(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {row["key"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def save_decisions(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([rows[k] for k in sorted(rows)], ensure_ascii=False, indent=1)
    _atomic_write(path, text + "\n")


def general_items(today: dt.date, raw_root: Path | None) -> dict[str, dict[str, Any]]:
    """Key -> item of every general journal and general feed (``journals:`` / ``news:``)."""
    general_journals = {j.journal for j in journals.load_journals() if j.scope == "general"}
    general_feeds = {f.feed for f in news.load_feeds() if f.scope == "general"}
    out = {}
    for key, e in journals.store(raw_root).recent(LOOKBACK_DAYS, today).items():
        if e.payload.get("journal") in general_journals:
            out[f"journals:{key}"] = {**e.payload, "lang": "en"}
    for key, e in news.store(raw_root).recent(LOOKBACK_DAYS, today).items():
        if e.payload.get("feed") in general_feeds:
            out[f"news:{key}"] = e.payload
    return out


def rule(item: dict[str, Any], works: dict[str, dict[str, Any]]) -> tuple[bool, str] | None:
    """(is_neuro, basis) from the data, or None when only the LLM can tell."""
    doi = item.get("doi")
    work = works.get(doi) if doi else None
    primary = (work or {}).get("primary_topic") or {}
    if primary.get("field") == NEURO_FIELD or primary.get("subfield") in NEURO_SUBFIELDS:
        return True, "openalex"
    if (
        work
        and primary
        and not any(
            t.get("field") == NEURO_FIELD or t.get("subfield") in NEURO_SUBFIELDS
            for t in work.get("topics") or []
        )
    ):
        return False, "openalex"
    return None


def model_input(item: dict[str, Any]) -> str:
    """What the model sees of one item (and what its hash covers)."""
    text = item["title"]
    if item.get("section"):
        text = f"({item['section']}) {text}"
    if item.get("summary"):
        text += " — " + item["summary"]
    return text


def input_hash(item: dict[str, Any]) -> str:
    return hashlib.sha1(model_input(item).encode()).hexdigest()[:12]


def ask_batch(llm: LLM, system: str, batch: list[tuple[str, dict[str, Any]]]) -> dict[str, bool]:
    """Key -> the model's answer, for the items it answered."""
    lines = [f"{i}. [{item.get('lang', 'en')}] {model_input(item)}"
             for i, (_, item) in enumerate(batch, start=1)]  # fmt: skip
    answer = llm.complete_json(system, "ITEMS:\n" + "\n".join(lines), BatchDecisions,
                               max_tokens=1_500)  # fmt: skip
    by_index = {d.index: d.neuro for d in answer.items}
    return {key: by_index[i] for i, (key, _) in enumerate(batch, start=1) if i in by_index}


def decide(
    llm: LLM | None = None,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    derived_root: Path | None = None,
    limit: int | None = None,
    keys: Iterable[str] | None = None,
    now: dt.datetime | None = None,
) -> NeuroResult:
    """Decide every general item: rules, then the LLM for the rest (newest first when
    ``limit`` caps the calls). Idempotent: a rerun asks nothing already answered."""
    today = today or utc_today()
    items = general_items(today, raw_root)
    if keys is not None:
        items = {k: v for k, v in items.items() if k in set(keys)}
    recent_works = openalex.store(raw_root).recent(LOOKBACK_DAYS, today)
    works = {k: e.payload for k, e in recent_works.items()}
    path = decisions_path(derived_root)
    old = load_decisions(path)
    rows: dict[str, dict[str, Any]] = {}
    pending = []
    version = prompt("neuro_filter")[1]
    for key, item in items.items():
        if (decided := rule(item, works)) is not None:
            rows[key] = {"key": key, "is_neuro": decided[0], "basis": decided[1]}
            continue
        previous = old.get(key)
        if (
            previous and previous.get("basis") == "llm"
            and previous.get("input_hash") == input_hash(item)
            and previous.get("prompt_version") == version
        ):  # fmt: skip
            rows[key] = previous
        else:
            pending.append((key, item))
    result = NeuroResult(items=len(items))
    if llm is not None and pending:
        system = prompt("neuro_filter")[0]
        pending.sort(key=lambda kv: kv[1].get("published") or "", reverse=True)
        pending = pending[:limit] if limit is not None else pending
        stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
        for start in range(0, len(pending), BATCH):
            batch = pending[start : start + BATCH]
            for key, is_neuro in ask_batch(llm, system, batch).items():
                rows[key] = {
                    "key": key, "is_neuro": is_neuro, "basis": "llm",
                    "input_hash": input_hash(items[key]), "prompt_version": version,
                    "generator": llm.label, "decided_at": stamp,
                }  # fmt: skip
                result.llm_asked += 1
            save_decisions(path, {**old, **rows})  # keep progress if the quota runs out
    # Items that left the window keep their row (the warehouse still shows them).
    merged = {**{k: v for k, v in old.items() if k not in items}, **rows}
    save_decisions(path, merged)
    result.undecided = sum(1 for k in items if k not in rows)
    basis: dict[str, int] = {}
    for k in items:
        if k in rows:
            label = f"{rows[k]['basis']}:{'neuro' if rows[k]['is_neuro'] else 'not'}"
            basis[label] = basis.get(label, 0) + 1
    result.by_basis = dict(sorted(basis.items()))
    return result
