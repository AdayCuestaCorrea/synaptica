"""Studies of each rat ↔ human pair of Neuro Atlas (SCOPE §7, «Qué hemos aprendido en
animales»; Aday's choices of v188: per pair, every neuroscience study of the warehouse,
the table not published).

The pair → MeSH table is :file:`region_terms.toml` (a proposal for Sofía). The MeSH
descriptors of the brain (tree A08.186.211) and their entry terms are in
:file:`mesh/A08.186.211.json`, from NLM's MeSH SPARQL endpoint (``syn atlas mesh``, by
hand; never in the pipeline). The fetch is copied from the web mock-up's
``spikes/web/topics.py`` (``sparql``), adding the tree number of each row.

A study goes to a pair as in :mod:`synaptica.news.topics`:

* indexed with MeSH (PubMed, or Europe PMC's names): the pairs of its descriptors (basis
  ``mesh``);
* otherwise (new PubMed records, preprints): an entry term in the title or the author
  keywords, or :data:`MIN_MENTIONS` in the abstract read from the private cache (basis
  ``text``). Nothing of the abstract is written anywhere.

Measured on 2026-11-16 (5463 neuroscience studies, 2145 with MeSH; titles and keywords
only, no abstracts locally): of 19 text matches on indexed studies that MeSH did not give,
almost all were right (MeSH does not tag every region a study names).
"""

from __future__ import annotations

import functools
import json
import re
import tomllib
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import duckdb
import httpx

from synaptica.http import get_json
from synaptica.narrative.sources import abstract_for
from synaptica.review.models import ItemType, ReviewItem, TermsContent

SPARQL = "https://id.nlm.nih.gov/mesh/sparql"
TREE = "A08.186.211"  # Brain
MIN_TERM = 4  # shorter entry terms are acronyms that collide with other words
MIN_MENTIONS = 2  # one passing mention in an abstract is not the region (as in topics)
PAGE = 1000


def vocabulary_path() -> Path:
    return Path(str(resources.files("synaptica.atlas") / "mesh" / f"{TREE}.json"))


def fetch(client: httpx.Client, tree: str = TREE) -> list[dict[str, str]]:
    """Every descriptor under ``tree`` with each of its tree numbers and entry terms, sorted
    (so a fetch with no change in MeSH writes the same file)."""
    query = f"""PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?d ?name ?tn ?term FROM <http://id.nlm.nih.gov/mesh> WHERE {{
  ?d a meshv:TopicalDescriptor ; rdfs:label ?name ; meshv:treeNumber ?t .
  ?t rdfs:label ?tn . FILTER(?tn = "{tree}" || STRSTARTS(?tn, "{tree}."))
  ?d (meshv:preferredConcept|meshv:concept) ?c . ?c (meshv:preferredTerm|meshv:term) ?x .
  ?x meshv:prefLabel ?term .
}} ORDER BY ?d ?tn ?term"""
    rows: set[tuple[str, str, str, str]] = set()
    offset = 0
    while True:
        doc = get_json(client, SPARQL, params={"query": query, "format": "JSON",
                                               "limit": PAGE, "offset": offset})  # fmt: skip
        got = doc["results"]["bindings"]
        rows |= {(b["d"]["value"].rsplit("/", 1)[1], b["name"]["value"], b["tn"]["value"],
                  b["term"]["value"]) for b in got}  # fmt: skip
        if len(got) < PAGE:
            break
        offset += PAGE
    return [dict(zip(("ui", "name", "tree", "term"), r, strict=True)) for r in sorted(rows)]


def write_vocabulary(rows: list[dict[str, str]], path: Path | None = None) -> bool:
    """Write the vocabulary; True when it changed."""
    path = path or vocabulary_path()
    text = json.dumps(rows, ensure_ascii=False, indent=0) + "\n"
    if path.exists() and path.read_text("utf-8") == text:
        return False
    path.write_text(text, "utf-8")
    return True


@functools.cache
def vocabulary() -> list[dict[str, str]]:
    return json.loads(vocabulary_path().read_text("utf-8"))


@functools.cache
def region_terms() -> dict[str, list[str]]:
    """Pair kind → its MeSH descriptor UIs (the proposal in region_terms.toml)."""
    path = resources.files("synaptica.atlas") / "region_terms.toml"
    return {r["kind"]: r["mesh"] for r in tomllib.loads(path.read_text("utf-8"))["region"]}


def descriptor_kinds(rows: list[dict[str, str]], terms: dict[str, list[str]]) -> dict[str, str]:
    """Descriptor UI → pair kind: under a root descriptor of the table, the most specific
    root winning (the longest tree number that contains it)."""
    trees: dict[str, set[str]] = {}
    for r in rows:
        trees.setdefault(r["ui"], set()).add(r["tree"])
    roots = [(t, kind) for kind, uis in terms.items() for ui in uis for t in trees.get(ui, ())]
    out = {}
    for ui, numbers in trees.items():
        best: tuple[int, str] | None = None
        for t in numbers:
            for root, kind in roots:
                inside = t == root or t.startswith(root + ".")
                if inside and (best is None or len(root) > best[0]):
                    best = (len(root), kind)
        if best:
            out[ui] = best[1]
    return out


class Matcher:
    """Which pairs a study is about, by its MeSH or its text."""

    def __init__(self, rows: list[dict[str, str]], terms: dict[str, list[str]]) -> None:
        self.by_ui = descriptor_kinds(rows, terms)
        self.by_name = {r["name"].lower(): self.by_ui[r["ui"]] for r in rows
                        if r["ui"] in self.by_ui}  # fmt: skip
        words: dict[str, set[str]] = {}
        for r in rows:
            kind = self.by_ui.get(r["ui"])
            term = r["term"]
            # Inverted («Cortex, Motor») and qualified forms never appear in prose.
            if kind and len(term) >= MIN_TERM and ", " not in term and "(" not in term:
                words.setdefault(kind, set()).add(term)
        self.patterns = {}
        for kind, ws in sorted(words.items()):
            alt = "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True))
            self.patterns[kind] = re.compile(rf"(?<![\w-])(?:{alt})(?:s|es)?(?![\w-])", re.I)

    def mesh(self, uis: list[str], names: list[str]) -> set[str]:
        return {self.by_ui[u] for u in uis if u in self.by_ui} | {
            self.by_name[n.lower()] for n in names if n.lower() in self.by_name
        }

    def text(self, head: str, body: str = "") -> set[str]:
        both = head + " " + body
        return {
            k
            for k, rx in self.patterns.items()
            if rx.search(head) or len(rx.findall(both)) >= MIN_MENTIONS
        }


@functools.cache
def matcher() -> Matcher:
    return Matcher(vocabulary(), region_terms())


def pair_studies(
    warehouse: Path,
    columns: tuple[str, ...],
    *,
    cache_root: Path | None = None,
    abstract: Callable[..., Any] = abstract_for,
    match: Matcher | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Pair kind → its neuroscience studies that are not noise (``columns`` of ``dim_study``
    plus ``basis``), newest first. Abstracts only from the cache: no client, so never the
    network."""
    match = match or matcher()
    with duckdb.connect(str(warehouse), read_only=True) as con:
        have = {r[0] for r in con.execute(
            "select table_name from information_schema.tables").fetchall()}  # fmt: skip
        pubmed = "int_pubmed__records" in have
        epmc = "stg_europepmc__records" in have
        empty = "[]::varchar[]"
        cols = ", ".join(f"s.{c}" for c in columns)
        rows = con.execute(
            f"select {cols}, "
            f"{'coalesce(p.mesh_uis, [])' if pubmed else empty} as _uis, "
            f"{'coalesce(p.keywords, [])' if pubmed else empty} as _kw, "
            f"{'coalesce(e.mesh_names, [])' if epmc else empty} as _names "
            "from dim_study s "
            + ("left join int_pubmed__records p on p.pmid = s.pmid " if pubmed else "")
            + ("left join (select doi, flatten(list(mesh_names)) as mesh_names "
               "from stg_europepmc__records where doi is not null group by doi) e "
               "on e.doi = s.doi " if epmc else "")
            # Not what the classifier of Neuro News called noise (Aday, v191).
            + "where s.is_neuro and s.title is not null "
            "and coalesce(s.news_type, '') != 'noise' "
            "order by s.entered_on desc, least(s.published_on, s.entered_on) desc nulls last, "
            "s.study_id"
        ).fetchall()  # fmt: skip
    names = [*columns, "_uis", "_kw", "_names"]
    out: dict[str, list[dict[str, Any]]] = {}
    for values in rows:
        row = dict(zip(names, values, strict=True))
        uis, kw, mesh_names = row.pop("_uis"), row.pop("_kw"), row.pop("_names")
        if uis or mesh_names:
            kinds, basis = match.mesh(uis, mesh_names), "mesh"
        else:
            text = abstract({k: row.get(k) for k in ("pmid", "doi", "pmcid", "sources")},
                            cache_root=cache_root)  # fmt: skip
            kinds = match.text(" ".join([row["title"] or "", *kw]), text[0] if text else "")
            basis = "text"
        for kind in sorted(kinds):
            out.setdefault(kind, []).append(row | {"basis": basis})
    return out


SPECIES_GROUPS = ("humans", "animals", "both", "unknown")


def by_species(studies: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """The four groups in order, each with up to ``cap`` studies and how many are left out;
    an empty group is left out."""
    groups = []
    for sp in SPECIES_GROUPS:
        mine = [s for s in studies if (s.get("species") or "unknown") == sp]
        if mine:
            groups.append({"species": sp, "studies": mine[:cap], "more": len(mine) - cap
                           if len(mine) > cap else 0, "total": len(mine)})  # fmt: skip
    return groups


# ---- Sofía's queue (v190, option 1 of Aday) ---------------------------------------------

EXAMPLES = 3


def review_items(found: dict[str, list[dict[str, Any]]] | None = None) -> list[ReviewItem]:
    """One ``search_terms`` item per pair, in the order of pairs.toml: the names and entry
    terms of its MeSH descriptors and a few studies they find today (``found``, from
    :func:`pair_studies`). She approves, or corrects the list; her correction goes into
    region_terms.toml by hand (Aday's option 1, v190)."""
    from synaptica.config import project_root

    pairs = tomllib.loads((resources.files("synaptica.atlas") / "pairs.toml").read_text("utf-8"))
    # The rat region's name, from the viewer's data (pairs.toml only keeps its id).
    built = project_root() / "site" / "static" / "atlas" / "pairs.json"
    rat_names = {p["waxholm"]["id"]: p["waxholm"]["name"]
                 for p in json.loads(built.read_text("utf-8"))["pairs"]}  # fmt: skip
    rows, terms = vocabulary(), region_terms()
    items = []
    for pair in pairs["pair"]:
        kind = pair["kind"]
        words: list[str] = []
        for ui in terms[kind]:
            mine = [r for r in rows if r["ui"] == ui]
            for w in [mine[0]["name"], *sorted({r["term"] for r in mine})]:
                if w not in words:
                    words.append(w)
        examples = [s["title"] for s in (found or {}).get(kind, [])[:EXAMPLES]]
        human = ", ".join(pair["human"])
        items.append(ReviewItem(
            item_type=ItemType.SEARCH_TERMS, item_id=f"waxholm-{pair['waxholm']}",
            title_es=f"{rat_names.get(pair['waxholm'], pair['waxholm'])} (rata) ↔ {human}",
            content=TermsContent(region=f"waxholm-{pair['waxholm']}", terms=words,
                                 examples=examples),
        ))  # fmt: skip
    return items
