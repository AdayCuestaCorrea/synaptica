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
from collections.abc import Callable, Iterator
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
    """Every descriptor under ``tree``, itself included, with each of its tree numbers and
    entry terms, sorted (so a fetch with no change in MeSH writes the same file). Tree labels
    carry a language tag (``"…"@en``), so the equality compares ``STR(?tn)``: without it the
    descriptor of ``tree`` itself was left out (found in Neuro Lab's measurement, v201)."""
    query = f"""PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?d ?name ?tn ?term FROM <http://id.nlm.nih.gov/mesh> WHERE {{
  ?d a meshv:TopicalDescriptor ; rdfs:label ?name ; meshv:treeNumber ?t .
  ?t rdfs:label ?tn . FILTER(STR(?tn) = "{tree}" || STRSTARTS(?tn, "{tree}."))
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


@functools.cache
def region_text() -> dict[str, list[str]]:
    """Pair kind → Sofía's own words for it (``text`` in region_terms.toml, copied by hand
    from her correction): found in a study's text like the MeSH entry terms, never taken
    as MeSH (the ``mesh`` list holds only IDs of the fetched vocabulary)."""
    path = resources.files("synaptica.atlas") / "region_terms.toml"
    return {r["kind"]: list(r.get("text", []))
            for r in tomllib.loads(path.read_text("utf-8"))["region"]}  # fmt: skip


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

    def __init__(
        self,
        rows: list[dict[str, str]],
        terms: dict[str, list[str]],
        text: dict[str, list[str]] | None = None,
    ) -> None:
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
        for kind, ws in (text or {}).items():  # hers: any length, she chose them
            words.setdefault(kind, set()).update(ws)
        self.patterns = {}
        for kind, ws in sorted(words.items()):
            alt = "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True))
            self.patterns[kind] = re.compile(rf"(?<![\w-])(?:{alt})(?:s|es)?(?![\w-])", re.I)

    def mesh(self, uis: list[str], names: list[str]) -> set[str]:
        return {self.by_ui[u] for u in uis if u in self.by_ui} | {
            self.by_name[n.lower()] for n in names if n.lower() in self.by_name
        }

    def text(self, head: str, body: str = "", min_mentions: int = MIN_MENTIONS) -> set[str]:
        """Pairs named in the title or keywords (``head``), or ``min_mentions`` times in
        head and abstract together."""
        both = head + " " + body
        return {
            k
            for k, rx in self.patterns.items()
            if rx.search(head) or len(rx.findall(both)) >= min_mentions
        }


@functools.cache
def matcher() -> Matcher:
    return Matcher(vocabulary(), region_terms(), region_text())


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
    out: dict[str, list[dict[str, Any]]] = {}
    for row, uis, kw, mesh_names in _rows(warehouse, columns):
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


def _rows(
    warehouse: Path, columns: tuple[str, ...]
) -> Iterator[tuple[dict[str, Any], list[str], list[str], list[str]]]:
    """The neuroscience studies that are not noise, newest first: (row, MeSH UIs, keywords,
    MeSH names)."""
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
    for values in rows:
        row = dict(zip(names, values, strict=True))
        yield row, row.pop("_uis"), row.pop("_kw"), row.pop("_names")


# ---- measuring the abstract rule (A2.2) ----------------------------------------------

THRESHOLDS = (1, 2, 3)
SHOWN_IDS = 15  # PMIDs per list in the report: public IDs, never text


def measure(
    warehouse: Path,
    *,
    cache_root: Path | None = None,
    abstract: Callable[..., Any] = abstract_for,
    match: Matcher | None = None,
) -> dict[str, Any]:
    """How the text rule (:data:`MIN_MENTIONS` in the abstract) would behave at 1, 2 or 3
    mentions, with the abstracts of the private cache (A2.2). Two measures, only counts:

    - ``check``: on the studies that have MeSH and an abstract in the cache, the text rule
      against MeSH (what the pages use for them): per threshold, pairs it finds that MeSH
      also gives (``tp``), pairs MeSH does not give (``fp``) and pairs it misses (``fn``);
    - ``text``: on the studies without MeSH (where the rule is used), studies found per
      pair at each threshold, and the PMIDs that move between 2 and 1 or 2 and 3.

    Nothing of an abstract is returned: the CI log is public."""
    match = match or matcher()
    cols = ("study_id", "pmid", "doi", "pmcid", "sources", "title")
    out: dict[str, Any] = {"studies": 0, "with_mesh": 0, "with_mesh_abstract": 0,
                           "without_mesh": 0, "without_mesh_abstract": 0,
                           "check": {n: {"tp": 0, "fp": 0, "fn": 0} for n in THRESHOLDS},
                           "text": {n: {} for n in THRESHOLDS},
                           "only_at_1": [], "lost_at_3": []}  # fmt: skip
    for row, uis, kw, mesh_names in _rows(warehouse, cols):
        out["studies"] += 1
        has_mesh = bool(uis or mesh_names)
        out["with_mesh" if has_mesh else "without_mesh"] += 1
        text = abstract({k: row.get(k) for k in ("pmid", "doi", "pmcid", "sources")},
                        cache_root=cache_root)  # fmt: skip
        body = text[0] if text else ""
        if body:
            out["with_mesh_abstract" if has_mesh else "without_mesh_abstract"] += 1
        head = " ".join([row["title"] or "", *kw])
        found = {n: match.text(head, body, n) for n in THRESHOLDS}
        if has_mesh:
            if not body:
                continue
            truth = match.mesh(uis, mesh_names)
            for n, kinds in found.items():
                c = out["check"][n]
                c["tp"] += len(kinds & truth)
                c["fp"] += len(kinds - truth)
                c["fn"] += len(truth - kinds)
            continue
        for n, kinds in found.items():
            for kind in kinds:
                out["text"][n][kind] = out["text"][n].get(kind, 0) + 1
        ident = row["pmid"] or row["study_id"]
        for kind in sorted(found[1] - found[2]):
            out["only_at_1"].append(f"{ident} {kind}")
        for kind in sorted(found[2] - found[3]):
            out["lost_at_3"].append(f"{ident} {kind}")
    return out


def measure_markdown(m: dict[str, Any]) -> str:
    """The measure as a short Markdown report (counts and PMIDs only)."""
    lines = [
        "## Neuro Atlas: the abstract rule (A2.2)",
        "",
        f"Neuroscience studies (not noise): {m['studies']}. With MeSH: {m['with_mesh']} "
        f"({m['with_mesh_abstract']} with an abstract in the cache). Without MeSH: "
        f"{m['without_mesh']} ({m['without_mesh_abstract']} with an abstract in the cache).",
        "",
        "### Text rule against MeSH (studies with both)",
        "",
        "| Mentions | Found, MeSH agrees | Found, MeSH does not | Missed | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for n, c in m["check"].items():
        p = f"{c['tp'] / (c['tp'] + c['fp']):.2f}" if c["tp"] + c["fp"] else "n/a"
        r = f"{c['tp'] / (c['tp'] + c['fn']):.2f}" if c["tp"] + c["fn"] else "n/a"
        lines.append(f"| {n} | {c['tp']} | {c['fp']} | {c['fn']} | {p} | {r} |")
    kinds = sorted({k for per in m["text"].values() for k in per})
    lines += ["", "### Studies without MeSH found per pair", "",
              "| Pair | " + " | ".join(f"≥ {n} in the abstract" for n in THRESHOLDS) + " |",
              "|---" * (len(THRESHOLDS) + 1) + "|"]  # fmt: skip
    for k in kinds:
        lines.append(f"| {k} | " + " | ".join(str(m["text"][n].get(k, 0)) for n in THRESHOLDS)
                     + " |")  # fmt: skip
    for key, label in (("only_at_1", "Found with 1 mention, not with 2"),
                       ("lost_at_3", "Found with 2 mentions, not with 3")):  # fmt: skip
        ids = m[key]
        more = f" (and {len(ids) - SHOWN_IDS} more)" if len(ids) > SHOWN_IDS else ""
        lines += ["", f"{label}: {len(ids)}{more}"]
        if ids:
            lines += ["", *(f"- {i}" for i in ids[:SHOWN_IDS])]
    return "\n".join(lines) + "\n"


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
    rows, terms, text = vocabulary(), region_terms(), region_text()
    items = []
    for pair in pairs["pair"]:
        kind = pair["kind"]
        words: list[str] = []
        for ui in terms[kind]:
            mine = [r for r in rows if r["ui"] == ui]
            for w in [mine[0]["name"], *sorted({r["term"] for r in mine})]:
                if w not in words:
                    words.append(w)
        # Her words are part of what she approves: a new one changes the hash, so the item
        # goes back to her queue to confirm the copy (A2.1, Aday's option a).
        words += [w for w in text.get(kind, []) if w not in words]
        examples = [s["title"] for s in (found or {}).get(kind, [])[:EXAMPLES]]
        human = ", ".join(pair["human"])
        items.append(ReviewItem(
            item_type=ItemType.SEARCH_TERMS, item_id=f"waxholm-{pair['waxholm']}",
            title_es=f"{rat_names.get(pair['waxholm'], pair['waxholm'])} (rata) ↔ {human}",
            content=TermsContent(region=f"waxholm-{pair['waxholm']}", terms=words,
                                 examples=examples),
        ))  # fmt: skip
    return items


def reviewed(review_dir: Path | None) -> dict[str, str]:
    """Pair kind → the date Sofía approved its search terms («Están bien»), only for the
    table as it is today: ``state`` compares the hash, so a later change of the pair's row
    (a new descriptor, her words copied in) brings the item back and the pair is a proposal
    again until she approves it. A correction («Corregir») leaves the pair a proposal until
    Aday copies it into region_terms.toml and she approves that version (A2.1, option a)."""
    from synaptica.review.apply import read_log, state

    if review_dir is None or not review_dir.exists():
        return {}
    events = read_log(review_dir)
    pairs = tomllib.loads((resources.files("synaptica.atlas") / "pairs.toml").read_text("utf-8"))
    kinds = {f"waxholm-{p['waxholm']}": p["kind"] for p in pairs["pair"]}
    out = {}
    for item in review_items():
        st = state(item, events)
        if st.status == "decided" and st.terms is None and st.reviewed_at is not None:
            out[kinds[item.item_id]] = st.reviewed_at.date().isoformat()
    return out
