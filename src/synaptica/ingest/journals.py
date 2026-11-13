"""Nature, Science, Cell and sister journals: metadata and links only.

The journals come from the seed ``dbt/seeds/journals.csv`` (key, name, ``scope`` —
``general`` journals need the neuroscience filter of step 13, ``neuro`` ones do not —,
RSS feed and the ISSN Crossref indexes: the print one for Cell Press, as S1 found).

From each feed only the title, authors, date, DOI, section and link are kept
(CLAUDE.md: "De Nature, Science y Cell solo se usan metadatos y enlaces"); the feed's
description is publisher text and is dropped, and the article pages are never
downloaded. If a feed fails or comes back empty, the same fields are listed from
Crossref by ISSN for the last :data:`FALLBACK_DAYS` days (``via: crossref``), as S1
measured as fallback (``spikes/s1/journals.py``, ``docs/fuentes.md``).

Feeds list the same items for days or weeks (Cell's is the current issue), so items are
keyed by DOI in a daily batch (``raw/journals/items/<date>.jsonl``) and compared with the
last :data:`LOOKBACK_DAYS` days: only new or changed items are written.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL, project_root
from synaptica.http import HttpError, Throttle, get_json, get_text
from synaptica.ingest.feeds import item_key, parse_feed
from synaptica.store import BatchStore, utc_today

log = logging.getLogger(__name__)

CROSSREF = "https://api.crossref.org/journals/{issn}/works"
FALLBACK_DAYS = 14
LOOKBACK_DAYS = 90  # longer than any item stays in a feed
CROSSREF_SELECT = "DOI,title,author,type,published,URL"


@dataclass(frozen=True)
class Journal:
    journal: str
    name: str
    scope: str  # general | neuro
    rss: str
    issn: str


@dataclass
class JournalsResult:
    items: dict[str, int] = field(default_factory=dict)  # per journal
    via_crossref: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    new_versions: int = 0


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("journals", "items", raw_root=raw_root)


def load_journals(seed: Path | None = None) -> list[Journal]:
    path = seed or project_root() / "dbt" / "seeds" / "journals.csv"
    with path.open(encoding="utf-8") as f:
        return [
            Journal(r["journal"], r["name"], r["scope"], r["rss"], r["issn"])
            for r in csv.DictReader(f)
        ]


def _key(item: dict[str, Any]) -> str:
    return item["doi"] or f"url:{item_key(item['url'])}"


def from_rss(client: httpx.Client, journal: Journal) -> list[dict[str, Any]]:
    items = parse_feed(get_text(client, journal.rss, retries=2))  # never the summary
    return [{**i, "journal": journal.journal, "via": "rss"} for i in items]


def _crossref_date(parts: dict[str, Any] | None) -> str | None:
    date = ((parts or {}).get("date-parts") or [[]])[0]
    if not date or date[0] is None:
        return None
    y, m, d = [*date, 1, 1][:3]
    return f"{y:04d}-{m:02d}-{d:02d}T00:00:00Z"


def from_crossref(client: httpx.Client, journal: Journal, today: dt.date) -> list[dict[str, Any]]:
    since = today - dt.timedelta(days=FALLBACK_DAYS)
    body = get_json(client, CROSSREF.format(issn=journal.issn), params={
        "filter": f"from-pub-date:{since}", "select": CROSSREF_SELECT, "rows": 1000,
        "mailto": CONTACT_EMAIL,
    })  # fmt: skip
    out = []
    for w in body.get("message", {}).get("items", []):
        if not w.get("DOI"):
            continue
        out.append({
            "url": w.get("URL") or f"https://doi.org/{w['DOI']}",
            "title": " ".join(" ".join(w.get("title") or []).split()),
            "published": _crossref_date(w.get("published")),
            "doi": w["DOI"].lower(),
            "authors": [" ".join(p for p in (a.get("given"), a.get("family")) if p)
                        for a in w.get("author") or [] if a.get("family")],
            "section": w.get("type"),
            "journal": journal.journal,
            "via": "crossref",
        })  # fmt: skip
    return [i for i in out if i["title"]]


def ingest(
    client: httpx.Client,
    journals: list[Journal] | None = None,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> JournalsResult:
    """Every item of every journal feed (or its Crossref fallback). A journal whose feed
    and fallback both fail is logged and skipped, so one publisher never stops the run.
    Idempotent: a rerun writes nothing new."""
    today = today or utc_today()
    throttle = throttle or Throttle(1)
    journals = journals if journals is not None else load_journals()
    result, found = JournalsResult(), {}
    for journal in journals:
        items: list[dict[str, Any]] = []
        try:
            throttle.wait()
            items = from_rss(client, journal)
        except (HttpError, httpx.HTTPError, ET.ParseError) as exc:
            log.warning("Feed of %s failed: %s", journal.journal, exc)
        if not items:
            try:
                throttle.wait()
                items = from_crossref(client, journal, today)
                result.via_crossref.append(journal.journal)
            except (HttpError, httpx.HTTPError) as exc:
                log.warning("Crossref fallback for %s failed: %s", journal.journal, exc)
                result.failed.append(journal.journal)
                continue
        result.items[journal.journal] = len(items)
        for item in items:
            found.setdefault(_key(item), item)  # first journal wins if a DOI repeats
    batches = store(raw_root)
    previous = {k: e.payload for k, e in batches.recent(LOOKBACK_DAYS, today).items()}
    result.new_versions = batches.save(found, today, previous=previous)
    return result


def has_new_items(
    client: httpx.Client,
    journals: list[Journal] | None = None,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
) -> bool:
    """Cheap change detection for ``syn check``: one request per feed; True if any item
    is not stored yet. A failing feed is skipped (the ingestion has the fallback); if
    every feed fails, the error propagates (``syn check`` exits 2)."""
    today = today or utc_today()
    journals = journals if journals is not None else load_journals()
    stored = store(raw_root).recent(LOOKBACK_DAYS, today)
    errors = []
    for journal in journals:
        try:
            items = from_rss(client, journal)
        except (HttpError, httpx.HTTPError, ET.ParseError) as exc:
            errors.append(exc)
            continue
        if any(_key(i) not in stored for i in items):
            return True
    if errors and len(errors) == len(journals):
        raise HttpError(f"every journal feed failed: {errors[0]}")
    return False
