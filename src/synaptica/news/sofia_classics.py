"""Sofía's own list of Clásicos (her sheet, row 3, 2026-11-24; Aday's option A, v238).

She answered the «choose the first Clásicos» question with a list of the landmark papers
she wants, none of them in the OpenAlex proposals (which go by citation count only). Her
list replaces the weekly proposal: the site shows :data:`PER_WEEK` of them each week, in
her order (which groups them by theme), starting at ``start_week`` and going round again
at the end. Her choice is the approval of step 24b; no proposal goes to her queue any more.

``classics_sofia.json`` keeps her titles exactly as she wrote them and, next to each, what
OpenAlex says of it (CC0 metadata: DOI, title, year, citations, subfield), found once with
``syn classics resolve`` (by hand, never in the pipeline). A title OpenAlex does not know,
or knows only by a different title, keeps ``match`` so it can be checked by hand; a title
with no DOI is shown with its OpenAlex link instead. The integrity signal is still read
from ``dim_integrity`` when the page is built (v148).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx

from synaptica.http import Throttle, get_json
from synaptica.ingest import classics as listing
from synaptica.ingest import openalex

LIST = Path(__file__).with_name("classics_sofia.json")
PER_WEEK = 5
SELECT = "id,doi,display_name,publication_year,cited_by_count,primary_topic"


def normal(title: str) -> str:
    """Lower case, no accents, any dash or quote mark a space (OpenAlex writes «end-plate»
    with U+2010 and «astrocyte-neuron» with an en dash)."""
    text = "".join(
        c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c)
    )  # «Über» → «Uber», not «U ber»
    text = re.sub(r"[\W_]+", " ", text)
    return re.sub(r"\s+", " ", text.encode("ascii", "ignore").decode().casefold()).strip()


def _trim(work: dict[str, Any]) -> dict[str, Any]:
    sub = ((work.get("primary_topic") or {}).get("subfield") or {}).get("id") or ""
    return {
        "openalex": (work.get("id") or "").removeprefix("https://openalex.org/") or None,
        "doi": (work.get("doi") or "").removeprefix("https://doi.org/").lower() or None,
        "title": work.get("display_name"),
        "year": work.get("publication_year"),
        "cited_by": work.get("cited_by_count") or 0,
        "subfield_id": sub.rsplit("/", 1)[-1] or None,
    }


def find(client: httpx.Client, title: str, throttle: Throttle) -> dict[str, Any]:
    """OpenAlex's work for one of her titles: the most cited whose title is hers
    (``match: exact``), else the most cited of the search (``closest``), else nothing."""
    throttle.wait()
    body = get_json(client, listing.WORKS, params={
        "filter": f"title.search:{title.replace(',', ' ')}", "sort": "cited_by_count:desc",
        "per_page": 10, "select": SELECT, **openalex.auth_params(),
    })  # fmt: skip
    works = [_trim(w) for w in body.get("results") or []]
    exact = [w for w in works if w["title"] and normal(w["title"]) == normal(title)]
    if exact:
        return {**exact[0], "match": "exact"}
    if works:
        return {**works[0], "match": "closest"}
    return {"match": "none"}


def resolve(client: httpx.Client, titles: list[str], *, chosen_at: str, source: str,
            start_week: str, dois: dict[int, str] | None = None,
            throttle: Throttle | None = None) -> dict[str, Any]:  # fmt: skip
    """Her list with OpenAlex's metadata; ``dois`` (1-based position → DOI) overrides the
    search where it was checked by hand."""
    throttle, dois = throttle or Throttle(5), dois or {}
    works = [{"title_hers": t, **(by_doi(client, dois[n], throttle) if n in dois
                                  else find(client, t, throttle))}
             for n, t in enumerate(titles, 1)]  # fmt: skip
    return {"chosen_by": "sofia", "chosen_at": chosen_at, "source": source,
            "start_week": start_week, "per_week": PER_WEEK, "works": works}  # fmt: skip


def load(path: Path | None = None) -> dict[str, Any] | None:
    path = path or LIST
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _monday(week: str) -> dt.date:
    year, w = week.split("-W")
    return dt.date.fromisocalendar(int(year), int(w), 1)


def of_week(data: dict[str, Any], today: dt.date) -> list[dict[str, Any]]:
    """The works shown this week: the next :data:`PER_WEEK` of her list, round and round;
    [] before her start week. Only works whose title matched hers or was checked by hand:
    never a «closest» guess."""
    works = [w for w in data["works"] if w.get("match") in ("exact", "doi")]
    weeks = (today - _monday(data["start_week"])).days // 7
    if weeks < 0 or not works:
        return []
    per = int(data.get("per_week", PER_WEEK))
    start = weeks * per
    return [works[(start + i) % len(works)] for i in range(min(per, len(works)))]


def by_doi(client: httpx.Client, doi: str, throttle: Throttle) -> dict[str, Any]:
    """The work of a DOI (or an OpenAlex id, ``W…``, for one without a DOI) checked by
    hand, for a title the search gets wrong (a reprint instead of the original, or
    nothing) or only finds by a longer title: ``match: doi``."""
    throttle.wait()
    key = f"openalex:{doi}" if doi.startswith("W") else f"doi:{doi.lower()}"
    body = get_json(client, listing.WORKS, params={
        "filter": key, "select": SELECT, **openalex.auth_params(),
    })  # fmt: skip
    works = [_trim(w) for w in body.get("results") or []]
    return {**works[0], "match": "doi"} if works else {"match": "none"}


def shown(work: dict[str, Any]) -> dict[str, Any]:
    """What the Clásicos block reads: her title (OpenAlex writes some in capitals), the
    rest as OpenAlex has it, and its link; ``lang`` is the title's language."""
    url = (f"https://doi.org/{work['doi']}" if work.get("doi")
           else f"https://openalex.org/{work['openalex']}")  # fmt: skip
    return {"doi": work.get("doi"), "title": work["title_hers"], "lang": work.get("lang", "en"),
            "year": work.get("year"), "cited_by": work.get("cited_by") or 0, "url": url,
            "subfield_id": work.get("subfield_id")}  # fmt: skip
