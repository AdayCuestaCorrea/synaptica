"""OpenAlex: the most cited works of each neuroscience subfield, for the weekly Clásicos
(plan, step 24a; SCOPE §5: «each week the site proposes some of the most cited of each
topic and Sofía chooses»).

One listing a week: for each of the 8 subfields of OpenAlex's Neuroscience field (28),
the :data:`PER_SUBFIELD` most cited articles published at least :data:`MIN_AGE_YEARS`
years ago and not retracted, with ``filter`` + ``sort`` (never ``search``), as spike S1
measured. 8 list requests a week out of OpenAlex's ~1000 a day. The listing goes to
``raw/openalex/classics/<date>.jsonl``, keyed by subfield; a second run in the same ISO
week asks nothing. Only metadata: title, year, DOI and citation count (OpenAlex is CC0).
Not in Paleo Atlas.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import CONTACT_EMAIL
from synaptica.http import Throttle, get_json
from synaptica.store import BatchStore, utc_today

WORKS = "https://api.openalex.org/works"
PER_SUBFIELD = 25
MIN_AGE_YEARS = 5
SELECT = "doi,display_name,publication_year,cited_by_count"
# OpenAlex subfields of field 28 (Neuroscience), measured on 2026-11-13: id, ES, EN.
SUBFIELDS = (
    ("2805", "Neurociencia cognitiva", "Cognitive neuroscience"),
    ("2804", "Neurociencia celular y molecular", "Cellular and molecular neuroscience"),
    ("2808", "Neurología", "Neurology"),
    ("2807", "Sistemas endocrino y autónomo", "Endocrine and autonomic systems"),
    ("2809", "Sistemas sensoriales", "Sensory systems"),
    ("2806", "Neurociencia del desarrollo", "Developmental neuroscience"),
    ("2802", "Neurociencia conductual", "Behavioral neuroscience"),
    ("2803", "Psiquiatría biológica", "Biological psychiatry"),
)


@dataclass(frozen=True)
class ClassicsResult:
    subfields: int
    works: int
    new_versions: int
    skipped: bool  # this ISO week was already listed


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("openalex", "classics", raw_root=raw_root)


def iso_week(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def trim(work: dict[str, Any]) -> dict[str, Any] | None:
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").lower()
    if not doi or not work.get("display_name"):
        return None
    return {"doi": doi, "title": work["display_name"], "year": work.get("publication_year"),
            "cited_by": work.get("cited_by_count") or 0}  # fmt: skip


def listing(
    client: httpx.Client, subfield: str, before_year: int, throttle: Throttle
) -> list[dict[str, Any]]:
    throttle.wait()
    body = get_json(client, WORKS, params={
        "filter": f"primary_topic.subfield.id:{subfield},type:article,is_retracted:false,"
                  f"publication_year:<{before_year}",
        "sort": "cited_by_count:desc", "per_page": PER_SUBFIELD, "select": SELECT,
        "mailto": CONTACT_EMAIL,
    })  # fmt: skip
    return [w for w in map(trim, body.get("results") or []) if w]


def latest(raw_root: Path | None = None, today: dt.date | None = None) -> dict[str, Any]:
    """Subfield id -> {"week", "works"} of the newest listing of the last 8 weeks."""
    return {k: e.payload for k, e in store(raw_root).recent(56, today).items()}


def works_by_doi(
    raw_root: Path | None = None, today: dt.date | None = None, days: int = 56
) -> dict[str, dict[str, Any]]:
    """Every work listed in the last ``days`` days (older listings too, so a pick keeps
    its metadata after the next week's listing), with its subfield id."""
    today, st = today or utc_today(), store(raw_root)
    out: dict[str, dict[str, Any]] = {}
    for offset in range(days):
        for sid, payload in st.read_day(today - dt.timedelta(days=offset)).items():
            for w in payload.get("works", []):
                out.setdefault(w["doi"], {**w, "subfield_id": sid})
    return out


def ingest(
    client: httpx.Client,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> ClassicsResult:
    """List the week's most cited works per subfield. Idempotent within an ISO week."""
    today = today or utc_today()
    week = iso_week(today)
    if any(p.get("week") == week for p in latest(raw_root, today).values()):
        return ClassicsResult(0, 0, 0, skipped=True)
    throttle = throttle or Throttle(5)
    records = {sid: {"week": week, "works": listing(client, sid, today.year - MIN_AGE_YEARS + 1,
                                                    throttle)}
               for sid, _, _ in SUBFIELDS}  # fmt: skip
    saved = store(raw_root).save(records, today)
    works = sum(len(r["works"]) for r in records.values())
    return ClassicsResult(len(records), works, saved, skipped=False)
