"""A section of a PMC article as the source of a Neuro Lab technique's «limits» (v245).

Sofía named one review for each technique whose Wikipedia article says nothing of its
limits (sheet row 40, 2026-11-24). No openly licensed review matched hers (v242), so hers
are the sources; Aday's choice for the ones without an open licence (2026-11-25): **like
the PubMed abstracts**. The repository keeps the PMCID, the section heading, the citation,
the licence and the SHA-256 of the section's text; the text itself is committed only when
the licence lets it be shared (a Creative Commons one, as Wikipedia). Otherwise it lives in
``data/cache/lab/pmc/`` (never committed): fetched when the text is drafted, and again
where her edits are checked (``syn review sweep`` in Actions), accepted only if its hash is
the stored one. Facts are taken from it and written in our own words, with a link; no
sentence is copied (the 8-word check). Only an edit of hers that cites one reaches the
network (:func:`warm`); everything else reads the repository or the cache.

Full text from NCBI E-utilities (``efetch``, ``db=pmc``), which serves the author
manuscripts too; citation and licence from Europe PMC's metadata. A publisher that forbids
the XML download (the chemogenetics review, Wiley) leaves the technique without a source:
its gap stays.
"""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from synaptica.http import HttpError, Throttle, get_json, get_text
from synaptica.ingest.pubmed import base_params

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARTICLE = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_open(licence: str | None) -> bool:
    """A Creative Commons licence: its text may be committed (NC and ND included: shared
    whole, not for profit, with its credit)."""
    return bool(licence) and licence.lower().startswith("cc")


def section_text(xml: str, heading: str) -> str | None:
    """The plain text of the body section titled ``heading`` (its subsections included):
    one paragraph per line, the titles of its subsections as their own lines; figures,
    tables and references left out. None when the article has no such section (or the
    publisher does not allow its full text)."""
    root = ET.fromstring(xml)
    body = root.find(".//body")
    if body is None:
        return None
    for sec in body.iter("sec"):
        if (sec.findtext("title") or "").strip() == heading:
            lines: list[str] = []
            _lines(sec, lines, top=True)
            text = "\n".join(x for x in lines if x)
            return text or None
    return None


def _lines(sec: ET.Element, out: list[str], top: bool = False) -> None:
    for child in sec:
        if (child.tag == "title" and not top) or child.tag == "p":
            out.append(_flat(child))
        elif child.tag == "sec":
            _lines(child, out)
        elif child.tag == "list":
            out += [_flat(i) for i in child.iter("list-item")]


def _flat(el: ET.Element) -> str:
    skip = {"xref", "fig", "table-wrap", "fn"}
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag in skip:
            parts.append(e.tail or "")
            return
        parts.append(e.text or "")
        for c in e:
            walk(c)
        if e is not el:
            parts.append(e.tail or "")

    walk(el)
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    text = re.sub(r"[(\[][\s,;\u2013-]*[)\]]", "", text)  # what the removed citations leave
    return re.sub(r"\s+([,.;:)\]])", r"\1", text)


def fetch_xml(client: httpx.Client, pmcid: str, throttle: Throttle) -> str:
    throttle.wait()
    params = base_params(os.environ.get("NCBI_API_KEY")) | {"db": "pmc", "id": pmcid,
                                                            "retmode": "xml"}  # fmt: skip
    return get_text(client, EFETCH, params=params)


def citation(client: httpx.Client, pmcid: str, throttle: Throttle) -> dict[str, Any]:
    """Title, authors, journal, year, DOI and licence (None: no open licence) of the
    article, from Europe PMC."""
    throttle.wait()
    body = get_json(client, EPMC, params={"query": f"PMCID:{pmcid}", "resultType": "core",
                                          "format": "json"})  # fmt: skip
    r = ((body.get("resultList") or {}).get("result") or [{}])[0]
    journal = (r.get("journalInfo") or {}).get("journal") or {}
    return {"title": r.get("title"), "authors": r.get("authorString"),
            "journal": journal.get("medlineAbbreviation") or journal.get("title"),
            "year": r.get("pubYear"), "doi": r.get("doi"),
            "licence": r.get("license")}  # fmt: skip


def cache_path(cache_root: Path, entry: dict[str, Any]) -> Path:
    return cache_root / "lab" / "pmc" / f"{entry['pmcid']}-{entry['sha256'][:16]}.txt"


def store(cache_root: Path, entry: dict[str, Any], text: str) -> None:
    path = cache_path(cache_root, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def text_of(entry: dict[str, Any], cache_root: Path | None,
            client: httpx.Client | None = None,
            throttle: Throttle | None = None) -> str | None:  # fmt: skip
    """The section's text: committed (open licence), else from the cache, else fetched
    when a ``client`` is given (and cached); only if its hash is the stored one. None when
    it cannot be had: whatever needs it waits (a draft, or the check of her edit)."""
    if entry.get("text") is not None:
        return entry["text"]
    if cache_root is not None:
        path = cache_path(cache_root, entry)
        if path.exists() and sha256(text := path.read_text("utf-8")) == entry["sha256"]:
            return text
    if client is None:
        return None
    try:
        got = section_text(fetch_xml(client, entry["pmcid"], throttle or Throttle(3)),
                           entry["heading"])  # fmt: skip
    except HttpError, ET.ParseError:
        return None
    if got is None or sha256(got) != entry["sha256"]:
        return None  # changed or gone: never checked against another text
    if cache_root is not None:
        store(cache_root, entry, got)
    return got


def label(entry: dict[str, Any]) -> str:
    """How her card and the site cite it: «title», authors, journal year, section."""
    c = entry["citation"]
    return (
        f"«{c['title']}» {c['authors']} {c['journal']} {c['year']} ({entry['pmcid']}), "
        f"sección «{entry['heading']}»"
    )


def warm(cache_root: Path, sources_path: Path | None = None,
         client: httpx.Client | None = None) -> list[str]:  # fmt: skip
    """Fetch into the cache the PMC sections kept out of the repository that it lacks
    (``review.intake.run``, only when an edit of hers cites one, so it is checked like any
    other). Returns what could not be had; that Issue then waits (exit 2)."""
    from synaptica.http import make_client
    from synaptica.lab.sources import SOURCES
    from synaptica.wiki import read_json

    wanted = [e for t in read_json(sources_path or SOURCES, "techniques").values()
              if (e := t.get("limits_en")) and e.get("source") == "pmc"
              and e.get("text") is None and text_of(e, cache_root) is None]  # fmt: skip
    if not wanted:
        return []
    own = client is None
    client = client or make_client()
    try:
        return [e["pmcid"] for e in wanted if text_of(e, cache_root, client) is None]
    finally:
        if own:
            client.close()
