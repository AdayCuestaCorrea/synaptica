"""The weekly Clásicos: the proposal that goes to Sofía's queue, and what the site shows
(plan, step 24a; 24b is her approval through the review flow, ADR 0005).

**Proposal.** From the week's OpenAlex listing (:mod:`synaptica.ingest.classics`), the
:data:`PER_SUBFIELD` most cited works of each subfield that she has not picked before and
that were not proposed in the last :data:`REST_WEEKS` weeks, so the proposal moves on
instead of repeating itself. She picks up to :data:`MAX_PICKS`.

**On the site.** Nothing until she has chosen: the block shows the works of her newest
pick, with their title, year and citation count as OpenAlex gives them. A pick names
DOIs only; their metadata comes from the listings of the last weeks.

**Integrity (v148).** The Clásicos do not go through ``dim_study``, so they read their
signal from ``dim_integrity`` (Crossref and Retraction Watch, every DOI with a notice).
OpenAlex already leaves out what it knows to be retracted (``is_retracted:false``), but it
lags and says nothing of concerns or corrections. Rule (Aday, 2026-11-14): a retracted or
partially retracted work is never proposed; a concern or a correction is proposed with
its signal, and she decides; a work she picked that is retracted later stays on the site
with its signal. Without a warehouse there is no proposal: none goes out unchecked.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import duckdb

from synaptica.ingest import classics as listing
from synaptica.review.apply import read_log
from synaptica.review.models import (
    Action,
    Candidate,
    CandidatesContent,
    ItemType,
    Queue,
    ReviewItem,
)

PER_SUBFIELD = 2
MAX_PICKS = 5
REST_WEEKS = 4
NAMES = {sid: {"es": es, "en": en} for sid, es, en in listing.SUBFIELDS}
RETRACTED = frozenset({"retracted", "partially_retracted"})


def integrity(warehouse: Path, dois: list[str]) -> dict[str, dict[str, Any]]:
    """``dim_integrity`` rows of these DOIs (lower case, as dbt keys them); a DOI without
    notices is absent. A missing warehouse raises: nothing is shown or proposed unchecked."""
    if not warehouse.exists():
        raise FileNotFoundError(f"no warehouse at {warehouse}: run syn build first")
    with duckdb.connect(str(warehouse), read_only=True) as con:
        cur = con.execute(
            "select doi, integrity, integrity_notices, integrity_sources "
            "from main.dim_integrity where doi in (select unnest(?))",
            [sorted({d.lower() for d in dois})],
        )
        cols = [c[0] for c in cur.description]
        return {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}


def item_id(week: str) -> str:
    return f"classics-{week.lower()}"


def _picks(review_dir: Path) -> list[tuple[str, list[str]]]:
    """(item_id, DOIs) of each of her Clásicos picks, oldest first."""
    return [(e.decision.item_id, list(e.decision.payload.get("dois", [])))
            for e in read_log(review_dir)
            if e.decision.item_type is ItemType.CLASSICS and e.decision.action is Action.PICK
            and not e.held]  # fmt: skip


def _recently_proposed(review_dir: Path, today: dt.date) -> set[str]:
    out: set[str] = set()
    for path in review_dir.glob("queue-*.json"):
        try:
            day = dt.date.fromisoformat(path.stem.removeprefix("queue-"))
        except ValueError:
            continue
        if not (today - dt.timedelta(weeks=REST_WEEKS) <= day < today):
            continue
        queue = Queue.model_validate_json(path.read_text("utf-8"))
        for item in queue.items:
            if item.item_type is ItemType.CLASSICS and item.item_id != item_id(
                listing.iso_week(today)
            ):
                out |= {c.doi for c in item.content.candidates}
    return out


def proposal(
    raw_root: Path, review_dir: Path, today: dt.date, warehouse: Path
) -> ReviewItem | None:
    """This week's Clásicos item, or None without a listing of this week (or without a
    warehouse to check their notices in). Retracted works are left out."""
    week = listing.iso_week(today)
    rows = {k: v for k, v in listing.latest(raw_root, today).items() if v.get("week") == week}
    if not rows:
        return None
    left_out = {doi for _, dois in _picks(review_dir) for doi in dois}
    left_out |= _recently_proposed(review_dir, today)
    if not warehouse.exists():
        return None
    works = [w for r in rows.values() for w in r.get("works", [])]
    notices = integrity(warehouse, [w["doi"] for w in works])
    left_out |= {d for d, n in notices.items() if n["integrity"] in RETRACTED}
    candidates: list[Candidate] = []
    for sid, _, _ in listing.SUBFIELDS:
        fresh = [w for w in rows.get(sid, {}).get("works", []) if w["doi"] not in left_out]
        for w in fresh[:PER_SUBFIELD]:
            n = notices.get(w["doi"], {})
            candidates.append(Candidate(
                doi=w["doi"], title=w["title"], year=w["year"], cited_by=w["cited_by"],
                integrity=n.get("integrity", "none"),
                integrity_notices=n.get("integrity_notices") or [],
            ))  # fmt: skip
    if not candidates:
        return None
    return ReviewItem(
        item_type=ItemType.CLASSICS,
        item_id=item_id(week),
        title_es=f"Clásicos de la semana {week}",
        content=CandidatesContent(week=week, max_picks=MAX_PICKS, candidates=candidates),
    )


def approved(
    raw_root: Path, review_dir: Path, today: dt.date, warehouse: Path
) -> list[dict[str, Any]]:
    """The works of her newest pick, most cited first, with their subfield and their
    integrity signal; [] until she has chosen. A DOI whose metadata is no longer in the
    listings is left out."""
    picks = _picks(review_dir)
    if not picks:
        return []
    chosen = picks[-1][1]
    meta = listing.works_by_doi(raw_root, today)
    notices = integrity(warehouse, [d for d in chosen if d in meta])
    works = [{**meta[d], "subfield": NAMES.get(meta[d]["subfield_id"]),
              "integrity": notices.get(d, {}).get("integrity", "none"),
              "integrity_notices": notices.get(d, {}).get("integrity_notices") or [],
              "integrity_sources": notices.get(d, {}).get("integrity_sources") or []}
             for d in dict.fromkeys(chosen) if d in meta]  # fmt: skip
    return sorted(works, key=lambda w: (-w["cited_by"], w["doi"]))
