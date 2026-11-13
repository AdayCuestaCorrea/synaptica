"""Feed parsing shared by the journal (step 6) and news (step 7) ingestion.

Copied and adapted from paleo-atlas ``src/paleo/ingest/news.py`` (same author, AGPL in
both; decision D2): ``canonical_url``, ``item_key``, ``_text`` and ``_date`` unchanged;
``parse_feed`` also reads RSS 1.0 (RDF), which Nature, Science and Cell serve, and the
Dublin Core / PRISM fields they carry (DOI, authors, section). The feed's own summary is
returned only when the caller asks for it (licences differ per feed).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
PRISM_NAMESPACES = (
    "{http://prismstandard.org/namespaces/basic/2.0/}",
    "{http://prismstandard.org/namespaces/1.2/basic/}",
)
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|src$|rss$|af$)", re.I)
DOI = re.compile(r"10\.\d{4,9}/[^\s<\"?#]+")


def canonical_url(url: str) -> str:
    """The article's link without tracking parameters or fragment, on https, so the
    same article keeps one key whichever feed it came from."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)])
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    return urlunsplit((scheme, parts.netloc.lower(), parts.path, query, ""))


def item_key(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]


def _text(value: str | None) -> str:
    """Plain text: tags stripped, entities decoded, spaces collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _date(value: str | None) -> str | None:
    """RFC 822 (RSS), ISO 8601 (Atom, Dublin Core) or a bare date → ISO 8601 in UTC."""
    if not value:
        return None
    value = value.strip()
    try:
        when = email.utils.parsedate_to_datetime(value)
    except TypeError, ValueError:
        try:
            when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            match = re.match(r"\d{4}-\d{2}-\d{2}", value)  # Cell: 2026-11-05-08:00
            if not match:
                return None
            when = dt.datetime.fromisoformat(match.group())
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return when.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _prism(item: ET.Element, name: str) -> str | None:
    for ns in PRISM_NAMESPACES:
        if (value := item.findtext(ns + name)) is not None:
            return value
    return None


def find_doi(*values: str | None) -> str | None:
    """First DOI in the values (``doi:10.1038/x``, a URL, a bare DOI), in lower case."""
    for value in values:
        if value and (match := DOI.search(value)):
            return match.group().rstrip(".").lower()
    return None


def parse_feed(body: str, *, keep_summary: bool = False) -> list[dict[str, Any]]:
    """The items of an RSS 2.0, RSS 1.0 (RDF) or Atom feed: url, title, published (UTC),
    doi, authors, section and, only with ``keep_summary``, the feed's summary."""
    root = ET.fromstring(body)
    raw = []
    for item in [*root.iter("item"), *root.iter(RSS1 + "item")]:  # RSS 2.0 and RSS 1.0
        find = lambda n, i=item: i.findtext(n) or i.findtext(RSS1 + n)  # noqa: E731
        link = (find("link") or find("guid") or item.get(
            "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or "").strip()  # fmt: skip
        raw.append({
            "link": link,
            "title": find("title") or item.findtext(DC + "title"),
            "published": find("pubDate") or item.findtext(DC + "date")
            or _prism(item, "publicationDate") or _prism(item, "coverDate"),
            "doi": find_doi(_prism(item, "doi"), item.findtext(DC + "identifier"), link),
            "authors": [_text(c.text) for c in item.iter(DC + "creator") if _text(c.text)],
            "section": _prism(item, "section") or item.findtext(DC + "type"),
            "summary": find("description"),
        })  # fmt: skip
    for entry in root.iter(ATOM + "entry"):
        links = entry.findall(ATOM + "link")
        link = next((a.get("href") for a in links if a.get("rel", "alternate") == "alternate"),
                    links[0].get("href") if links else "")  # fmt: skip
        raw.append({
            "link": link or "",
            "title": entry.findtext(ATOM + "title"),
            "published": entry.findtext(ATOM + "published") or entry.findtext(ATOM + "updated"),
            "doi": None,
            "authors": [_text(a.findtext(ATOM + "name")) for a in entry.iter(ATOM + "author")
                        if _text(a.findtext(ATOM + "name"))],
            "section": None,
            "summary": entry.findtext(ATOM + "summary"),
        })  # fmt: skip
    out = []
    for r in raw:
        if not r["link"] or not _text(r["title"]):
            continue
        payload = {
            "url": canonical_url(r["link"]),
            "title": _text(r["title"]),
            "published": _date(r["published"]),
            "doi": r["doi"],
            "authors": r["authors"],
            "section": _text(r["section"]) or None,
        }
        if keep_summary and _text(r["summary"]):
            payload["summary"] = _text(r["summary"])
        out.append(payload)
    return out
