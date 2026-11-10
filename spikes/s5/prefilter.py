"""S5 · How many of PubMed's daily neuro records survive a cheap pre-filter (metadata only).

One day of the broad S1 query; ``esummary`` (no abstracts) for every record; counts by
publication type, language and whether the record has an abstract, and the size of the
filtered set the LLM would have to summarize. Run from the repo root:

    uv run --env-file .env python spikes/s5/prefilter.py
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import time
from pathlib import Path

import httpx

from synaptica.config import CONTACT_EMAIL, USER_AGENT

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TERM = (
    '"nervous system"[MeSH] OR "nervous system diseases"[MeSH] OR brain[tiab] '
    "OR neuron*[tiab] OR neural[tiab] OR cortex[tiab] OR synap*[tiab]"
)
DAYS = ("2026/11/02", "2026/11/03", "2026/11/04", "2026/11/05", "2026/11/06")
NOT_RESEARCH = {"Erratum", "Published Erratum", "Comment", "Editorial", "Letter", "News",
                "Retraction of Publication", "Retracted Publication", "Preprint"}  # fmt: skip
REVIEWS = {"Review", "Systematic Review", "Meta-Analysis"}
OUT = Path(__file__).parent / "results" / "prefilter.json"


def main() -> None:
    params = {"db": "pubmed", "tool": "synaptica", "email": CONTACT_EMAIL}
    if key := os.environ.get("NCBI_API_KEY"):
        params["api_key"] = key
    out: dict[str, object] = {"measured_at": dt.datetime.now(dt.UTC).isoformat(), "days": {}}
    with httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}) as c:
        for day in DAYS:
            r = c.get(f"{EUTILS}/esearch.fcgi", params={
                **params, "term": TERM, "datetype": "edat", "mindate": day, "maxdate": day,
                "retmax": 5000, "retmode": "json"})  # fmt: skip
            ids = r.raise_for_status().json()["esearchresult"]["idlist"]
            docs = []
            for i in range(0, len(ids), 200):
                time.sleep(0.2)
                r = c.post(
                    f"{EUTILS}/esummary.fcgi",
                    data={**params, "id": ",".join(ids[i : i + 200]), "retmode": "json"},
                )
                res = r.raise_for_status().json()["result"]
                docs += [res[u] for u in res["uids"]]
            types = collections.Counter(t for d in docs for t in d.get("pubtype", []))

            def keep(d: dict, *, reviews: bool) -> bool:
                pt = set(d.get("pubtype", []))
                return (
                    "Has Abstract" in d.get("attributes", [])
                    and "eng" in d.get("lang", [])
                    and not pt & NOT_RESEARCH
                    and (reviews or not pt & REVIEWS)
                )

            row = {
                "records": len(docs),
                "with_abstract": sum("Has Abstract" in d.get("attributes", []) for d in docs),
                "english": sum("eng" in d.get("lang", []) for d in docs),
                "research_with_abstract_en": sum(keep(d, reviews=True) for d in docs),
                "same_without_reviews": sum(keep(d, reviews=False) for d in docs),
                "top_types": types.most_common(12),
            }
            print(day, {k: v for k, v in row.items() if k != "top_types"})
            out["days"][day] = row
            time.sleep(0.5)
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
