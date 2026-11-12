"""Topics of each piece for the mock-up (SCOPE v81; option B, chosen by Aday): placeholders
until there is more news, but built on a controlled vocabulary instead of title words.

* Each topic is a set of MeSH branches (``TOPICS``). The descriptors under them and their
  entry terms (MeSH synonyms) come from NLM's MeSH SPARQL endpoint, cached in
  ``data/sources/mesh/`` (committed, like the other small metadata caches; MeSH is free
  to use, courtesy of the U.S. National Library of Medicine) so a rerun needs no network.
* A study indexed with MeSH (PubMed, or Europe PMC's MeSH names) gets the topics of its
  descriptors: basis ``mesh``.
* Otherwise (new PubMed records are not indexed yet, preprints never are) the entry terms
  are searched in the title, the author keywords and the abstract: basis ``text``. The
  abstract is read from the local cache only to tag; it is never written anywhere.
* Media news only have a title: basis ``text``.
* Measured: the text rule is also run on the indexed studies and compared with their MeSH
  topics (precision and recall per topic), so we know how far to trust ``text``.

Output: ``data/topics.json`` (topic tags per study and per news URL, the vocabulary
summary and the measurement). No abstract text, no LLM.

    SYN_DATA_DIR=<scratch>/real uv run python spikes/web/topics.py --warehouse <db>
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import duckdb

from synaptica.http import get_json, make_client
from synaptica.narrative.sources import abstract_for

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
CACHE = HERE / "data/sources/mesh"
S5_EFETCH = ROOT / "data/cache/s5/pubmed/efetch_20261102.xml"
SPARQL = "https://id.nlm.nih.gov/mesh/sparql"

# Topic -> MeSH tree numbers (each with everything under it). Placeholders (Aday, v81).
TOPICS: dict[str, list[str]] = {
    "memory": ["F02.463.425.540"],  # Memory
    # Substance-Related Disorders; Behavior, Addictive
    "addiction": ["F03.900", "F01.145.527.100.120"],
    "neurodegeneration": ["C10.574"],  # Neurodegenerative Diseases
    "neuroinflammation": ["C10.586"],  # Neuroinflammatory Diseases
    "sleep": ["F02.830.855", "F03.870"],  # Sleep; Sleep Wake Disorders
    "emotion": ["F01.470"],  # Emotions (Sofía confirms the topic, v13)
}  # fmt: skip

# Text matches that are not the topic: immune memory is not Memory.
EXCLUDE = re.compile(r"memory (?:[tb][ -]?cells?|lymphocytes?)|immun\w* memory", re.I)
MIN_TERM = 4  # shorter entry terms are acronyms that collide with other words
# Entry terms that are also common English words (measured: «affect» was almost always the
# verb, 8 of the 12 false Emotion tags).
COMMON = {"affect"}
# One passing mention in an abstract is not the topic (measured: every Neurodegeneration
# tag with one mention was false; with two or more, none). The title and author keywords
# count with one.
MIN_MENTIONS = 2


def sparql(client: Any, tree: str) -> list[dict[str, str]]:
    """Every descriptor under a tree number, with all its entry terms (cached)."""
    path = CACHE / f"{tree}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    query = f"""PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?d ?name ?term FROM <http://id.nlm.nih.gov/mesh> WHERE {{
  ?d a meshv:TopicalDescriptor ; rdfs:label ?name ; meshv:treeNumber ?t .
  ?t rdfs:label ?tn . FILTER(?tn = "{tree}" || STRSTARTS(?tn, "{tree}."))
  ?d (meshv:preferredConcept|meshv:concept) ?c . ?c (meshv:preferredTerm|meshv:term) ?x .
  ?x meshv:prefLabel ?term .
}} ORDER BY ?d ?term"""
    rows: list[dict[str, str]] = []
    offset = 0
    while True:
        doc = get_json(client, SPARQL, params={"query": query, "format": "JSON",
                                               "limit": 1000, "offset": offset})  # fmt: skip
        got = [{"ui": b["d"]["value"].rsplit("/", 1)[1], "name": b["name"]["value"],
                "term": b["term"]["value"]} for b in doc["results"]["bindings"]]  # fmt: skip
        rows += got
        if len(got) < 1000:
            break
        offset += 1000
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def vocabulary() -> dict[str, dict[str, Any]]:
    with make_client() as client:
        out = {}
        for topic, trees in TOPICS.items():
            rows = [r for tree in trees for r in sparql(client, tree)]
            out[topic] = {
                "trees": trees,
                "uis": sorted({r["ui"] for r in rows}),
                "names": sorted({r["name"] for r in rows}),
                # Inverted («Memory, Long-Term») and qualified («Recognition (Psychology)»)
                # forms never appear in prose.
                "terms": sorted(
                    {
                        r["term"]
                        for r in rows
                        if len(r["term"]) >= MIN_TERM
                        and ", " not in r["term"]
                        and "(" not in r["term"]
                        and r["term"].lower() not in COMMON
                    }
                ),
            }
    return out


def text_matcher(vocab: dict[str, dict[str, Any]]) -> Any:
    """Topic -> regex of its entry terms (whole words, any case, optional plural)."""
    rx = {}
    for topic, v in vocab.items():
        terms = sorted(v["terms"], key=len, reverse=True)
        alt = "|".join(re.escape(t) for t in terms)
        rx[topic] = re.compile(rf"(?<![\w-])(?:{alt})(?:s|es)?(?![\w-])", re.I)

    def topics(head: str, body: str = "") -> set[str]:
        """Topics of a piece: one mention in ``head`` (title, keywords) or MIN_MENTIONS in
        all of it (``body`` is the abstract)."""
        head, body = EXCLUDE.sub(" ", head), EXCLUDE.sub(" ", body)
        return {
            t
            for t, r in rx.items()
            if r.search(head) or len(r.findall(head + " " + body)) >= MIN_MENTIONS
        }

    return topics


def s5_mesh() -> dict[str, set[str]]:
    """MeSH UIs of the S5 studies (efetch cache), keyed by PMID."""
    if not S5_EFETCH.exists():
        return {}
    out = {}
    for art in ET.parse(S5_EFETCH).getroot().iter("PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        uis = {d.get("UI") for d in art.iter("DescriptorName")}
        if pmid and uis:
            out[pmid] = uis
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", required=True)
    args = ap.parse_args()
    vocab = vocabulary()
    by_ui = {ui: t for t, v in vocab.items() for ui in v["uis"]}
    by_name = {n.lower(): t for t, v in vocab.items() for n in v["names"]}
    match = text_matcher(vocab)

    con = duckdb.connect(args.warehouse, read_only=True)
    rel = con.sql("""
        select s.*, coalesce(p.mesh_uis, []) as mesh_uis, coalesce(p.keywords, []) as keywords,
               coalesce(e.mesh_names, []) as mesh_names
        from dim_study s
        left join int_pubmed__records p on p.pmid = s.pmid
        left join (select doi, flatten(list(mesh_names)) as mesh_names
                   from stg_europepmc__records where doi is not null group by doi) e
          on e.doi = s.doi
    """)  # fmt: skip
    rows = [dict(zip(rel.columns, r, strict=True)) for r in rel.fetchall()]
    mockup = json.loads((HERE / "data/mockup.json").read_text(encoding="utf-8"))
    shown = {s["study_id"]: s for s in mockup["latest"] + mockup["s5"] + mockup["nsc"]}
    s5 = s5_mesh()

    studies: dict[str, list[list[str]]] = {}
    pairs = []  # (mesh topics, text topics) of indexed candidates
    in_wh = set()
    for r in rows:
        in_wh.add(r["study_id"])
        if not (r["news_candidate"] or r["study_id"] in shown):
            continue
        mesh = {by_ui[u] for u in r["mesh_uis"] if u in by_ui}
        mesh |= {by_name[n.lower()] for n in r["mesh_names"] if n.lower() in by_name}
        indexed = bool(len(r["mesh_uis"]) or len(r["mesh_names"]))
        found = abstract_for({k: r[k] for k in ("pmid", "doi", "pmcid")} |
                             {"sources": list(r["sources"])})  # fmt: skip
        txt = match(" ".join([r["title"] or "", *r["keywords"]]), found[0] if found else "")
        if indexed and r["news_candidate"]:
            pairs.append((mesh, txt, match(r["title"] or "")))
        basis, found_topics = ("mesh", mesh) if indexed else ("text", txt)
        studies[r["study_id"]] = [[t, basis] for t in sorted(found_topics)]
    # Shown studies not in this warehouse (S5): their efetch MeSH, else the title.
    for sid, s in shown.items():
        if sid in in_wh:
            continue
        uis = s5.get(s.get("pmid") or "")
        if uis:
            studies[sid] = [[t, "mesh"] for t in sorted({by_ui[u] for u in uis if u in by_ui})]
        else:
            studies[sid] = [[t, "text"] for t in sorted(match(s["title"] or ""))]
    news = {n["url"]: [[t, "text"] for t in sorted(match(n["title"]))] for n in mockup["news"]}

    def score(i: int) -> dict[str, dict[str, float | int]]:
        out = {}
        for t in TOPICS:
            tp = sum(t in p[0] and t in p[i] for p in pairs)
            fp = sum(t not in p[0] and t in p[i] for p in pairs)
            fn = sum(t in p[0] and t not in p[i] for p in pairs)
            out[t] = {"mesh": tp + fn, "tp": tp, "fp": fp, "fn": fn,
                      "precision": round(tp / (tp + fp), 2) if tp + fp else None,
                      "recall": round(tp / (tp + fn), 2) if tp + fn else None}  # fmt: skip
        return out

    cand = [r for r in rows if r["news_candidate"]]
    tagged = [studies[r["study_id"]] for r in cand]
    summary = {
        "candidates": len(cand),
        "indexed": len(pairs),
        "by_basis": {b: sum(any(x[1] == b for x in tg) for tg in tagged) for b in ("mesh", "text")},
        "with_topic": sum(bool(tg) for tg in tagged),
        "per_topic": {t: sum(any(x[0] == t for x in tg) for tg in tagged) for t in TOPICS},
        "text_vs_mesh": score(1),
        "title_only_vs_mesh": score(2),
    }
    out = {
        "as_of": mockup["as_of"],
        "vocabulary": {
            t: {"trees": v["trees"], "descriptors": len(v["uis"]), "terms": len(v["terms"])}
            for t, v in vocab.items()
        },
        "measure": summary,
        "studies": {k: v for k, v in studies.items() if k in shown},
        "news": news,
    }
    (HERE / "data/topics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")  # fmt: skip
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
