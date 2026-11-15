"""The source of each glossary term: the lead of its Wikipedia article, in English and
in Spanish.

Copied and adapted from Paleo Atlas, ``src/paleo/ingest/glossary.py`` (same author, AGPL).
Changes:

* the English article is named in ``terms.csv`` (``source_en``), not guessed from the
  term: acronyms such as PET or AD are disambiguation pages;
* acceptance uses the term's own forms (acronyms in their case, names in any case);
* the leads are kept in git, in ``sources.json`` next to this module, not in the local
  cache. They are CC BY-SA (shown with their title and revision on the site), and her
  review in Actions checks her texts against them: a cache the runner does not have
  would leave her edits waiting (the 2026-11-14 recovery of step 28, v150);
* run by hand (``syn glossary sources``), never in the daily pipeline, like
  ``syn atlas build``: a term's source changes only when someone asks.

A lead is accepted only if the article exists, is not a disambiguation page and its lead
names the term (one of its forms). A term without an accepted lead in a language has no
source there, and its text in that language cannot pass the checks: a gap, never filled.
Every source keeps its revision id, so a definition cites the exact text it was checked
against (``oldid`` link).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from synaptica.glossary import Term
from synaptica.http import HttpError, Throttle, get_json
from synaptica.store import _atomic_write, utc_today

API = "https://{lang}.wikipedia.org/w/api.php"
PERMALINK = "https://{lang}.wikipedia.org/w/index.php?oldid={revid}"
SOURCES = Path(__file__).with_name("sources.json")
BATCH = 20  # the most leads the API returns in one request (exlimit)
LANGS = ("en", "es")
LICENCE = "CC BY-SA 4.0"
log = logging.getLogger(__name__)


@dataclass
class SourcesResult:
    terms: int = 0
    asked: int = 0
    accepted: dict[str, int] = field(default_factory=lambda: {"en": 0, "es": 0})
    changed: int = 0
    failed: list[str] = field(default_factory=list)


def _batches(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_leads(
    client: httpx.Client, lang: str, titles: list[str], throttle: Throttle
) -> dict[str, dict[str, Any]]:
    """Asked title -> {title, revid, lead, disambiguation, es_title} (title None if the
    page does not exist). Redirects and normalised titles are followed."""
    params = {
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
        "titles": "|".join(titles), "prop": "extracts|revisions|pageprops|langlinks",
        "exintro": 1, "explaintext": 1, "exlimit": "max", "rvprop": "ids",
        "lllang": "es", "lllimit": "max", "maxlag": 5,
    }  # fmt: skip
    throttle.wait()
    body = get_json(client, API.format(lang=lang), params=params)
    if "error" in body:  # API errors come as 200 (maxlag is retried in http): never "no page"
        raise HttpError(f"Wikipedia ({lang}): {body['error'].get('code')}")
    query = body.get("query", {})
    final = {t: t for t in titles}
    for step in ("normalized", "redirects"):
        moves = {m["from"]: m["to"] for m in query.get(step, [])}
        final = {t: moves.get(f, f) for t, f in final.items()}
    pages = {p["title"]: p for p in query.get("pages", [])}
    out = {}
    for asked in titles:
        page = pages.get(final[asked], {})
        if not page or page.get("missing") or page.get("invalid"):
            out[asked] = {"title": None}
            continue
        links = page.get("langlinks") or []
        out[asked] = {
            "title": page["title"],
            "revid": (page.get("revisions") or [{}])[0].get("revid"),
            "lead": (page.get("extract") or "").strip(),
            "disambiguation": "disambiguation" in (page.get("pageprops") or {}),
            "es_title": links[0]["title"] if links else None,
        }
    return out


def accepted(page: dict[str, Any], term: Term) -> bool:
    """A real article whose lead names the term."""
    if not (page.get("title") and page.get("lead") and page.get("revid")):
        return False
    return not page.get("disambiguation") and bool(term.pattern.search(page["lead"]))


def load_sources(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """term_id -> {lang: source}; empty when nothing was looked up yet."""
    path = path or SOURCES
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))["terms"]


def _entry(page: dict[str, Any], term: Term, lang: str, today: dt.date) -> dict[str, Any]:
    ok = accepted(page, term)
    entry: dict[str, Any] = {"title": page.get("title"), "accepted": ok}
    if ok:
        entry |= {"revid": page["revid"], "url": PERMALINK.format(lang=lang, revid=page["revid"]),
                  "retrieved": today.isoformat(), "lead": page["lead"]}  # fmt: skip
    return entry


def _same(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    """Same source, whatever day it was looked up (keeps ``retrieved`` stable)."""
    strip = lambda e: {k: v for k, v in (e or {}).items() if k != "retrieved"}  # noqa: E731
    return strip(old) == strip(new)


def update_sources(
    client: httpx.Client,
    terms: list[Term],
    *,
    path: Path | None = None,
    refresh: bool = False,
    today: dt.date | None = None,
    throttle: Throttle | None = None,
) -> SourcesResult:
    """Look up the terms without a source (all of them with ``refresh``) and write
    ``sources.json``. Idempotent: a rerun asks for nothing new, and a lead at the same
    revision is not rewritten. Terms no longer in ``terms.csv`` are dropped."""
    path = path or SOURCES
    today = today or utc_today()
    throttle = throttle or Throttle(2)
    old = load_sources(path)
    known = {t.term_id for t in terms}
    sources = {k: v for k, v in old.items() if k in known}
    pending = [t for t in terms if refresh or t.term_id not in sources]
    result = SourcesResult(terms=len(terms), asked=len(pending))
    for batch in _batches(pending, BATCH):
        try:
            en = fetch_leads(client, "en", sorted({t.source_en for t in batch}), throttle)
            es_titles = {t.term_id: en[t.source_en]["es_title"] for t in batch
                         if en[t.source_en].get("es_title")}  # fmt: skip
            es = (fetch_leads(client, "es", sorted(set(es_titles.values())), throttle)
                  if es_titles else {})  # fmt: skip
        except HttpError as exc:
            log.warning("Wikipedia leads of %d terms failed: %s", len(batch), exc)
            result.failed += [t.term_id for t in batch]
            continue
        for t in batch:
            pages = {"en": en[t.source_en], "es": es.get(es_titles.get(t.term_id, ""), {})}
            new = {}
            for lang in LANGS:
                entry = _entry(pages[lang] or {"title": None}, t, lang, today)
                prev = (old.get(t.term_id) or {}).get(lang)
                new[lang] = prev if _same(prev, entry) else entry
                result.accepted[lang] += entry["accepted"]
            result.changed += new != old.get(t.term_id)
            sources[t.term_id] = new
    body = {
        "note": "Source of each Neuro Glossary term: the lead of its Wikipedia article at the "
        "revision given (oldid). Written by `syn glossary sources`; do not edit by hand.",
        "licence": f"Wikipedia text: {LICENCE}, its authors (see each article's history)",
        "terms": dict(sorted(sources.items())),
    }
    text = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text("utf-8") != text:
        _atomic_write(path, text)
    return result
