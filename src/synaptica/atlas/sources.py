"""Sources for the texts of Neuro Atlas's regions and the diseases related to each, by
pair of the rat ↔ human table (step 5 of the plan of 2026-11-17; nothing is published).

* ``sources.json``: per pair, the Wikidata item of its MeSH descriptor (property P486,
  MeSH descriptor ID) and the lead of that item's Wikipedia article in English and
  Spanish (:mod:`synaptica.wiki`), the source a region's text will be written from.
* ``diseases.json``: per pair, the Wikidata items whose anatomical location (P927) is the
  region and that are a disease (an instance or subclass of Q12136). **Not shown on the
  site** until Sofía answers row 16 of the questions sheet (does she review each list?).

By hand (``syn atlas sources``), never in the daily pipeline; Wikidata is CC0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from synaptica.atlas.studies import matcher, region_terms
from synaptica.http import Throttle
from synaptica.store import utc_today
from synaptica.wiki import LICENCE, LeadsResult, leads, qid, read_json, wikidata, write_json

HERE = Path(__file__).parent
SOURCES = HERE / "sources.json"
DISEASES = HERE / "diseases.json"
DISEASE = "Q12136"


@dataclass
class AtlasSourcesResult:
    leads: LeadsResult = field(default_factory=LeadsResult)
    items: int = 0
    diseases: dict[str, int] = field(default_factory=dict)
    ambiguous: list[str] = field(default_factory=list)


def items_by_mesh(client: httpx.Client, uis: list[str], throttle: Throttle) -> list[dict]:
    """Wikidata items with one of these MeSH descriptor IDs, and their article titles."""
    values = " ".join(f'"{u}"' for u in sorted(uis))
    rows = wikidata(client, f"""SELECT ?mesh ?item ?en WHERE {{ VALUES ?mesh {{ {values} }}
  ?item wdt:P486 ?mesh .
  OPTIONAL {{ ?page schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ;
              schema:name ?en }} }} ORDER BY ?mesh ?item""", throttle)  # fmt: skip
    return [{"mesh": r["mesh"], "item": qid(r["item"]), "en": r.get("en")} for r in rows]


def diseases_of(client: httpx.Client, qids: list[str], throttle: Throttle) -> list[dict]:
    """Diseases located (P927) in these items, with their English and Spanish labels. In
    two queries, the second walking up from each candidate (``gearing forward``): the
    class path to «disease» times out otherwise."""
    values = " ".join(f"wd:{q}" for q in sorted(qids))
    located = wikidata(client, f"""SELECT ?item ?d ?en ?es WHERE {{ VALUES ?item {{ {values} }}
  ?d wdt:P927 ?item .
  OPTIONAL {{ ?d rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?d rdfs:label ?es FILTER(LANG(?es) = "es") }} }} ORDER BY ?item ?d""",
                       throttle)  # fmt: skip
    if not located:
        return []
    candidates = " ".join(sorted({f"wd:{qid(r['d'])}" for r in located}))
    sick = {qid(r["d"]) for r in wikidata(client, f"""SELECT DISTINCT ?d WHERE {{
  VALUES ?d {{ {candidates} }} ?d (wdt:P31|wdt:P279)/wdt:P279* wd:{DISEASE} .
  hint:Prior hint:gearing "forward" . }}""",
                                          throttle)}  # fmt: skip
    return [{"item": qid(r["item"]), "qid": qid(r["d"]), "en": r.get("en"), "es": r.get("es")}
            for r in located if qid(r["d"]) in sick]  # fmt: skip


def update(
    client: httpx.Client,
    *,
    sources_path: Path | None = None,
    diseases_path: Path | None = None,
    refresh: bool = False,
    throttle: Throttle | None = None,
) -> AtlasSourcesResult:
    """Both files, for every pair of region_terms.toml. Idempotent: the same Wikipedia
    revisions and Wikidata answers write the same files."""
    sources_path, diseases_path = sources_path or SOURCES, diseases_path or DISEASES
    throttle = throttle or Throttle(1)
    result = AtlasSourcesResult()
    terms = region_terms()
    kind_of = {u: k for k, us in terms.items() for u in us}
    found = items_by_mesh(client, list(kind_of), throttle)
    result.items = len(found)
    per_kind: dict[str, list[dict[str, Any]]] = {}
    for r in found:
        per_kind.setdefault(kind_of[r["mesh"]], []).append(r)
    # One article per pair: a MeSH ID on two items is reported, never guessed between.
    chosen: dict[str, dict[str, Any]] = {}
    for kind, rs in per_kind.items():
        with_page = [r for r in rs if r["en"]]
        if len(with_page) == 1:
            chosen[kind] = with_page[0]
        else:
            result.ambiguous.append(f"{kind}: {[r['item'] for r in rs]}")
    old = read_json(sources_path, "pairs")
    patterns = matcher().patterns
    wanted = {k: (r["en"], patterns[k]) for k, r in chosen.items()
              if refresh or k not in old or old[k].get("wikidata") != r["item"]}  # fmt: skip
    got = leads(client, wanted, {k: v.get("leads", {}) for k, v in old.items()}, utc_today(),
                throttle, result.leads)  # fmt: skip
    pairs = {}
    for kind in terms:
        if kind in got:
            pairs[kind] = {"wikidata": chosen[kind]["item"], "leads": got[kind]}
        elif kind in old and kind in chosen and old[kind].get("wikidata") == chosen[kind]["item"]:
            pairs[kind] = old[kind]
    write_json(sources_path, {
        "note": "Source of each Neuro Atlas pair's text: the Wikidata item of its MeSH "
        "descriptor (P486) and the lead of its Wikipedia article at the revision given. "
        "Written by `syn atlas sources`; do not edit by hand.",
        "licence": LICENCE + "; Wikidata: CC0",
        "pairs": pairs,
    })  # fmt: skip
    rows = diseases_of(client, [r["item"] for r in chosen.values()], throttle)
    item_kind = {r["item"]: k for k, r in chosen.items()}
    diseases: dict[str, list[dict[str, Any]]] = {k: [] for k in chosen}
    for r in rows:
        diseases[item_kind[r["item"]]].append({k: r[k] for k in ("qid", "en", "es")})
    result.diseases = {k: len(v) for k, v in diseases.items()}
    write_json(diseases_path, {
        "note": "Diseases whose anatomical location (Wikidata P927) is each pair's region, "
        "an instance or subclass of disease (Q12136). NOT PUBLISHED until Sofía answers "
        "row 16 of the questions sheet. Written by `syn atlas sources`.",
        "licence": "Wikidata: CC0",
        "pairs": {k: diseases[k] for k in terms if k in diseases},
    })  # fmt: skip
    return result
