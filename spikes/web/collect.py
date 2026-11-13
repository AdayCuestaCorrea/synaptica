"""Collect the real data the three web mock-ups show (spike, not package code).

Inputs, all real:
- the warehouse built from the 2026-11-12 raw batches (``--warehouse``): studies and news;
- the S5 run with the D4 pair (writer qwen3.8-27b, judge gpt-oss-120b): own summaries, shown
  only when they passed the checks and the judge; otherwise the data fallback
  (``synaptica.narrative.fallback``), as the site will do;
- the S5 efetch cache (``data/cache/s5/``): title, journal, date, DOI and MeSH of those
  studies (the abstract is never read here);
- three build-time requests, cached in ``data/sources/`` so a rerun needs no network:
  Crossref metadata of one retracted and one corrected neuro study (the notices come from
  our own Crossref batch) and one Wikidata SPARQL query (CC0) for mock-up C's anniversary.

Nothing is invented: a missing field stays ``None`` and the templates mark it as a gap.

    SYN_DATA_DIR=<scratch> uv run python spikes/web/collect.py --warehouse <db>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import duckdb

from synaptica.http import get_json, make_client
from synaptica.narrative.fallback import fallback_text
from synaptica.narrative.weekly import weekly_fallback

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
S5_RUN = ROOT / "spikes/s5/results/run_groq-qwen-qwen3.8-27b-groq-openai-gpt-oss-120b.json"
S5_EFETCH = ROOT / "data/cache/s5/pubmed/efetch_20261102.xml"
SOURCES = HERE / "data/sources"
AS_OF = dt.date(2026, 11, 12)
WEEK = "2026-W45"  # the S5 window (2026-11-02 … 08) is exactly that ISO week

TRIAL_TYPES = {"Clinical Trial", "Randomized Controlled Trial", "Clinical Trial, Phase I",
               "Clinical Trial, Phase II", "Clinical Trial, Phase III",
               "Clinical Trial, Phase IV", "Controlled Clinical Trial"}  # fmt: skip
# Real notices from our Crossref batch of 2026-11-12 (raw/crossref/notices), neuro journals.
NOTICE_EXAMPLES = {
    "retracted": ("10.1016/j.bbi.2018.02.015", "retraction"),
    "corrected": ("10.1016/j.expneurol.2025.115634", "erratum"),
}
WIKIDATA = "https://query.wikidata.org/sparql"
# People whose occupation is neuroscientist (Q6337803) or neurologist (Q783906), born on
# 12 November; their Wikidata description (CC0) is the only text used.
SPARQL = """
SELECT ?p ?es ?en ?des ?den ?born ?links WHERE {
  VALUES ?occ { wd:Q6337803 wd:Q783906 }
  ?p wdt:P106 ?occ; wdt:P569 ?born; wikibase:sitelinks ?links.
  FILTER(MONTH(?born) = 11 && DAY(?born) = 12)
  OPTIONAL { ?p rdfs:label ?es FILTER(LANG(?es) = "es") }
  OPTIONAL { ?p rdfs:label ?en FILTER(LANG(?en) = "en") }
  OPTIONAL { ?p schema:description ?des FILTER(LANG(?des) = "es") }
  OPTIONAL { ?p schema:description ?den FILTER(LANG(?den) = "en") }
} ORDER BY DESC(?links) LIMIT 5
"""


def _cached(name: str, fetch) -> Any:
    path = SOURCES / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    SOURCES.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, dt.date | dt.datetime) else value


def original_url(row: dict[str, Any]) -> str | None:
    if row.get("doi"):
        return f"https://doi.org/{row['doi']}"
    if row.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"
    if row.get("pmcid"):  # only in Europe PMC
        return f"https://europepmc.org/article/PMC/{row['pmcid'].removeprefix('PMC')}"
    return None


def news_type(row: dict[str, Any]) -> str | None:
    """Only clinical trial is known without the LLM (PubMed publication type); the rest
    stays None, a gap until ``syn news classify`` runs (step 14a)."""
    if TRIAL_TYPES & set(row.get("publication_types") or []):
        return "clinical_trial"
    return row.get("news_type")


def study_record(row: dict[str, Any], origin: str) -> dict[str, Any]:
    row = {k: _iso(v) for k, v in row.items()}
    summary = {lang: {"kind": "fallback", "text": fallback_text(row, lang)}
               for lang in ("es", "en")}  # fmt: skip
    return {**row, "type": news_type(row), "url": original_url(row), "summary": summary,
            "origin": origin}  # fmt: skip


# --- the warehouse ----------------------------------------------------------------------

COLUMNS = """study_id, doi, pmid, pmcid, title, journal, published_on, entered_on, authors,
sources, review_status, species, integrity, integrity_notices, is_open_access, license,
publication_types, news_type, preprint_doi, published_doi"""


def latest(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """A slice of today's candidates covering every signal value and the trials: the two
    most recent of each (review, species) pair, plus every clinical trial."""
    rows = con.execute(f"""
        with c as (
            select {COLUMNS},
                row_number() over (partition by review_status, species
                                   order by published_on desc nulls last, study_id) as n
            from main.dim_study
            where news_candidate and not list_contains(sources, 'journals')
              -- mock-up only: noise is removed by step 14a, not run yet; among the studies
              -- with no species, keep those with a neuro word in the title
              and (species != 'unknown' or regexp_matches(lower(title),
                   'neur|brain|cereb|cortic|synap|cognit|memory|hippocamp|glia|axon'))
        )
        select * exclude (n) from c
        where n <= 2 or list_has_any(publication_types, ?)
        order by published_on desc nulls last, study_id
    """, [sorted(TRIAL_TYPES)]).fetchall()  # fmt: skip
    names = [d[0] for d in con.description]
    return [study_record(dict(zip(names, r, strict=True)), "warehouse") for r in rows]


def nature_science_cell(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = con.execute(f"""
        select {COLUMNS} from main.dim_study
        where list_contains(sources, 'journals') and is_neuro
        order by published_on desc nulls last, study_id
    """).fetchall()  # fmt: skip
    names = [d[0] for d in con.description]
    return [study_record(dict(zip(names, r, strict=True)), "warehouse") for r in rows]


def outlet_news(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Headline, outlet, language, date and link. The feed summary is not shown (only our
    own texts are published). ``story_id`` equals the item id until step 15 groups them."""
    rows = con.execute("""
        select n.news_item_id, n.outlet, n.feed, n.lang, n.url, n.title, n.published_at,
               n.story_id, n.news_type, f.license
        from main.fct_news_item n left join main.news_feeds f using (feed)
        where n.origin = 'outlet' and n.is_neuro
        order by n.published_at desc
        limit 14
    """).fetchall()
    names = [d[0] for d in con.description]
    return [{k: _iso(v) for k, v in zip(names, r, strict=True)} for r in rows]


def day_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Mock-up B's «number of the day»: today's neuro candidates by signal."""
    (row,) = con.execute("""
        select count(*),
            count(*) filter (where species in ('humans', 'both')),
            count(*) filter (where species in ('animals', 'both')),
            count(*) filter (where species = 'unknown'),
            count(*) filter (where review_status = 'preprint')
        from main.dim_study where news_candidate and entered_on = ?
    """, [AS_OF]).fetchall()  # fmt: skip
    return dict(zip(["total", "humans", "animals", "unknown", "preprints"], row, strict=True))


# --- S5 summaries -----------------------------------------------------------------------


def _text(el: ET.Element | None) -> str | None:
    return " ".join("".join(el.itertext()).split()) if el is not None else None


def s5_studies() -> list[dict[str, Any]]:
    run = json.loads(S5_RUN.read_text(encoding="utf-8"))
    meta = {}
    for art in ET.parse(S5_EFETCH).getroot().iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        pmid = cit.findtext("PMID")
        a = cit.find("Article")
        mesh = {_text(d) for d in cit.iterfind("MeshHeadingList/MeshHeading/DescriptorName")}
        species = ("both" if {"Humans", "Animals"} <= mesh else "humans" if "Humans" in mesh
                   else "animals" if "Animals" in mesh else "unknown")  # fmt: skip
        doi = art.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='doi']")
        pmc = art.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
        date = None
        for path in ("PubmedData/History/PubMedPubDate[@PubStatus='pubmed']",):
            if (d := art.find(path)) is not None:
                date = dt.date(int(d.findtext("Year")), int(d.findtext("Month")),
                               int(d.findtext("Day"))).isoformat()  # fmt: skip
        authors = [f"{x.findtext('ForeName') or ''} {x.findtext('LastName') or ''}".strip()
                   for x in a.iterfind("AuthorList/Author") if x.findtext("LastName")]  # fmt: skip
        meta[pmid] = {
            "study_id": f"pubmed:{pmid}", "pmid": pmid, "doi": doi, "pmcid": pmc,
            "title": _text(a.find("ArticleTitle")), "journal": a.findtext("Journal/Title"),
            "published_on": date, "entered_on": date, "authors": authors,
            "sources": ["pubmed"], "review_status": "journal", "species": species,
            "integrity": "none", "integrity_notices": [], "license": None,
            "publication_types": [_text(p) for p in a.iterfind(
                "PublicationTypeList/PublicationType")],
            "news_type": None,
        }  # fmt: skip
    out = []
    for art in run["articles"]:
        row = meta[art["pmid"]]
        rec = study_record(row, "s5")
        if art["status"] == "published":
            for lang in ("es", "en"):
                rec["summary"][lang] = {
                    "kind": "verified", "sentences": art[lang],
                    "generator": run["writer"], "judge": run["judge"],
                }  # fmt: skip
        else:  # rejected by the judge or failed: the site shows the fallback
            for lang in ("es", "en"):
                rec["summary"][lang]["why"] = art["status"]
                rec["summary"][lang]["reason"] = (art.get("judge") or {}).get("reason")
        out.append(rec)
    return out


# --- build-time requests (cached) -------------------------------------------------------


def notice_examples(client) -> dict[str, dict[str, Any]]:
    out = {}
    for state, (doi, kind) in NOTICE_EXAMPLES.items():
        msg = _cached(f"crossref-{doi.replace('/', '_')}.json",
                      lambda doi=doi: get_json(client, f"https://api.crossref.org/works/{doi}")[
                          "message"])  # fmt: skip
        notice = next(u for u in _notices() if u["doi"] == doi)
        parts = (msg.get("published") or msg.get("issued") or {}).get("date-parts", [[None]])[0]
        published = dt.date(*parts).isoformat() if len(parts) == 3 else None
        row = {
            "study_id": f"doi:{doi}", "doi": doi, "pmid": None, "pmcid": None,
            "title": (msg.get("title") or [None])[0],
            "journal": (msg.get("container-title") or [None])[0],
            "published_on": published, "entered_on": None,
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in msg.get("author", [])],
            "sources": ["crossref"], "review_status": "journal", "species": None,
            "integrity": state, "integrity_notices": [f"{kind} {notice['notice']} "
                                                      f"({notice['date']})"],
            "license": None, "publication_types": [], "news_type": None,
        }  # fmt: skip
        out[state] = study_record(row, "crossref")
    return out


def _notices() -> list[dict[str, str]]:
    import os

    raw = Path(os.environ["SYN_DATA_DIR"]) / "raw/crossref/notices"
    out = []
    for f in sorted(raw.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            p = json.loads(line)["payload"]
            out += [{"doi": u["doi"], "notice": p["doi"], "date": u["date"], "type": u["type"]}
                    for u in p["updates"]]  # fmt: skip
    return out


def anniversary(client) -> dict[str, Any] | None:
    data = _cached("wikidata-born-11-12.json", lambda: get_json(
        client, WIKIDATA, params={"query": SPARQL, "format": "json"}))  # fmt: skip
    rows = data["results"]["bindings"]
    if not rows:
        return None
    r = rows[0]
    val = lambda k: r[k]["value"] if k in r else None  # noqa: E731
    return {"qid": val("p").rsplit("/", 1)[1], "name_es": val("es"), "name_en": val("en"),
            "desc_es": val("des"), "desc_en": val("den"), "born": val("born")[:10],
            "license": "CC0 1.0 (Wikidata)"}  # fmt: skip


# --- main -------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", type=Path, required=True)
    args = ap.parse_args()
    con = duckdb.connect(str(args.warehouse), read_only=True)
    s5 = s5_studies()
    published = [s for s in s5 if s["summary"]["en"]["kind"] == "verified"]
    with make_client() as client:
        examples = notice_examples(client)
        born = anniversary(client)
    # Mock-up A's fact: one verified sentence, rotating with the date of the build.
    pick = published[AS_OF.toordinal() % len(published)]
    n = AS_OF.toordinal() % len(pick["summary"]["en"]["sentences"])
    data = {
        "as_of": AS_OF.isoformat(),
        "week": WEEK,
        "latest": latest(con),
        "s5": s5,
        "nsc": nature_science_cell(con),
        "news": outlet_news(con),
        "examples": examples,
        "facts": {
            "a": {
                "study_id": pick["study_id"],
                "es": pick["summary"]["es"]["sentences"][n],
                "en": pick["summary"]["en"]["sentences"][n],
            },
            "b": day_counts(con),
            "c": born,
        },
        "weekly": {lang: weekly_fallback(WEEK, s5, lang) for lang in ("es", "en")},
    }
    out = HERE / "data/mockup.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"{out}: {len(data['latest'])} latest, {len(s5)} S5 ({len(published)} verified), "
        f"{len(data['nsc'])} NSC, {len(data['news'])} news; anniversary: "
        f"{born and born['name_en']}"
    )


if __name__ == "__main__":
    main()
