"""Retractions, corrections and other editorial notices from Crossref.

Not a per-DOI lookup, as in paleo-atlas ``src/paleo/ingest/crossref.py``: SYNAPTICA has
~700 new studies a day, and a retraction can arrive years later, so asking about every
study again would grow without end. Instead, every day the step lists the *notices*
deposited in the last few days, in every discipline (``filter=update-type:<kind>``).
Each notice says which DOIs it updates (``update-to``); dbt joins them with the studies by
DOI (plan, steps 11 and 12), so a study published today is flagged whenever its retraction
appears, without asking about it again.

``from-update-date`` filters on the date the notice's metadata was last deposited (measured
on 2026-11-12: same totals as ``from-deposit-date``), not on the date of the retraction, so
a notice deposited late with an old date is still caught. Re-deposits of old notices
come back too; lines whose content did not change within the window are not written
again.

Limits: list queries 3 requests/s with ``mailto`` (``docs/fuentes.md``), cursor paging.
Measured on 2026-11-12 (one day): 826 notices of all kinds, 186 KB once trimmed, 37 s.

Known gap: retractions that Crossref only knows from Retraction Watch (``source:
retraction-watch``, with no notice deposited by the publisher) appear in the
``updated-by`` field of the retracted work, not as a notice, so this list misses them.
Covering them needs a per-DOI lookup for the studies the site keeps showing (Clásicos)
or the Retraction Watch dataset; left for later (plan, step 8).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL
from synaptica.http import Throttle, get_json
from synaptica.store import BatchStore, utc_today

WORKS = "https://api.crossref.org/works"
# Crossref update types that change how a study is shown (checked live on 2026-11-12).
KINDS = (
    "retraction", "partial_retraction", "withdrawal", "removal",
    "expression_of_concern", "correction", "erratum",
)  # fmt: skip
ROWS = 1000  # Crossref's maximum page size
SELECT = "DOI,type,update-to"
LOOKBACK_MARGIN = 2  # extra days of stored files read to skip unchanged notices


@dataclass(frozen=True)
class CrossrefResult:
    notices: dict[str, int]  # listed per kind
    new_versions: int


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("crossref", "notices", raw_root=raw_root)


def trim_notice(item: dict[str, Any]) -> dict[str, Any]:
    """The notice reduced to what the signals need; DOIs in lower case, as dbt joins."""
    return {
        "doi": item["DOI"].lower(),
        "updates": sorted(
            (
                {
                    "doi": u["DOI"].lower(),
                    "type": u.get("type"),
                    "source": u.get("source"),
                    "date": (u.get("updated") or {}).get("date-time", "")[:10] or None,
                }
                for u in item.get("update-to") or []
                if u.get("DOI")
            ),
            key=lambda u: (u["doi"], u["type"] or "", u["date"] or ""),
        ),
    }


def list_notices(
    client: httpx.Client, kind: str, since: dt.date, throttle: Throttle
) -> Iterator[dict[str, Any]]:
    """Every notice of ``kind`` deposited since ``since``, following the cursor."""
    cursor = "*"
    while True:
        throttle.wait()
        body = get_json(client, WORKS, params={
            "filter": f"update-type:{kind},from-update-date:{since.isoformat()}",
            "select": SELECT, "rows": ROWS, "cursor": cursor, "mailto": CONTACT_EMAIL,
        })  # fmt: skip
        message = body.get("message", {})
        items = message.get("items", [])
        yield from items
        cursor = message.get("next-cursor")
        if len(items) < ROWS or not cursor:  # a short page is the last one
            return


def ingest(
    client: httpx.Client,
    *,
    days: int = 3,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> CrossrefResult:
    """Store the notices of the last ``days`` days (overlapping runs, so a missed day is
    recovered). Idempotent: a rerun the same day writes nothing new."""
    today = today or utc_today()
    throttle = throttle or Throttle(3)
    notices = store(raw_root)
    since = today - dt.timedelta(days=days)
    counts: dict[str, int] = {}
    found: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        items = [i for i in list_notices(client, kind, since, throttle) if i.get("DOI")]
        counts[kind] = len(items)
        for item in items:
            found[item["DOI"].lower()] = trim_notice(item)
    previous = {k: e.payload for k, e in notices.recent(days + LOOKBACK_MARGIN, today).items()}
    return CrossrefResult(counts, notices.save(found, today, previous=previous))
