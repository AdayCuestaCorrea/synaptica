"""New neuroscience records from PubMed (E-utilities): metadata, MeSH and abstracts.

Three calls, as measured in spike S1 (``spikes/s1/pubmed.py``, ``docs/fuentes.md``):

1. ``esearch``: PMIDs that *entered* PubMed in the last ``days`` days (``datetype=edat``)
   for :data:`TERM`, paged.
2. ``esummary``: metadata of each new PMID, trimmed to :data:`SUMMARY_FIELDS`.
3. ``efetch``: the MEDLINE record, from which only indexing is kept: status, MeSH
   headings, publication types and author keywords. The MeSH ``Humans`` / ``Animals``
   headings feed the study signals (plan, step 12).

Both go to daily batch files (:class:`synaptica.store.BatchStore`, Aday's decision of
2026-11-12: ~700 records a day would otherwise mean ~500 000 files a year in the ``data``
branch): ``raw/pubmed/summary/<date>.jsonl`` and ``raw/pubmed/medline/<date>.jsonl``.

Abstracts are publisher text (SCOPE §3, CLAUDE.md "Licencias"): they go only to the local
cache ``data/cache/pubmed/abstract/<pmid>.json``, never committed, as input for the
summaries. New records usually have no MeSH yet (status ``Publisher``, ``In-Process``…),
so their MEDLINE record is fetched again when they are 7, 14… days old
(:data:`MEDLINE_RECHECK_DAYS`), until it reaches a final status or turns
:data:`MEDLINE_MAX_AGE_DAYS` days old. The schedule depends only on the age, so it needs
no "last checked" state; a run that misses a day moves that check to the next week.

Limits: 3 requests/s without an API key, 10/s with ``NCBI_API_KEY``. Every request also
carries ``tool`` and ``email``, as NCBI asks.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL, get_paths
from synaptica.http import HttpError, Throttle, get_json, get_text
from synaptica.store import BatchStore, _atomic_write, utc_today

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Broad on purpose (spike S1): new records have no MeSH yet, so title/abstract words matter.
TERM = (
    '"nervous system"[MeSH] OR "nervous system diseases"[MeSH] OR brain[tiab] '
    "OR neuron*[tiab] OR neural[tiab] OR cortex[tiab] OR synap*[tiab]"
)
PAGE = 500  # PMIDs per esearch page
BATCH = 200  # PMIDs per esummary / efetch request (NCBI recommends at most ~200 per GET)
MAX_RECORDS = 5000  # safety cap per run: S1 measured ~3400 records a week
# esummary fields the pipeline uses; the rest (sort keys, history, references…) is dropped.
SUMMARY_FIELDS = (
    "uid", "title", "source", "fulljournalname", "issn", "essn", "pubdate", "epubdate",
    "sortpubdate", "lang", "pubtype", "pubstatus", "articleids", "authors",
)  # fmt: skip
ARTICLE_ID_TYPES = {"pubmed", "doi", "pmc", "pmcid", "pii"}
LOOKBACK_MARGIN = 2  # extra days of stored files read to know which PMIDs are already in
MEDLINE_RECHECK_DAYS = 7
MEDLINE_MAX_AGE_DAYS = 90
# Final statuses: indexed with MeSH, or never to be indexed (NLM selects MEDLINE journals).
FINAL_STATUSES = {"MEDLINE", "OLDMEDLINE", "PubMed-not-MEDLINE"}

Indexing = dict[str, Any]
Abstract = list[dict[str, str]]


@dataclass(frozen=True)
class PubmedResult:
    found: int  # PMIDs that entered PubMed in the window
    summaries_requested: int
    summaries_new_versions: int
    medline_requested: int
    medline_new_versions: int
    abstracts_cached: int


def summary_store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("pubmed", "summary", raw_root=raw_root)


def medline_store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("pubmed", "medline", raw_root=raw_root)


def base_params(api_key: str | None) -> dict[str, str]:
    params = {"db": "pubmed", "tool": "synaptica", "email": CONTACT_EMAIL}
    if api_key:
        params["api_key"] = api_key
    return params


def _batches(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# --- requests ------------------------------------------------------------------------


def search(
    client: httpx.Client, days: int, params: dict[str, str], throttle: Throttle
) -> list[str]:
    """PMIDs that entered PubMed in the last ``days`` days, newest first, up to the cap."""
    pmids: list[str] = []
    while True:
        throttle.wait()
        body = get_json(client, f"{BASE}/esearch.fcgi", params={
            **params, "term": TERM, "datetype": "edat", "reldate": days,
            "retstart": len(pmids), "retmax": PAGE, "retmode": "json",
        })  # fmt: skip
        result = body.get("esearchresult", {})
        if "ERROR" in result:
            raise HttpError(f"PubMed esearch error: {result['ERROR']}")
        page = result.get("idlist", [])
        pmids += page
        if not page or len(pmids) >= min(int(result.get("count", 0)), MAX_RECORDS):
            return pmids[:MAX_RECORDS]


def trim_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Keep only :data:`SUMMARY_FIELDS`; authors by name, article IDs of known types."""
    out = {k: record[k] for k in SUMMARY_FIELDS if k in record}
    if "authors" in out:
        out["authors"] = [a["name"] for a in out["authors"] if a.get("name")]
    if "articleids" in out:
        out["articleids"] = {
            a["idtype"]: a["value"] for a in out["articleids"] if a["idtype"] in ARTICLE_ID_TYPES
        }
    return out


def fetch_summaries(
    client: httpx.Client, pmids: list[str], params: dict[str, str], throttle: Throttle
) -> dict[str, dict[str, Any]]:
    """Trimmed esummary records by PMID; PMIDs reported as missing are left out."""
    out: dict[str, dict[str, Any]] = {}
    for batch in _batches(pmids, BATCH):
        throttle.wait()
        body = get_json(client, f"{BASE}/esummary.fcgi", params={
            **params, "id": ",".join(batch), "retmode": "json",
        })  # fmt: skip
        result = body.get("result", {})
        for uid in result.get("uids", []):
            record = result.get(uid)
            if isinstance(record, dict) and "error" not in record:
                out[uid] = trim_summary(record)
    return out


def fetch_medline(
    client: httpx.Client, pmids: list[str], params: dict[str, str], throttle: Throttle
) -> dict[str, tuple[Indexing, Abstract]]:
    """(indexing, abstract sections) by PMID, parsed from efetch XML."""
    out: dict[str, tuple[Indexing, Abstract]] = {}
    for batch in _batches(pmids, BATCH):
        throttle.wait()
        xml = get_text(client, f"{BASE}/efetch.fcgi", params={
            **params, "id": ",".join(batch), "retmode": "xml",
        })  # fmt: skip
        out.update(parse_efetch(xml))
    return out


# --- parsing ---------------------------------------------------------------------------


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def parse_efetch(xml: str) -> dict[str, tuple[Indexing, Abstract]]:
    """Split each PubmedArticle into public indexing and the private abstract.

    Indexing: MEDLINE status, MeSH descriptors (UI, name, major topic, qualifiers),
    publication types and author keywords. Abstract: its sections, label and text."""
    out = {}
    for article in ET.fromstring(xml).iter("PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None or not (pmid := citation.findtext("PMID")):
            continue
        mesh = []
        for heading in citation.iterfind("MeshHeadingList/MeshHeading"):
            descriptor = heading.find("DescriptorName")
            if descriptor is None:
                continue
            mesh.append({
                "ui": descriptor.get("UI"),
                "name": _text(descriptor),
                "major": descriptor.get("MajorTopicYN") == "Y",
                "qualifiers": [_text(q) for q in heading.iterfind("QualifierName")],
            })  # fmt: skip
        indexing = {
            "status": citation.get("Status"),
            "mesh": mesh,
            "publication_types": [
                {"ui": p.get("UI"), "name": _text(p)}
                for p in citation.iterfind("Article/PublicationTypeList/PublicationType")
            ],
            "keywords": [_text(k) for k in citation.iterfind("KeywordList/Keyword")],
            "has_abstract": citation.find("Article/Abstract") is not None,
        }
        abstract = [
            {"label": section.get("Label") or "", "text": _text(section)}
            for section in citation.iterfind("Article/Abstract/AbstractText")
        ]
        out[pmid] = (indexing, abstract)
    return out


# --- what to request -------------------------------------------------------------------


def medline_recheck_due(status: str | None, first_seen: dt.date, today: dt.date) -> bool:
    """True on the days a record still waiting for indexing is asked again: when it is
    7, 14… days old, up to :data:`MEDLINE_MAX_AGE_DAYS`."""
    age = (today - first_seen).days
    return (
        status not in FINAL_STATUSES
        and 0 < age <= MEDLINE_MAX_AGE_DAYS
        and age % MEDLINE_RECHECK_DAYS == 0
    )


def _cache_abstract(cache_root: Path, pmid: str, sections: Abstract) -> bool:
    """Write the abstract to the local cache if it is new or changed (True if written)."""
    if not sections:
        return False
    path = cache_root / "pubmed" / "abstract" / f"{pmid}.json"
    text = json.dumps({"pmid": pmid, "sections": sections}, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, text)
    return True


# --- the step --------------------------------------------------------------------------


def ingest(
    client: httpx.Client,
    *,
    days: int = 3,
    api_key: str | None = None,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    cache_root: Path | None = None,
    throttle: Throttle | None = None,
) -> PubmedResult:
    """Fetch the records of the last ``days`` days that are not stored yet, and re-check
    the MEDLINE indexing of recent records that had none. Idempotent: a second run on the
    same day requests only what is still missing and writes nothing new.

    The window overlaps previous runs on purpose (default 3 days), so a skipped or failed
    day is recovered by the next run."""
    today = today or utc_today()
    if api_key is None:
        api_key = os.environ.get("NCBI_API_KEY") or None
    throttle = throttle or Throttle(10 if api_key else 3)
    cache_root = cache_root if cache_root is not None else get_paths().cache
    params = base_params(api_key)
    summaries, medline = summary_store(raw_root), medline_store(raw_root)

    pmids = search(client, days, params, throttle)
    stored = summaries.recent(days + LOOKBACK_MARGIN, today)
    new = [p for p in pmids if p not in stored]
    found = fetch_summaries(client, new, params, throttle)
    summary_versions = summaries.save(found, today)

    indexed = medline.recent(MEDLINE_MAX_AGE_DAYS + 1, today)
    due = sorted(
        {p for p in (*found, *stored) if p not in indexed}  # never fetched, or failed before
        | {
            p
            for p, entry in indexed.items()
            if medline_recheck_due(entry.payload.get("status"), entry.first_seen, today)
        }
    )
    records = fetch_medline(client, due, params, throttle)
    medline_versions = medline.save(
        {p: indexing for p, (indexing, _) in records.items()},
        today,
        previous={p: e.payload for p, e in indexed.items()},
    )
    abstracts = sum(
        _cache_abstract(cache_root, p, sections) for p, (_, sections) in records.items()
    )
    return PubmedResult(
        found=len(pmids),
        summaries_requested=len(new),
        summaries_new_versions=summary_versions,
        medline_requested=len(due),
        medline_new_versions=medline_versions,
        abstracts_cached=abstracts,
    )
