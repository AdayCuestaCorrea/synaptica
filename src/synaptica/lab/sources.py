"""The source of each Neuro Lab technique's texts: the lead of its Wikipedia article in
English and Spanish (B2-4, step 5 of the plan of 2026-11-17), kept in ``sources.json``
next to this module, as the glossary does (``synaptica.glossary.sources``: the texts are
checked against them in Actions, where a local cache would not exist).

By hand (``syn lab sources``), never in the daily pipeline. No LLM: this only stores the
sources a text will be written from.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from synaptica.http import Throttle
from synaptica.lab.studies import matcher, techniques
from synaptica.store import utc_today
from synaptica.wiki import LICENCE, LeadsResult, leads, read_json, write_json

SOURCES = Path(__file__).with_name("sources.json")


def update_sources(
    client: httpx.Client,
    *,
    path: Path | None = None,
    refresh: bool = False,
    throttle: Throttle | None = None,
) -> LeadsResult:
    """Look up the techniques without a source (all with ``refresh``); a lead counts only
    if it names the technique (its MeSH entry terms or its words). Idempotent."""
    path = path or SOURCES
    old = read_json(path, "techniques")
    patterns = matcher().patterns
    rows = {t["id"]: t for t in techniques()}
    sources = {k: v for k, v in old.items() if k in rows}
    wanted = {k: (t["source_en"], patterns[k]) for k, t in rows.items()
              if refresh or k not in sources}  # fmt: skip
    result = LeadsResult()
    sources |= leads(client, wanted, old, utc_today(), throttle or Throttle(2), result)
    write_json(path, {
        "note": "Source of each Neuro Lab technique: the lead of its Wikipedia article at the "
        "revision given (oldid). Written by `syn lab sources`; do not edit by hand.",
        "licence": LICENCE,
        "techniques": {k: sources[k] for k in rows if k in sources},
    })  # fmt: skip
    return result
