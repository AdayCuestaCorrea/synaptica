"""OpenAlex by DOI: topics and citation counts.

Two uses downstream: the topic of each work feeds the "is it neuroscience?" filter for the
general journals (plan, step 13: Nature, Science, Science Advances and Cell publish every
field; OpenAlex classifies each work into a field, 28 being Neuroscience), and its
citation count is the input for the weekly Clásicos proposal (step 24a, which lists the
most cited works with ``filter`` + ``sort``, as spike S1 measured in
``spikes/s1/signals.py``).

This step looks up, by DOI, the items of the ``general`` journals first stored in the
last :data:`LOOKBACK_DAYS` days, 50 DOIs per request with ``filter=doi:a|b|…`` (never
``search``, which costs 10 times more). A DOI OpenAlex does not know yet (new works take
some days) is asked again on later runs until the item is :data:`LOOKBACK_DAYS` days old.
Results go to a daily batch ``raw/openalex/works/<date>.jsonl``, keyed by DOI. A DOI
is looked up once: the citation count stored here is the one at that moment, and the
up-to-date counts for the Clásicos come from the step 24a listing.

Limits (``docs/fuentes.md``): without a key, 10 requests/s and a daily budget of ~1000
list queries shared by the IP. Not in Paleo Atlas.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL
from synaptica.http import Throttle, get_json
from synaptica.ingest import journals
from synaptica.store import BatchStore, utc_today

WORKS = "https://api.openalex.org/works"
BATCH = 50
LOOKBACK_DAYS = 30
SELECT = "id,doi,type,publication_year,cited_by_count,primary_topic,topics,is_retracted"


@dataclass(frozen=True)
class OpenAlexResult:
    asked: int
    found: int
    new_versions: int


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("openalex", "works", raw_root=raw_root)


def _id(url: str | None) -> str | None:
    return url.rsplit("/", 1)[-1] if url else None


def _topic(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _id(t.get("id")),
        "name": t.get("display_name"),
        "score": t.get("score"),
        "subfield": _id((t.get("subfield") or {}).get("id")),
        "field": _id((t.get("field") or {}).get("id")),
        "field_name": (t.get("field") or {}).get("display_name"),
    }


def trim_work(work: dict[str, Any]) -> dict[str, Any]:
    primary = work.get("primary_topic")
    return {
        "doi": (work.get("doi") or "").removeprefix("https://doi.org/").lower(),
        "openalex_id": _id(work.get("id")),
        "type": work.get("type"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "is_retracted": work.get("is_retracted"),
        "primary_topic": _topic(primary) if primary else None,
        "topics": [_topic(t) for t in work.get("topics") or []],
    }


def lookup(
    client: httpx.Client, dois: Iterable[str], throttle: Throttle
) -> dict[str, dict[str, Any]]:
    """Trimmed works by DOI (lower case); DOIs OpenAlex does not know are left out."""
    dois = sorted(set(dois))
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(dois), BATCH):
        batch = dois[start : start + BATCH]
        throttle.wait()
        body = get_json(client, WORKS, params={
            "filter": "doi:" + "|".join(batch), "select": SELECT, "per_page": BATCH,
            "mailto": CONTACT_EMAIL,
        })  # fmt: skip
        for work in body.get("results") or []:
            trimmed = trim_work(work)
            if trimmed["doi"]:
                out[trimmed["doi"]] = trimmed
    return out


def due_dois(today: dt.date, raw_root: Path | None = None) -> list[str]:
    """DOIs of general-journal items seen in the last :data:`LOOKBACK_DAYS` days that
    are not stored yet."""
    general = {j.journal for j in journals.load_journals() if j.scope == "general"}
    items = journals.store(raw_root).recent(LOOKBACK_DAYS, today)
    stored = store(raw_root).recent(LOOKBACK_DAYS, today)
    return sorted({
        e.payload["doi"] for e in items.values()
        if e.payload.get("journal") in general and e.payload.get("doi")
        and e.payload["doi"] not in stored
    })  # fmt: skip


def ingest(
    client: httpx.Client,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> OpenAlexResult:
    """Look up the due DOIs and store what changed. Idempotent: a rerun the same day
    asks only for DOIs OpenAlex did not know and writes nothing new."""
    today = today or utc_today()
    throttle = throttle or Throttle(5)
    dois = due_dois(today, raw_root)
    found = lookup(client, dois, throttle)
    works = store(raw_root)
    return OpenAlexResult(len(dois), len(found), works.save(found, today))
