"""Retraction Watch database, for the retractions publishers never deposit in Crossref.

New in SYNAPTICA (no Paleo Atlas counterpart). It fills the known gap of
``synaptica.ingest.crossref``: a retraction that Crossref only knows from Retraction Watch
appears in the ``updated-by`` field of the retracted work, not as a notice, so the daily
list of notices misses it.

Source (checked on 2026-11-13): Crossref publishes the whole database as one CSV in
https://gitlab.com/crossref/retraction-watch-data, updated every working day (73 786 rows,
68 MB, UTF-8; one request, GitLab allows 500 unauthenticated requests per window).

Licence: CC0, no attribution required (Crossref's licensing table,
https://www.crossref.org/documentation/retrieve-metadata/#73020, confirmed by its support
team to Aday on 2026-11-13: the data are "facts" in the public domain). The site still
names the source next to each notice. Only facts are kept (which DOI, which kind of
notice, which date and the notice's DOI): no titles, authors, reasons or notes.

Storage: a :class:`~synaptica.store.BatchStore` keyed by the Retraction Watch record ID.
The state is the sum of every daily file (:meth:`BatchStore.all`): the first run stores
every useful row (~68 600), later runs only the rows that are new or changed. A record
can change kind (a ``Retraction`` becomes a ``Reinstatement`` in the same row: 157 of the
158 reinstated DOIs have no other retraction row), so dbt keeps the latest version of
each record. A record that leaves the CSV is stored as ``{"removed": true}``.

The download is conditional (``If-None-Match`` with the ETag kept in the private cache):
on days without a new commit GitLab answers 304 and nothing is read. A file much smaller
than the stored state (a truncated download, a format change) is refused rather than
marking thousands of records as removed. A day lost after the 304 (the ETag cached but
the data commit failed) is recovered on the next change: every download is the full
snapshot, compared with the whole stored state.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import get_paths
from synaptica.http import HttpError, get_response
from synaptica.store import BatchStore, utc_today

URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
COLUMNS = (
    "Record ID", "RetractionDate", "RetractionDOI", "OriginalPaperDOI",
    "OriginalPaperPubMedID", "RetractionNature",
)  # fmt: skip
NATURES = {
    "Retraction": "retraction",
    "Expression of concern": "expression_of_concern",
    "Correction": "correction",
    "Reinstatement": "reinstatement",
}
MIN_SHARE = 0.9  # a new file with fewer live records than this share of the stored ones
MIN_LIVE = 1000  # … is refused once at least this many records are stored
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)


@dataclass(frozen=True)
class RetractionWatchResult:
    downloaded: bool  # False when GitLab answered 304 (no new commit)
    rows: int  # rows in the CSV
    kept: int  # rows with a DOI or a PubMed ID of the original paper
    new_versions: int  # records new or changed today (removals included)
    removed: int


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("retractionwatch", "notices", raw_root=raw_root)


def _etag_path(cache_root: Path | None) -> Path:
    return (cache_root if cache_root is not None else get_paths().cache) / "retractionwatch.json"


def clean_doi(value: str) -> str | None:
    """Lower case, without a resolver prefix; None for '', 'unavailable' or a non-DOI."""
    doi = _DOI_PREFIX.sub("", value.strip()).lower()
    return doi if doi.startswith("10.") else None


def clean_pmid(value: str) -> str | None:
    value = value.strip()
    return value if value.isdigit() and value.strip("0") else None


def clean_date(value: str) -> str | None:
    """``5/6/2026 0:00`` (month first) to ``2026-05-06``; None when it does not parse."""
    try:
        return dt.datetime.strptime(value.split()[0], "%m/%d/%Y").date().isoformat()
    except ValueError, IndexError:
        return None


def trim_row(row: dict[str, str]) -> dict[str, Any] | None:
    """The facts of one row, or None when it names no original paper we could match."""
    doi = clean_doi(row["OriginalPaperDOI"])
    pmid = clean_pmid(row["OriginalPaperPubMedID"])
    if not doi and not pmid:
        return None
    nature = row["RetractionNature"].strip()
    return {
        "doi": doi,
        "pmid": pmid,
        "nature": NATURES.get(nature, nature),  # an unknown kind is a dbt warning
        "notice_doi": clean_doi(row["RetractionDOI"]),
        "date": clean_date(row["RetractionDate"]),
    }


def parse(text: str) -> tuple[int, dict[str, dict[str, Any]]]:
    """Rows in the CSV and the trimmed records by record ID. Missing columns raise."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise HttpError(f"Retraction Watch CSV without the columns {missing}")
    rows = 0
    records: dict[str, dict[str, Any]] = {}
    for row in reader:
        rows += 1
        if (record := trim_row(row)) is not None:
            records[row["Record ID"].strip()] = record
    return rows, records


def ingest(
    client: httpx.Client,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    cache_root: Path | None = None,
) -> RetractionWatchResult:
    """Store what changed in the Retraction Watch CSV since the last run. Idempotent: a
    rerun the same day writes nothing new (and usually gets a 304)."""
    today = today or utc_today()
    notices = store(raw_root)
    etag_file = _etag_path(cache_root)
    cached = json.loads(etag_file.read_text(encoding="utf-8")) if etag_file.exists() else {}
    headers = {"If-None-Match": cached["etag"]} if cached.get("etag") else {}
    response = get_response(client, URL, headers=headers, timeout=180)
    if response.status_code == 304:
        return RetractionWatchResult(False, 0, 0, 0, 0)

    rows, records = parse(response.content.decode("utf-8-sig"))
    state = {k: e.payload for k, e in notices.all().items()}
    live = {k for k, p in state.items() if not p.get("removed")}
    if len(live) >= MIN_LIVE and len(records) < MIN_SHARE * len(live):
        raise HttpError(
            f"Retraction Watch CSV has {len(records)} usable rows, fewer than "
            f"{MIN_SHARE:.0%} of the {len(live)} stored: refused (truncated or changed?)"
        )
    removed = {k: {"removed": True} for k in live - records.keys()}
    changed = notices.save(records | removed, today, previous=state)
    if etag := response.headers.get("ETag"):
        etag_file.parent.mkdir(parents=True, exist_ok=True)
        etag_file.write_text(json.dumps({"etag": etag, "checked_on": today.isoformat()}))
    return RetractionWatchResult(True, rows, len(records), changed, len(removed))
