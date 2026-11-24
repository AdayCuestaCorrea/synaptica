"""Neuro Atlas regions -> Neuro Glossary terms (P6 of spike S3): touching or hovering over a
region's short name in the viewer shows its full name, its short name and, when the region
is a glossary term Sofía approved, its definition.

The viewer names a region by its atlas and short name (``site/static/viewer/viewer.js``,
``names``): the Waxholm acronym, or the Julich-Brain name before the brackets. Those are not
the glossary's acronyms (the subthalamic nucleus is ``STh`` in Waxholm, the accumbens comes
in two parts), so ``regions.csv`` maps them, one row per region:

* ``same``: the region is the term (Waxholm ``VTA`` -> VTA);
* ``part``: the region is a part of it (Waxholm ``NAc-c``, the core -> NAc).

Only the six glossary terms that are regions are mapped, and only where an atlas has the
structure under that name (PFC is many areas in both atlases: not mapped). The map is a name
match, read from the atlases' own labels; Sofía can correct it like any other item.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from synaptica.site.glossary import Glossary, with_full_stop

REGIONS = Path(__file__).with_name("regions.csv")
RELATIONS = ("same", "part")


def load_region_terms(path: Path | None = None) -> list[dict[str, str]]:
    with (path or REGIONS).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["relation"] not in RELATIONS:
            raise ValueError(f"{r['atlas']}:{r['short']}: unknown relation {r['relation']!r}")
    return rows


def atlas_index(gl: Glossary, page_url: str) -> dict[str, Any]:
    """What the viewer needs, for the published terms only: ``regions`` maps the viewer's
    ``atlas:short`` key to a term and relation; ``terms`` has each term's text (definition
    None while its English is still to be written); ``page`` is the glossary page."""
    regions = {f"{r['atlas']}:{r['short']}": {"term": r["term_id"], "relation": r["relation"]}
               for r in load_region_terms() if r["term_id"] in gl.entries}  # fmt: skip
    used = {v["term"] for v in regions.values()}
    terms = {key: {"term": gl.entries[key].term.term, "meaning": gl.meaning(key),
                   "definition": (None if (d := gl.entries[key].definition[gl.lang]) is None
                                  else with_full_stop(d))}
             for key in sorted(used)}  # fmt: skip
    return {"page": page_url, "regions": dict(sorted(regions.items())), "terms": terms}
