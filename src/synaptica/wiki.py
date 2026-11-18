"""Wikipedia leads and Wikidata queries for the fixed texts of Phase 2 (Neuro Lab's
techniques, Neuro Atlas's regions), by hand and never in the daily pipeline.

Built on :func:`synaptica.glossary.sources.fetch_leads` (from Paleo Atlas) with the same
entry format as the glossary's ``sources.json`` (title, revision, permalink, lead), so a
text written later cites the exact revision it was checked against. Acceptance:

* English: the article exists, is not a disambiguation page and its lead names the thing
  (``pattern``);
* Spanish: the interlanguage link of an accepted English article, when it exists and is
  not a disambiguation page. The Spanish names of the regions are Sofía's to settle (sheet
  row 13), so the link between the two articles is the check, not words.

A thing without an accepted lead has no source in that language: a gap, never filled.
Wikipedia text is CC BY-SA 4.0 (its authors); Wikidata is CC0.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from synaptica.glossary.sources import (
    API,
    BATCH,
    LANGS,
    PERMALINK,
    _batches,
    _same,
    fetch_leads,
)
from synaptica.http import HttpError, Throttle, get_json
from synaptica.store import _atomic_write

WIKIDATA = "https://query.wikidata.org/sparql"
LICENCE = "Wikipedia text: CC BY-SA 4.0, its authors (see each article's history)"


@dataclass
class LeadsResult:
    asked: int = 0
    accepted: dict[str, int] = field(default_factory=lambda: {"en": 0, "es": 0})
    changed: int = 0
    failed: list[str] = field(default_factory=list)
    sections: int = 0  # article sections stored (Neuro Lab's «limits», v214)


def _entry(page: dict[str, Any], ok: bool, lang: str, today: dt.date) -> dict[str, Any]:
    entry: dict[str, Any] = {"title": page.get("title"), "accepted": ok}
    if ok:
        entry |= {"revid": page["revid"], "url": PERMALINK.format(lang=lang, revid=page["revid"]),
                  "retrieved": today.isoformat(), "lead": page["lead"]}  # fmt: skip
    return entry


def _real(page: dict[str, Any]) -> bool:
    return bool(page.get("title") and page.get("lead") and page.get("revid")
                and not page.get("disambiguation"))  # fmt: skip


def leads(
    client: httpx.Client,
    wanted: dict[str, tuple[str, re.Pattern[str]]],
    old: dict[str, dict[str, Any]],
    today: dt.date,
    throttle: Throttle,
    result: LeadsResult,
) -> dict[str, dict[str, Any]]:
    """key -> {lang: entry} for ``wanted`` (key -> English title and the pattern its lead
    must match). An entry at the same revision keeps its old ``retrieved``."""
    out: dict[str, dict[str, Any]] = {}
    keys = sorted(wanted)
    result.asked += len(keys)
    for batch in _batches(keys, BATCH):
        try:
            en = fetch_leads(client, "en", sorted({wanted[k][0] for k in batch}), throttle)
            ok_en = {k: _real(en[wanted[k][0]]) and bool(wanted[k][1].search(
                en[wanted[k][0]]["lead"])) for k in batch}  # fmt: skip
            es_titles = {k: en[wanted[k][0]]["es_title"] for k in batch
                         if ok_en[k] and en[wanted[k][0]].get("es_title")}  # fmt: skip
            es = (fetch_leads(client, "es", sorted(set(es_titles.values())), throttle)
                  if es_titles else {})  # fmt: skip
        except HttpError as exc:
            result.failed += [f"{k}: {exc}" for k in batch]
            continue
        for k in batch:
            page_es = es.get(es_titles.get(k, ""), {"title": None})
            new = {"en": _entry(en[wanted[k][0]], ok_en[k], "en", today),
                   "es": _entry(page_es, _real(page_es), "es", today)}  # fmt: skip
            for lang in LANGS:
                prev = (old.get(k) or {}).get(lang)
                if _same(prev, new[lang]):
                    new[lang] = prev
                result.accepted[lang] += new[lang]["accepted"]
            result.changed += new != old.get(k)
            out[k] = new
    return out


# ---- one section of an article, at a given revision (v214) ---------------------------

_SKIP = {"style", "script", "table", "sup", "figure", "math", "img"}
_SKIP_CLASS = ("mw-editsection", "reference", "hatnote", "mw-empty-elt", "thumb", "navbox")
_BLOCKS = {"p", "li", "dd"}
_VOID = {"br", "hr", "img", "wbr", "meta", "link", "input"}
_URL = re.compile(r"\s*https?://\S*[^\s.,;:)]")  # a bare link, not its full stop


class _Text(HTMLParser):
    """The prose of a parsed section: paragraphs and list items, without headings,
    references, tables, figures or bare links."""

    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self._buf: list[str] = []
        self._skip: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        cls = dict(attrs).get("class") or ""
        heading = tag.startswith("h") and tag[1:].isdigit()
        if self._skip or tag in _SKIP or heading or any(c in cls for c in _SKIP_CLASS):
            self._skip.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if self._skip:
            self._skip.pop()
        elif tag in _BLOCKS:
            text = _URL.sub("", re.sub(r"\s+", " ", "".join(self._buf))).strip()
            self._buf = []
            if text:
                self.paragraphs.append(text)

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._buf.append(data)


def section_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return "\n\n".join(parser.paragraphs)


def fetch_section(
    client: httpx.Client, lang: str, revid: int, heading: str, throttle: Throttle
) -> str | None:
    """The plain text of the section titled ``heading`` (with its subsections) at revision
    ``revid``, or None when that revision has no such section or it has no prose."""
    params = {"action": "parse", "format": "json", "formatversion": 2, "oldid": revid,
              "maxlag": 5}  # fmt: skip
    throttle.wait()
    body = get_json(client, API.format(lang=lang), params=params | {"prop": "sections"})
    if "error" in body:
        raise HttpError(f"Wikipedia ({lang}): {body['error'].get('code')}")
    index = next((s["index"] for s in body["parse"]["sections"] if s["line"] == heading), None)
    if index is None:
        return None
    throttle.wait()
    text = {"prop": "text", "section": index, "disableeditsection": 1, "disablelimitreport": 1}
    body = get_json(client, API.format(lang=lang), params=params | text)
    if "error" in body:
        raise HttpError(f"Wikipedia ({lang}): {body['error'].get('code')}")
    return section_text(body["parse"]["text"]) or None


def wikidata(client: httpx.Client, query: str, throttle: Throttle) -> list[dict[str, str]]:
    """Rows of a Wikidata SPARQL query, each variable to its plain value."""
    throttle.wait()
    body = get_json(client, WIKIDATA, params={"query": query, "format": "json"})
    return [{k: v["value"] for k, v in b.items()} for b in body["results"]["bindings"]]


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[1]


def write_json(path: Path, body: dict[str, Any]) -> bool:
    """Write when it changed; True if it did (the same data, the same file)."""
    text = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text("utf-8") == text:
        return False
    _atomic_write(path, text)
    return True


def read_json(path: Path, key: str) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))[key] if path.exists() else {}
