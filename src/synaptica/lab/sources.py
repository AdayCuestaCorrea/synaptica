"""The source of each Neuro Lab technique's texts: the lead of its Wikipedia article in
English and Spanish (B2-4, step 5 of the plan of 2026-11-17), kept in ``sources.json``
next to this module, as the glossary does (``synaptica.glossary.sources``: the texts are
checked against them in Actions, where a local cache would not exist).

Since v214 (Aday's option A of 2026-11-18 for the «limits» their leads leave empty), a
technique with ``limits_section_en`` in its table row also keeps that section of the same
article, at the same revision as its lead (``limits_en``): its «limits» are then written
from it. Since v245, ``limits_pmc`` and ``limits_pmc_section`` instead take that section
from a PMC article (:mod:`synaptica.lab.pmc`): its text is kept here only under an open
licence, else in the cache, with its hash here. Since v253, ``protocol_section_en`` keeps
another section of the article, at the lead's revision (``protocol_en``), that the
technique's protocol is written from (Sofía's sheet, row 15).

By hand (``syn lab sources``), never in the daily pipeline. No LLM: this only stores the
sources a text will be written from.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from synaptica.glossary.sources import PERMALINK, _same, fetch_leads
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
    cache_root: Path | None = None,
) -> LeadsResult:
    """Look up the techniques without a source (all with ``refresh``); a lead counts only
    if it names the technique (its MeSH entry terms or its words). Idempotent."""
    path = path or SOURCES
    old = read_json(path, "techniques")
    patterns = matcher().patterns
    rows = {t["id"]: t for t in techniques()}
    sources = {k: v for k, v in old.items() if k in rows}
    # v227: a technique whose article lead never names it takes one section instead.
    sectioned = {k for k, t in rows.items() if t.get("source_section_en")}
    wanted = {k: (t["source_en"], patterns[k]) for k, t in rows.items()
              if k not in sectioned and (refresh or k not in sources)}  # fmt: skip
    result = LeadsResult()
    throttle = throttle or Throttle(2)
    sources |= leads(client, wanted, old, utc_today(), throttle, result)
    for k in sorted(sectioned):
        en = (sources.get(k) or {}).get("en") or {}
        if refresh or en.get("section") != rows[k]["source_section_en"]:  # asked once
            got = _section_source(client, rows[k], patterns[k], old.get(k), throttle, result)
            if got is not None:
                sources[k] = got
    for k, t in rows.items():
        if k in sources:
            prev = (old.get(k) or {}).get("limits_en")
            if t.get("limits_pmc"):
                _pmc_limits(client, t, sources[k], None if refresh else prev, throttle,
                            result, cache_root)  # fmt: skip
            else:
                _limits(client, t, sources[k], prev, throttle, result)
            _limits(client, t, sources[k], (old.get(k) or {}).get("protocol_en"), throttle,
                    result, field="protocol_section_en", key="protocol_en")  # fmt: skip
    write_json(path, {
        "note": "Source of each Neuro Lab technique: the lead of its Wikipedia article at the "
        "revision given (oldid). Written by `syn lab sources`; do not edit by hand.",
        "licence": LICENCE,
        "techniques": {k: sources[k] for k in rows if k in sources},
    })  # fmt: skip
    return result


def _section_source(
    client: httpx.Client,
    tech: dict[str, Any],
    pattern: re.Pattern[str],
    old: dict[str, Any] | None,
    throttle: Throttle,
    result: LeadsResult,
) -> dict[str, Any] | None:
    """The source of a technique whose article lead never names it (perfusion, v227): the
    section ``source_section_en`` of ``source_en`` at the article's current revision,
    stored as its lead (with ``section``), only if the section names the technique. No
    Spanish source: the Spanish article is about the whole subject."""
    heading, title = tech["source_section_en"], tech["source_en"]
    result.asked += 1
    try:
        page = fetch_leads(client, "en", [title], throttle)[title]
        text = (fetch_section(client, "en", page["revid"], heading, throttle)
                if page.get("title") and page.get("revid") else None)  # fmt: skip
    except HttpError as exc:
        result.failed.append(f"{tech['id']}: {exc}")
        return None
    ok = bool(text and pattern.search(text))
    if not ok:
        result.failed.append(f"{tech['id']}: no section «{heading}» naming it in «{title}»")
    en: dict[str, Any] = {"title": page.get("title"), "accepted": ok, "section": heading}
    if ok:
        en |= {"revid": page["revid"], "url": PERMALINK.format(lang="en", revid=page["revid"]),
               "retrieved": utc_today().isoformat(), "lead": text}  # fmt: skip
    prev = (old or {}).get("en")
    if _same(prev, en):
        en = prev  # type: ignore[assignment]
    result.accepted["en"] += ok
    new = {"en": en, "es": {"title": None, "accepted": False}}
    result.changed += new != {k: v for k, v in (old or {}).items() if k in ("en", "es")}
    return new


def _limits(
    client: httpx.Client,
    tech: dict[str, Any],
    entry: dict[str, Any],
    old: dict[str, Any] | None,
    throttle: Throttle,
    result: LeadsResult,
    field: str = "limits_section_en",
    key: str = "limits_en",
) -> None:
    """Keep ``key`` (``limits_en``, or ``protocol_en`` from ``protocol_section_en``, v253)
    in step with the English lead: the same revision, or none."""
    heading, en = tech.get(field), entry.get("en") or {}
    entry.pop(key, None)
    if not heading or not en.get("accepted"):
        result.changed += old is not None  # no longer wanted: dropped
        return
    if old and old.get("revid") == en["revid"] and old.get("heading") == heading:
        entry[key] = old  # the same revision: not asked again
        return
    try:
        text = fetch_section(client, "en", en["revid"], heading, throttle)
    except HttpError as exc:
        result.failed.append(f"{tech['id']} «{heading}»: {exc}")
        return
    if text is None:  # renamed or removed in this revision: no source, the gap stays
        result.failed.append(f"{tech['id']}: no section «{heading}» in revision {en['revid']}")
        return
    entry[key] = {"heading": heading, "revid": en["revid"], "url": en["url"],
                  "retrieved": utc_today().isoformat(), "text": text}  # fmt: skip
    result.sections += 1
    result.changed += 1


def _pmc_limits(
    client: httpx.Client,
    tech: dict[str, Any],
    entry: dict[str, Any],
    old: dict[str, Any] | None,
    throttle: Throttle,
    result: LeadsResult,
    cache_root: Path | None,
) -> None:
    """``limits_en`` from a section of a PMC article (v245): asked once (``refresh`` asks
    again); its text here only under an open licence, else to the cache."""
    from synaptica.lab import pmc

    pmcid, heading = tech["limits_pmc"], tech["limits_pmc_section"]
    entry.pop("limits_en", None)
    if old and old.get("pmcid") == pmcid and old.get("heading") == heading:
        entry["limits_en"] = old
        return
    try:
        text = pmc.section_text(pmc.fetch_xml(client, pmcid, throttle), heading)
        cite = pmc.citation(client, pmcid, throttle)
    except HttpError as exc:
        result.failed.append(f"{tech['id']} {pmcid}: {exc}")
        return
    if text is None:  # no such section, or the publisher does not allow its full text
        result.failed.append(f"{tech['id']}: no section «{heading}» in {pmcid}")
        return
    licence = cite.pop("licence")
    new = {"source": "pmc", "pmcid": pmcid, "heading": heading,
           "url": pmc.ARTICLE.format(pmcid=pmcid), "citation": cite, "licence": licence,
           "retrieved": utc_today().isoformat(), "sha256": pmc.sha256(text),
           "words": len(text.split())}  # fmt: skip
    if pmc.is_open(licence):
        new["text"] = text
    elif cache_root is not None:
        pmc.store(cache_root, new, text)
    entry["limits_en"] = new
    result.sections += 1
    result.changed += 1
