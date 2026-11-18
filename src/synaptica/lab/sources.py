"""The source of each Neuro Lab technique's texts: the lead of its Wikipedia article in
English and Spanish (B2-4, step 5 of the plan of 2026-11-17), kept in ``sources.json``
next to this module, as the glossary does (``synaptica.glossary.sources``: the texts are
checked against them in Actions, where a local cache would not exist).

Since v214 (Aday's option A of 2026-11-18 for the «limits» their leads leave empty), a
technique with ``limits_section_en`` in its table row also keeps that section of the same
article, at the same revision as its lead (``limits_en``): its «limits» are then written
from it.

By hand (``syn lab sources``), never in the daily pipeline. No LLM: this only stores the
sources a text will be written from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from synaptica.http import HttpError, Throttle
from synaptica.lab.studies import matcher, techniques
from synaptica.store import utc_today
from synaptica.wiki import LICENCE, LeadsResult, fetch_section, leads, read_json, write_json

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
    throttle = throttle or Throttle(2)
    sources |= leads(client, wanted, old, utc_today(), throttle, result)
    for k, t in rows.items():
        if k in sources:
            _limits(client, t, sources[k], (old.get(k) or {}).get("limits_en"), throttle, result)
    write_json(path, {
        "note": "Source of each Neuro Lab technique: the lead of its Wikipedia article at the "
        "revision given (oldid). Written by `syn lab sources`; do not edit by hand.",
        "licence": LICENCE,
        "techniques": {k: sources[k] for k in rows if k in sources},
    })  # fmt: skip
    return result


def _limits(
    client: httpx.Client,
    tech: dict[str, Any],
    entry: dict[str, Any],
    old: dict[str, Any] | None,
    throttle: Throttle,
    result: LeadsResult,
) -> None:
    """Keep ``limits_en`` in step with the English lead: the same revision, or none."""
    heading, en = tech.get("limits_section_en"), entry.get("en") or {}
    entry.pop("limits_en", None)
    if not heading or not en.get("accepted"):
        return
    if old and old.get("revid") == en["revid"] and old.get("heading") == heading:
        entry["limits_en"] = old  # the same revision: not asked again
        return
    try:
        text = fetch_section(client, "en", en["revid"], heading, throttle)
    except HttpError as exc:
        result.failed.append(f"{tech['id']} «{heading}»: {exc}")
        return
    if text is None:  # renamed or removed in this revision: no source, the gap stays
        result.failed.append(f"{tech['id']}: no section «{heading}» in revision {en['revid']}")
        return
    entry["limits_en"] = {"heading": heading, "revid": en["revid"], "url": en["url"],
                          "retrieved": utc_today().isoformat(), "text": text}  # fmt: skip
    result.sections += 1
    result.changed += 1
