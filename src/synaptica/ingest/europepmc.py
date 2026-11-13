"""Open-access neuroscience articles from Europe PMC: metadata, licence and full text.

Europe PMC is here for the full text of open-access articles (SCOPE §5: richer summaries),
not as another list of studies: PubMed already brings the metadata. So the step asks only
for open-access records (``OPEN_ACCESS:y``) that entered Europe PMC in the last ``days``
days (``FIRST_IDATE``, the index date, like PubMed's ``edat``: an article published weeks
ago but indexed today is still caught). Same title/abstract words as spike S1
(``spikes/s1/europepmc.py``).

- Metadata, trimmed to what the pipeline uses (IDs, journal, dates, types, licence, MeSH
  names), go to daily batch files ``raw/europepmc/records/<date>.jsonl``
  (:class:`synaptica.store.BatchStore`; S1 measured ~190 open-access records a week, but
  Europe PMC also lists preprints and non-MEDLINE sources, so the volume is checked live).
- The full text (``/{PMCID}/fullTextXML``) is article text under each article's licence:
  it goes only to the local cache ``data/cache/europepmc/fulltext/<PMCID>.xml``, never to
  the ``data`` branch (CLAUDE.md, "Licencias"). It is **not** fetched here but on demand
  (:func:`fetch_fulltext`), by the summary step, for the studies it is about to summarise.
  Measured on 2026-11-12: 289 open-access records in one day (250 also in PubMed, 39 from
  PMC only), 244 KB of metadata in a few seconds, but 10-26 s per full text and some over
  30 s: ~70 min a day for texts that would mostly never be summarised (Groq allows ~40-60
  summaries a day). Aday's decision, 2026-11-12: on demand.

Limits: 10 requests/s or 500/min per IP (Europe PMC team, ``docs/fuentes.md``); we stay at
5/s. Not in Paleo Atlas, which has no Europe PMC step; the shape follows
:mod:`synaptica.ingest.crossref`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL, get_paths
from synaptica.http import HttpError, Throttle, get_json, get_text
from synaptica.store import BatchStore, _atomic_write, utc_today

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
TERMS = "TITLE_ABS:(brain OR neuron* OR neural OR cortex OR synap*)"
PAGE = 1000  # Europe PMC's maximum page size
MAX_RECORDS = 3000  # safety cap per run
LOOKBACK_MARGIN = 2
FULLTEXT_TIMEOUT = 60.0  # seconds: measured 10-26 s per full text, some over 30 s


@dataclass(frozen=True)
class EuropePmcResult:
    found: int
    new_versions: int


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("europepmc", "records", raw_root=raw_root)


def query(since: dt.date, until: dt.date) -> str:
    return f"({TERMS}) AND OPEN_ACCESS:y AND FIRST_IDATE:[{since} TO {until}]"


def _items(value: Any, *path: str) -> list[Any]:
    for key in path:
        value = (value or {}).get(key)
    return value or []


def trim_record(item: dict[str, Any]) -> dict[str, Any]:
    """The fields the pipeline uses; DOIs in lower case, as dbt joins. No abstract."""
    journal = _items(item, "journalInfo", "journal") or {}
    return {
        "source": item.get("source"),
        "id": item.get("id"),
        "pmid": item.get("pmid"),
        "pmcid": item.get("pmcid"),
        "doi": (item.get("doi") or "").lower() or None,
        "title": item.get("title"),
        "authors": [a["fullName"] for a in _items(item, "authorList", "author")
                    if a.get("fullName")],
        "journal": journal.get("title"),
        "issn": journal.get("issn"),
        "essn": journal.get("essn"),
        "first_published": item.get("firstPublicationDate"),
        "first_indexed": item.get("firstIndexDate"),
        "pub_types": _items(item, "pubTypeList", "pubType"),
        "language": item.get("language"),
        "is_open_access": item.get("isOpenAccess") == "Y",
        "in_epmc": item.get("inEPMC") == "Y",
        "license": item.get("license"),
        "mesh": sorted(m["descriptorName"] for m in _items(item, "meshHeadingList", "meshHeading")
                       if m.get("descriptorName")),
        "keywords": _items(item, "keywordList", "keyword"),
    }  # fmt: skip


def search(
    client: httpx.Client, since: dt.date, until: dt.date, throttle: Throttle
) -> Iterator[dict[str, Any]]:
    """Every matching record (``resultType=core``), following ``cursorMark``."""
    cursor, seen = "*", 0
    while seen < MAX_RECORDS:
        throttle.wait()
        body = get_json(client, f"{BASE}/search", params={
            "query": query(since, until), "format": "json", "resultType": "core",
            "pageSize": PAGE, "cursorMark": cursor, "email": CONTACT_EMAIL,
        })  # fmt: skip
        items = _items(body, "resultList", "result")
        yield from items
        seen += len(items)
        next_cursor = body.get("nextCursorMark")
        if len(items) < PAGE or not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor


def fulltext_path(cache_root: Path, pmcid: str) -> Path:
    return cache_root / "europepmc" / "fulltext" / f"{pmcid}.xml"


def ingest(
    client: httpx.Client,
    *,
    days: int = 3,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> EuropePmcResult:
    """Store the open-access records indexed in the last ``days`` days (metadata only).
    Idempotent: a rerun the same day writes nothing new."""
    today = today or utc_today()
    throttle = throttle or Throttle(5)
    records = store(raw_root)
    found = {}
    for item in search(client, today - dt.timedelta(days=days), today, throttle):
        if item.get("source") and item.get("id"):
            found[f"{item['source']}:{item['id']}"] = trim_record(item)
    previous = {k: e.payload for k, e in records.recent(days + LOOKBACK_MARGIN, today).items()}
    return EuropePmcResult(len(found), records.save(found, today, previous=previous))


def fetch_fulltext(
    client: httpx.Client, pmcid: str, *, cache_root: Path | None = None
) -> str | None:
    """Full-text XML of an open-access article, from the local cache or Europe PMC (then
    cached). None when Europe PMC serves no full text (404). Never stored in ``raw/``."""
    cache_root = cache_root if cache_root is not None else get_paths().cache
    path = fulltext_path(cache_root, pmcid)
    if path.exists():
        return path.read_text(encoding="utf-8")
    try:
        xml = get_text(client, f"{BASE}/{pmcid}/fullTextXML", timeout=FULLTEXT_TIMEOUT)
    except HttpError as exc:
        if exc.status_code == 404:
            return None
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, xml)
    return xml


def has_new_records(
    client: httpx.Client, *, today: dt.date | None = None, raw_root: Path | None = None
) -> bool:
    """Cheap change detection for ``syn check``: the first page of the last day; True if
    any record is not stored yet. Errors propagate (``syn check`` exits 2)."""
    today = today or utc_today()
    body = get_json(client, f"{BASE}/search", params={
        "query": query(today - dt.timedelta(days=1), today), "format": "json",
        "resultType": "idlist", "pageSize": PAGE, "email": CONTACT_EMAIL,
    })  # fmt: skip
    stored = store(raw_root).recent(1 + LOOKBACK_MARGIN, today)
    return any(
        f"{i.get('source')}:{i.get('id')}" not in stored
        for i in _items(body, "resultList", "result")
    )
