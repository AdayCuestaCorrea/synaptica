"""The abstract a study is summarized from, read from the local cache only (step 16).

Abstracts are publisher text (CLAUDE.md, "Licencias"): the ingest steps keep them in
``data/cache/`` (never committed) and this module only reads them. In order:

1. PubMed, ``cache/pubmed/abstract/<pmid>.json`` (step 3), with its section labels.
2. bioRxiv / medRxiv, ``cache/<server>/abstract/<doi>.json`` (step 5).
3. Europe PMC, for open-access studies that only it has: the ``<abstract>`` of the
   full-text XML, which :func:`synaptica.ingest.europepmc.fetch_fulltext` downloads on
   demand (decision of Aday, SCOPE v62) and caches. Only the abstract is used: the full
   text would cost ten times the tokens and the prompts are written for abstracts.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import get_paths

MIN_CHARS = 200  # shorter "abstracts" are graphical abstracts or teasers


def _pubmed(cache_root: Path, pmid: str) -> str | None:
    path = cache_root / "pubmed" / "abstract" / f"{pmid}.json"
    if not path.exists():
        return None
    sections = json.loads(path.read_text(encoding="utf-8"))["sections"]
    return "\n".join(
        (f"{s['label']}: " if s.get("label") else "") + s["text"] for s in sections if s["text"]
    )


def _preprint(cache_root: Path, server: str, doi: str) -> str | None:
    path = cache_root / server / "abstract" / f"{doi.replace('/', '_')}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["abstract"]


def jats_abstract(xml: str) -> str | None:
    """The main abstract of a JATS article (not the graphical one, not a teaser)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    for node in root.iter("abstract"):
        if node.get("abstract-type") not in (None, "abstract", "summary"):
            continue
        parts = []
        for sec in node.iter():
            if sec.tag in ("title", "p"):
                text = " ".join("".join(sec.itertext()).split())
                if text:
                    parts.append(text + (":" if sec.tag == "title" else ""))
        text = " ".join(parts)
        if text:
            return text
    return None


def abstract_for(
    study: dict[str, Any],
    *,
    cache_root: Path | None = None,
    client: httpx.Client | None = None,
) -> tuple[str, str] | None:
    """(abstract, origin) for a ``dim_study`` row, or None when no source has one. Europe
    PMC is asked only with a ``client`` (``syn facts``; never in tests)."""
    cache_root = cache_root if cache_root is not None else get_paths().cache
    sources = study.get("sources") or []
    candidates = []
    if study.get("pmid"):
        candidates.append(("pubmed", lambda: _pubmed(cache_root, study["pmid"])))
    for server in ("biorxiv", "medrxiv"):
        if server in sources and study.get("doi"):
            candidates.append((server, lambda s=server: _preprint(cache_root, s, study["doi"])))
    if study.get("pmcid"):

        def europepmc() -> str | None:
            from synaptica.ingest.europepmc import fetch_fulltext, fulltext_path

            path = fulltext_path(cache_root, study["pmcid"])
            if path.exists():
                return jats_abstract(path.read_text(encoding="utf-8"))
            if client is None:
                return None
            xml = fetch_fulltext(client, study["pmcid"], cache_root=cache_root)
            return jats_abstract(xml) if xml else None

        candidates.append(("europepmc", europepmc))
    for origin, read in candidates:
        text = read()
        if text and len(text) >= MIN_CHARS:
            return text, origin
    return None
