"""Neuroscience preprints from bioRxiv and medRxiv, one entry per DOI.

The ``details`` API (``api.biorxiv.org/details/{server}/{from}/{to}/{cursor}``) lists the
preprints *posted* in an interval, one category at a time, in pages of
:data:`PAGE_SIZE`. Two things measured in spike S1 (``spikes/s1/biorxiv.py``,
``docs/fuentes.md``) shape this step:

- **Every version is a separate entry** with the same DOI (v1, v2…). Within a run only the
  highest version of each DOI is kept, and the daily batch stores one line per DOI, so a
  new version shows up as a changed line on the day it appears: two versions, one study.
- **Past days keep growing** (a week went from 30 to 34 preprints days later), so the
  window looks back :data:`DEFAULT_DAYS` days, and unchanged DOIs are not written again.

``published`` carries the DOI of the journal version once the preprint is published:
that is the preprint ↔ published link for the unified study (plan, step 11).

Abstracts are the authors' text under each preprint's licence (``cc_no`` allows no
reuse): they go only to the local cache ``data/cache/<server>/abstract/``, as PubMed's.

Limits: none published and no rate headers; the API is slow (3-13 s per request, one
timeout at 30 s in S1), so requests go one per second with a 120 s timeout. Not in Paleo
Atlas; the shape follows :mod:`synaptica.ingest.crossref`.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import get_paths
from synaptica.http import Throttle, get_json
from synaptica.store import BatchStore, _atomic_write, utc_today

BASE = "https://api.biorxiv.org/details"
# Categories are lower case with underscores (S1).
CATEGORIES = {
    "biorxiv": ("neuroscience",),
    "medrxiv": ("neurology", "psychiatry_and_clinical_psychology"),
}
PAGE_SIZE = 30  # fixed by the API
DEFAULT_DAYS = 7
TIMEOUT = 120.0
MAX_PAGES = 100  # safety cap per category and run (S1: ~400 a week in neuroscience)
LOOKBACK_MARGIN = 2


@dataclass(frozen=True)
class BiorxivResult:
    found: dict[str, int]  # DOIs (latest version) per server/category
    new_versions: dict[str, int]  # per server
    abstracts_cached: int


def store(server: str, raw_root: Path | None = None) -> BatchStore:
    return BatchStore(server, "preprints", raw_root=raw_root)


def list_details(
    client: httpx.Client,
    server: str,
    category: str,
    since: dt.date,
    until: dt.date,
    throttle: Throttle,
) -> Iterator[dict[str, Any]]:
    """Every entry (one per version) posted in ``[since, until]``, following the cursor."""
    cursor = 0
    for _ in range(MAX_PAGES):
        throttle.wait()
        body = get_json(
            client, f"{BASE}/{server}/{since}/{until}/{cursor}",
            params={"category": category}, timeout=TIMEOUT,
        )  # fmt: skip
        items = body.get("collection") or []
        yield from items
        message = (body.get("messages") or [{}])[0]
        total = int(message.get("total") or 0)
        cursor += len(items)
        if not items or cursor >= total:
            return


def _version(item: dict[str, Any]) -> int:
    try:
        return int(item.get("version") or 0)
    except ValueError:
        return 0


def trim_preprint(item: dict[str, Any]) -> dict[str, Any]:
    """The fields the pipeline uses; DOIs in lower case. No abstract."""
    published = (item.get("published") or "").strip()
    return {
        "doi": item["doi"].lower(),
        "server": item.get("server"),
        "title": " ".join((item.get("title") or "").split()) or None,
        "authors": [a.strip() for a in (item.get("authors") or "").split(";") if a.strip()],
        "date": item.get("date"),
        "version": _version(item),
        "type": item.get("type"),
        "license": item.get("license"),
        "category": item.get("category"),
        "published_doi": published.lower() if published and published != "NA" else None,
        "jatsxml": item.get("jatsxml"),
    }


def latest_versions(items: Iterator[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Highest version of each DOI (the API lists every version separately)."""
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not item.get("doi"):
            continue
        doi = item["doi"].lower()
        if doi not in out or _version(item) >= _version(out[doi]):
            out[doi] = item
    return out


def _cache_abstract(cache_root: Path, server: str, item: dict[str, Any]) -> bool:
    text = (item.get("abstract") or "").strip()
    if not text:
        return False
    doi = item["doi"].lower()
    path = cache_root / server / "abstract" / f"{doi.replace('/', '_')}.json"
    body = json.dumps(
        {"doi": doi, "version": _version(item), "abstract": text}, ensure_ascii=False, indent=1
    )
    if path.exists() and path.read_text(encoding="utf-8") == body + "\n":
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, body + "\n")
    return True


def ingest(
    client: httpx.Client,
    *,
    days: int = DEFAULT_DAYS,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    cache_root: Path | None = None,
    throttle: Throttle | None = None,
) -> BiorxivResult:
    """Store the latest version of every neuro preprint posted in the last ``days`` days.
    Idempotent: a rerun writes nothing new unless a new version or field appeared."""
    today = today or utc_today()
    throttle = throttle or Throttle(1)
    cache_root = cache_root if cache_root is not None else get_paths().cache
    since = today - dt.timedelta(days=days)
    found: dict[str, int] = {}
    new_versions: dict[str, int] = {}
    abstracts = 0
    for server, categories in CATEGORIES.items():
        items: dict[str, dict[str, Any]] = {}
        for category in categories:
            latest = latest_versions(list_details(client, server, category, since, today, throttle))
            found[f"{server}/{category}"] = len(latest)
            for doi, item in latest.items():
                if doi not in items or _version(item) >= _version(items[doi]):
                    items[doi] = item
        preprints = store(server, raw_root)
        recent = preprints.recent(days + LOOKBACK_MARGIN, today)
        previous = {k: e.payload for k, e in recent.items()}
        # A newer version stored on an earlier day is never overwritten by an older one.
        trimmed = {
            doi: trim_preprint(item)
            for doi, item in items.items()
            if doi not in previous or _version(item) >= previous[doi].get("version", 0)
        }
        new_versions[server] = preprints.save(trimmed, today, previous=previous)
        abstracts += sum(_cache_abstract(cache_root, server, items[d]) for d in trimmed)
    return BiorxivResult(found, new_versions, abstracts)


def has_new_preprints(
    client: httpx.Client, *, today: dt.date | None = None, raw_root: Path | None = None
) -> bool:
    """Cheap change detection for ``syn check``: the first bioRxiv neuroscience page of
    the last day; True if any DOI or version is not stored yet. Errors propagate."""
    today = today or utc_today()
    body = get_json(
        client, f"{BASE}/biorxiv/{today - dt.timedelta(days=1)}/{today}/0",
        params={"category": "neuroscience"}, timeout=TIMEOUT,
    )  # fmt: skip
    stored = store("biorxiv", raw_root).recent(DEFAULT_DAYS + LOOKBACK_MARGIN, today)
    for item in body.get("collection") or []:
        doi = (item.get("doi") or "").lower()
        if doi and (doi not in stored or _version(item) > stored[doi].payload.get("version", 0)):
            return True
    return False
