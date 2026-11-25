"""A PMC article's section as a Neuro Lab «limits» source (v245, src/synaptica/lab/pmc.py).

Without an open licence its text never goes to the repository: only its hash, and the
text in the cache. No network: NCBI and Europe PMC answer through ``httpx.MockTransport``,
and the article is a small JATS file written for the test."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from synaptica.http import Throttle
from synaptica.lab import pmc, texts
from synaptica.lab.sources import _pmc_limits
from synaptica.wiki import LeadsResult
from test_lab_texts import SECTION, SectionLLM, decide, sources

JATS = f"""<pmc-articleset><article><front/><body>
<sec><title>Overview</title><p>Not this one.</p></sec>
<sec><title>Limitations</title>
  <p>{SECTION[:-1]} [<xref ref-type="bibr" rid="R1">1</xref>,<xref ref-type="bibr"
  rid="R2">2</xref>].</p>
  <sec><title>Depth</title><p>Deeper regions need longer wavelengths.</p></sec>
</sec></body></article></pmc-articleset>"""
TEXT = f"{SECTION}\nDepth\nDeeper regions need longer wavelengths."


def fake(calls: list[str], licence: str | None, xml: str = JATS) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if "ncbi" in request.url.host:
            return httpx.Response(200, text=xml)
        return httpx.Response(200, json={"resultList": {"result": [{
            "title": "Limits of a technique.", "authorString": "Doe J, Roe R.",
            "journalInfo": {"journal": {"medlineAbbreviation": "J Methods"}},
            "pubYear": "2020", "doi": "10.1/x", "license": licence}]}})  # fmt: skip

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_section_is_read_whole_without_references() -> None:
    assert pmc.section_text(JATS, "Limitations") == TEXT
    assert pmc.section_text(JATS, "Problems") is None
    assert pmc.section_text("<article><front/></article>", "Limitations") is None  # no body


def stored(tmp_path: Path, licence: str | None) -> tuple[dict, list[str]]:
    tech = {"id": "optogenetics", "limits_pmc": "PMC123", "limits_pmc_section": "Limitations"}
    entry, calls = {"en": {"accepted": True, "revid": 7}}, []
    _pmc_limits(fake(calls, licence), tech, entry, None, Throttle(1000), LeadsResult(),
                tmp_path / "cache")  # fmt: skip
    return entry["limits_en"], calls


def test_an_open_licence_keeps_the_text_and_none_keeps_only_its_hash(tmp_path: Path) -> None:
    open_, _ = stored(tmp_path / "a", "cc by-nc-nd")
    assert open_["text"] == TEXT and open_["licence"] == "cc by-nc-nd"
    assert open_["citation"]["journal"] == "J Methods"
    closed, _ = stored(tmp_path / "b", None)
    assert "text" not in closed and closed["sha256"] == pmc.sha256(TEXT)
    assert closed["url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"
    assert pmc.cache_path(tmp_path / "b" / "cache", closed).read_text() == TEXT
    again = {"en": {"accepted": True, "revid": 7}}
    calls: list[str] = []
    _pmc_limits(fake(calls, None), {"id": "optogenetics", "limits_pmc": "PMC123",
                                    "limits_pmc_section": "Limitations"},
                again, closed, Throttle(1000), LeadsResult(), None)  # fmt: skip
    assert again["limits_en"] == closed and calls == []  # asked once


def test_the_text_counts_only_with_its_hash(tmp_path: Path) -> None:
    closed, _ = stored(tmp_path, None)
    cache = tmp_path / "cache"
    assert pmc.text_of(closed, cache) == TEXT
    pmc.cache_path(cache, closed).write_text(TEXT + " Changed.")
    assert pmc.text_of(closed, cache) is None  # not the text it was drafted from
    calls: list[str] = []
    assert pmc.text_of(closed, cache, fake(calls, None), Throttle(1000)) == TEXT  # fetched
    assert pmc.text_of(closed, cache) == TEXT and calls == ["eutils.ncbi.nlm.nih.gov"]
    other = JATS.replace("longer wavelengths", "shorter wavelengths")
    assert pmc.text_of(closed, tmp_path / "empty", fake([], None, other), Throttle(1000)) is None


def with_pmc(tmp_path: Path) -> tuple[Path, Path]:
    """Her technique with its «limits» from a PMC section without an open licence: the
    text only in the cache."""
    src = sources(tmp_path)
    closed, _ = stored(tmp_path, None)
    body = json.loads(src.read_text())
    body["techniques"]["optogenetics"]["limits_en"] = closed
    src.write_text(json.dumps(body))
    return src, tmp_path / "cache"


def test_limits_drafted_from_the_cache_and_her_card_cites_the_article(tmp_path: Path) -> None:
    src, cache = with_pmc(tmp_path)
    out = tmp_path / "texts.json"
    llm = SectionLLM()
    status = texts.write(llm, sources_path=src, path=out, cache_root=cache)
    assert status["optogenetics"] == {"what": "drafted", "limit": "drafted"}
    assert "LabFacts:section" in llm.calls
    items = {i.item_id: i for i in texts.review_items(out, src)}
    (s,) = items["optogenetics-limit"].content.sources
    assert s.id == "pmc-pmc123-lab-optogenetics-limits"
    assert s.label.startswith("«Limits of a technique.» Doe J, Roe R. J Methods 2020 (PMC123)")
    assert texts.source_texts(list(items.values()), src, cache)[s.id] == TEXT
    assert s.id not in texts.source_texts(list(items.values()), src, tmp_path / "none")
    assert "Not every cell" not in out.read_text() + src.read_text()  # no text committed


def test_without_its_text_nothing_is_drafted_or_asked(tmp_path: Path) -> None:
    src, _ = with_pmc(tmp_path)
    out = tmp_path / "texts.json"
    texts.write(SectionLLM(), sources_path=src, path=out)  # the lead only: no limits yet
    llm = SectionLLM()
    assert texts.write(llm, sources_path=src, path=out, cache_root=tmp_path / "none") == {}
    assert llm.calls == []


def test_the_site_cites_the_article_with_its_licence(tmp_path: Path) -> None:
    src, cache = with_pmc(tmp_path)
    out, review = tmp_path / "texts.json", tmp_path / "review"
    texts.write(SectionLLM(), sources_path=src, path=out, cache_root=cache)
    item = next(i for i in texts.review_items(out, src) if i.item_id == "optogenetics-limit")
    decide(review, item, "approve")
    shown = texts.published(review, out, src)["optogenetics"]["limit"]
    assert shown["source"]["kind"] == "pmc" and shown["source"]["licence"] is None
    assert shown["source"]["citation"]["authors"] == "Doe J, Roe R."
    assert shown["source"]["heading"] == "Limitations"


def test_her_edit_of_a_pmc_card_waits_without_its_text(tmp_path: Path) -> None:
    """In Actions the cache may lack it: the edit is never checked without its source."""
    import datetime as dt

    from synaptica.review import intake
    from synaptica.review.issue_block import encode
    from synaptica.review.models import Queue

    src, cache = with_pmc(tmp_path)
    out = tmp_path / "texts.json"
    texts.write(SectionLLM(), sources_path=src, path=out, cache_root=cache)
    item = next(i for i in texts.review_items(out, src) if i.item_id == "optogenetics-limit")
    q = Queue(generated_at=dt.datetime(2026, 11, 26, tzinfo=dt.UTC), items=[item])
    edit = {"item_type": "lab", "item_id": item.item_id, "content_sha256": item.content_sha256,
            "action": "edit", "payload": {"es": "Otra frase."}}  # fmt: skip
    body = f"```text\n{encode('2026-11-26T00:00:00Z', 'public', [edit])}\n```"
    sid = item.content.sources[0].id
    assert intake.missing_sources({"issue": {"body": body}}, q, {}) == [sid]
    assert intake.missing_sources({"issue": {"body": body}}, q, {sid: TEXT}) == []
