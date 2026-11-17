"""Studies of each Neuro Lab technique (SCOPE §7; Aday's options of v202: B2 option A, MeSH
and text with a gap where nothing is found; the table not published).

The technique → MeSH + words table is :file:`technique_terms.toml` (a proposal for Sofía).
The descriptors under its MeSH roots and their entry terms are in
:file:`mesh/techniques.json` (``syn lab mesh``, by hand; never in the pipeline), fetched
with :func:`synaptica.atlas.studies.fetch`.

Matching reuses :class:`synaptica.atlas.studies.Matcher`, with one difference measured in
B1 (docs/fases/fase-2-neuro-lab.md): a region is looked for in the text only when a study
has no MeSH, but a technique is looked for in the text of every study, because MeSH rarely
indexes the methods of recent records and some techniques have no descriptor at all. Text
means the title or keywords, or two mentions in title and abstract together, the abstract
read only from the private cache (so the counts of the web, built in Actions, are higher
than a local build's). Nothing of an abstract is written anywhere.
"""

from __future__ import annotations

import functools
import json
import tomllib
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import httpx

from synaptica.atlas import studies as atlas_studies
from synaptica.http import get_json
from synaptica.narrative.sources import abstract_for


def vocabulary_path() -> Path:
    return Path(str(resources.files("synaptica.lab") / "mesh" / "techniques.json"))


@functools.cache
def techniques() -> list[dict[str, Any]]:
    """The rows of technique_terms.toml, in its order (SCOPE §4's)."""
    path = resources.files("synaptica.lab") / "technique_terms.toml"
    return tomllib.loads(path.read_text("utf-8"))["technique"]


def terms() -> dict[str, list[str]]:
    return {t["id"]: list(t["mesh"]) for t in techniques()}


def text_terms() -> dict[str, list[str]]:
    return {t["id"]: list(t.get("text", [])) for t in techniques()}


def tree_numbers(client: httpx.Client, ui: str) -> list[str]:
    """The tree numbers of one descriptor (a technique may sit in two branches)."""
    query = f"""PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?tn FROM <http://id.nlm.nih.gov/mesh> WHERE {{
  <http://id.nlm.nih.gov/mesh/{ui}> meshv:treeNumber ?t . ?t rdfs:label ?tn .
}} ORDER BY ?tn"""
    doc = get_json(client, atlas_studies.SPARQL, params={"query": query, "format": "JSON"})
    return [b["tn"]["value"] for b in doc["results"]["bindings"]]


def fetch(client: httpx.Client) -> list[dict[str, str]]:
    """Every descriptor under the MeSH roots of the table, the roots included, with each
    tree number and entry term; sorted and without repeats (same MeSH, same file)."""
    rows: set[tuple[str, str, str, str]] = set()
    for ui in sorted({u for uis in terms().values() for u in uis}):
        for tree in tree_numbers(client, ui):
            rows |= {(r["ui"], r["name"], r["tree"], r["term"])
                     for r in atlas_studies.fetch(client, tree)}  # fmt: skip
    return [dict(zip(("ui", "name", "tree", "term"), r, strict=True)) for r in sorted(rows)]


def write_vocabulary(rows: list[dict[str, str]], path: Path | None = None) -> bool:
    return atlas_studies.write_vocabulary(rows, path or vocabulary_path())


@functools.cache
def vocabulary() -> list[dict[str, str]]:
    return json.loads(vocabulary_path().read_text("utf-8"))


def kept(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The vocabulary without each technique's ``exclude`` (with everything under them)
    and ``exclude_terms``."""
    out_ui = {u for t in techniques() for u in t.get("exclude", [])}
    out_terms = {w for t in techniques() for w in t.get("exclude_terms", [])}
    cut = {r["tree"] for r in rows if r["ui"] in out_ui}
    return [r for r in rows
            if not any(r["tree"] == c or r["tree"].startswith(c + ".") for c in cut)
            and r["term"] not in out_terms]  # fmt: skip


@functools.cache
def matcher() -> atlas_studies.Matcher:
    return atlas_studies.Matcher(kept(vocabulary()), terms(), text_terms())


def technique_studies(
    warehouse: Path,
    columns: tuple[str, ...],
    *,
    cache_root: Path | None = None,
    abstract: Callable[..., Any] = abstract_for,
    match: atlas_studies.Matcher | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Technique id → its neuroscience studies that are not noise (``columns`` of
    ``dim_study`` plus ``basis``: ``mesh`` when MeSH gives it, else ``text``), newest
    first. Abstracts only from the cache: no client, so never the network."""
    match = match or matcher()
    out: dict[str, list[dict[str, Any]]] = {}
    for row, uis, kw, mesh_names in atlas_studies._rows(warehouse, columns):
        by_mesh = match.mesh(uis, mesh_names)
        text = abstract({k: row.get(k) for k in ("pmid", "doi", "pmcid", "sources")},
                        cache_root=cache_root)  # fmt: skip
        by_text = match.text(" ".join([row["title"] or "", *kw]), text[0] if text else "")
        for tid in sorted(by_mesh | by_text):
            out.setdefault(tid, []).append(row | {"basis": "mesh" if tid in by_mesh else "text"})
    return out


def counts(found: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, int]]:
    """Per technique, in the table's order: studies found, and how many by MeSH and by text
    only (the measure of B2 option A, printed by ``syn site``; counts only)."""
    out = {}
    for t in techniques():
        mine = found.get(t["id"], [])
        mesh = sum(s["basis"] == "mesh" for s in mine)
        out[t["id"]] = {"studies": len(mine), "mesh": mesh, "text": len(mine) - mesh}
    return out
