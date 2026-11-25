"""Sources of Phase 2's fixed texts (src/synaptica/wiki.py, lab/sources.py,
atlas/sources.py; step 5 of the plan of 2026-11-17). No network: a fake Wikipedia and a
fake Wikidata behind ``httpx.MockTransport``, answering in their APIs' shapes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from synaptica.http import Throttle, make_client

NO_WAIT = Throttle(1000, sleep=lambda _: None)


class FakeWiki:
    """Wikipedia (formatversion 2) from ``pages`` (title -> lead, or None for a
    disambiguation page), with Spanish links from ``es`` and sections (heading -> HTML, the
    same in every revision) from ``sections``; Wikidata by the query's words."""

    def __init__(self, pages: dict[str, str | None], es: dict[str, str],
                 items: list[dict] | None = None, located: list[dict] | None = None,
                 sick: set[str] | None = None,
                 sections: dict[str, str] | None = None) -> None:  # fmt: skip
        self.pages, self.es = pages, es
        self.items, self.located, self.sick = items or [], located or [], sick or set()
        self.sections = sections or {}
        self.asked: list[tuple[str, str]] = []
        self.parsed: list[tuple[str, str]] = []  # (oldid, prop)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        params = request.url.params
        if params.get("action") == "parse":
            self.parsed.append((params["oldid"], params["prop"]))
            heads = list(self.sections)
            if params["prop"] == "sections":
                rows = [{"index": str(i), "line": h} for i, h in enumerate(heads, 1)]
                return httpx.Response(200, json={"parse": {"sections": rows}})
            html = self.sections[heads[int(params["section"]) - 1]]
            return httpx.Response(200, json={"parse": {"text": html}})
        if host == "eutils.ncbi.nlm.nih.gov":  # a PMC article (v245): none here, no body
            return httpx.Response(200, text="<pmc-articleset><article/></pmc-articleset>")
        if host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        if host == "query.wikidata.org":
            q = request.url.params["query"]
            if "P486" in q:
                rows = self.items
            elif "gearing" in q:
                rows = [{"d": f"http://www.wikidata.org/entity/{d}"} for d in sorted(self.sick)]
            else:
                rows = self.located
            bindings = [{k: {"value": v} for k, v in r.items()} for r in rows]
            return httpx.Response(200, json={"results": {"bindings": bindings}})
        lang = host.split(".")[0]
        titles = request.url.params["titles"].split("|")
        self.asked.append((lang, request.url.params["titles"]))
        out = []
        for n, t in enumerate(titles):
            if t not in self.pages:
                out.append({"title": t, "missing": True})
                continue
            lead = self.pages[t]
            page = {"title": t, "revisions": [{"revid": 1000 + n}], "extract": lead or "",
                    "pageprops": {} if lead else {"disambiguation": ""}}  # fmt: skip
            if lang == "en" and t in self.es:
                page["langlinks"] = [{"lang": "es", "title": self.es[t]}]
            out.append(page)
        return httpx.Response(200, json={"query": {"pages": out}})


def test_leads_accept_english_by_its_words_and_spanish_by_its_link() -> None:
    from synaptica.wiki import LeadsResult, leads

    fake = FakeWiki(
        {"Optogenetics": "Optogenetics is a technique…", "EEG (disambiguation)": None,
         "Perfusion": "Perfusion is the passage of fluid…", "Optogenética": "La optogenética…"},
        {"Optogenetics": "Optogenética", "Perfusion": "Perfusión"},
    )  # fmt: skip
    wanted = {
        "opto": ("Optogenetics", re.compile("optogenetics", re.I)),
        "eeg": ("EEG (disambiguation)", re.compile("EEG")),
        "perf": ("Perfusion", re.compile("transcardial perfusion", re.I)),  # not named
        "none": ("Nothing here", re.compile("x")),
    }
    r = LeadsResult()
    import datetime as dt

    with make_client(httpx.MockTransport(fake)) as c:
        got = leads(c, wanted, {}, dt.date(2026, 11, 17), NO_WAIT, r)
    assert got["opto"]["en"]["accepted"] and got["opto"]["es"]["title"] == "Optogenética"
    assert got["opto"]["es"]["url"] == "https://es.wikipedia.org/w/index.php?oldid=1000"
    assert not any(
        got[k][lang]["accepted"] for k in ("eeg", "perf", "none") for lang in ["en", "es"]
    )
    # The Spanish of a rejected English article is never asked: «Perfusión» is not looked up.
    assert [lang for lang, _ in fake.asked] == ["en", "es"] and "Perfusión" not in fake.asked[1][1]
    assert (r.asked, r.accepted) == (4, {"en": 1, "es": 1})


def test_lab_sources_one_per_technique_and_a_rerun_asks_nothing(tmp_path: Path) -> None:
    from synaptica.lab import sources
    from synaptica.lab.studies import techniques

    pages = {t["source_en"]: f"{t['name_en']} names it: {t['text'][0] if t['text'] else ''}."
             for t in techniques() if t["id"] != "perfusion"}  # fmt: skip
    pages["Optogenética"] = "La optogenética…"
    fake = FakeWiki(pages, {"Optogenetics": "Optogenética"})
    path = tmp_path / "s.json"
    with make_client(httpx.MockTransport(fake)) as c:
        r = sources.update_sources(c, path=path, throttle=NO_WAIT)
        again = sources.update_sources(c, path=path, throttle=NO_WAIT)
    got = json.loads(path.read_text())["techniques"]
    assert list(got) == [t["id"] for t in techniques()]
    assert not got["perfusion"]["en"]["accepted"]  # no section naming it: a gap
    assert got["optogenetics"]["es"]["title"] == "Optogenética"
    assert r.accepted["en"] == 10 and again.asked == 0


def test_atlas_sources_and_diseases_by_mesh_never_guessing(tmp_path: Path) -> None:
    from synaptica.atlas import sources

    wd = "http://www.wikidata.org/entity/"
    items = [
        {"mesh": "D006624", "item": wd + "Q48360", "en": "Hippocampus"},
        {"mesh": "D002531", "item": wd + "Q130983", "en": "Cerebellum"},
        # One MeSH ID on two items with an article: reported, left empty.
        {"mesh": "D000679", "item": wd + "Q1", "en": "Amygdala"},
        {"mesh": "D000679", "item": wd + "Q2", "en": "Amygdaloid body"},
    ]
    located = [
        {"item": wd + "Q130983", "d": wd + "Q564123", "en": "cerebellar disease"},
        {"item": wd + "Q130983", "d": wd + "Q999", "en": "cerebellum development"},
    ]
    fake = FakeWiki({"Hippocampus": "The hippocampus is…", "Cerebellum": "The cerebellum…",
                     "Hipocampo": "El hipocampo…"}, {"Hippocampus": "Hipocampo"},
                    items=items, located=located, sick={"Q564123"})  # fmt: skip
    with make_client(httpx.MockTransport(fake)) as c:
        r = sources.update(c, sources_path=tmp_path / "s.json",
                           diseases_path=tmp_path / "d.json", throttle=NO_WAIT)  # fmt: skip
    pairs = json.loads((tmp_path / "s.json").read_text())["pairs"]
    assert pairs["internal"]["wikidata"] == "Q48360"
    assert pairs["internal"]["leads"]["es"]["title"] == "Hipocampo"
    assert "third" not in pairs and r.ambiguous == ["third: ['Q1', 'Q2']"]
    body = json.loads((tmp_path / "d.json").read_text())
    assert "NOT PUBLISHED" in body["note"]
    assert body["pairs"]["cerebellum"] == [{"qid": "Q564123", "en": "cerebellar disease",
                                            "es": None}]  # fmt: skip
    assert body["pairs"]["internal"] == []


SECTION_HTML = (
    '<div class="mw-heading mw-heading2"><h2 id="Limits">Technical challenges and limitations'
    '</h2><span class="mw-editsection">[edit]</span></div>'
    '<div role="note" class="hatnote">Main article: Something</div>'
    "<p>Not every cell expresses the opsin at the same level.<sup class=\"reference\">"
    "<a>[12]</a></sup> Light fades with depth in tissue.</p>"
    "<table><tr><td>a table</td></tr></table>"
    "<ul><li>It heats the tissue https://example.org/x.</li></ul>"
)  # fmt: skip


def test_section_text_keeps_only_the_prose() -> None:
    from synaptica.wiki import section_text

    assert section_text(SECTION_HTML) == (
        "Not every cell expresses the opsin at the same level. Light fades with depth in "
        "tissue.\n\nIt heats the tissue."
    )


def test_lab_sources_keep_the_limits_section_at_the_lead_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synaptica.lab import sources
    from synaptica.lab.studies import techniques

    pmc = ("limits_pmc", "limits_pmc_section")  # its PMC source (v245): test_lab_pmc
    rows = [{k: v for k, v in t.items() if k not in pmc} | {"limits_section_en": "Problems"}
            if t["id"] == "western-blot" else t for t in techniques()]  # fmt: skip
    monkeypatch.setattr(sources, "techniques", lambda: rows)

    pages = {t["source_en"]: f"{t['name_en']} names it: {t['text'][0] if t['text'] else ''}."
             for t in techniques() if t["id"] != "perfusion"}  # fmt: skip
    fake = FakeWiki(pages, {}, sections={"Technical challenges and limitations": SECTION_HTML})
    path = tmp_path / "s.json"
    with make_client(httpx.MockTransport(fake)) as c:
        r = sources.update_sources(c, path=path, throttle=NO_WAIT)
        n = len(fake.parsed)
        again = sources.update_sources(c, path=path, throttle=NO_WAIT)
    got = json.loads(path.read_text())["techniques"]
    opto = got["optogenetics"]
    lim = opto["limits_en"]
    assert lim["heading"] == "Technical challenges and limitations"
    assert (lim["revid"], lim["url"]) == (opto["en"]["revid"], opto["en"]["url"])
    assert lim["text"].startswith("Not every cell")
    # Western blot names a section this fake article lacks: no source, and it says so.
    assert "limits_en" not in got["western-blot"] and r.sections == 1
    assert any("western-blot: no section «Problems»" in f for f in r.failed)
    assert "limits_en" not in got["eeg"]  # no section in its row: never asked
    # A rerun at the same revision keeps it without asking; only the missing one is asked.
    assert again.sections == 0 and got == json.loads(path.read_text())["techniques"]
    assert len(fake.parsed) - n == 1 and "limits_en" in got["optogenetics"]
    # Taken out of the table: dropped from the sources, and counted as a change.
    plain = [{k: v for k, v in t.items() if k != "limits_section_en"} for t in techniques()]
    monkeypatch.setattr(sources, "techniques", lambda: plain)
    with make_client(httpx.MockTransport(fake)) as c:
        dropped = sources.update_sources(c, path=path, throttle=NO_WAIT)
    left = json.loads(path.read_text())["techniques"]
    assert dropped.changed == 1 and not any("limits_en" in v for v in left.values())


PERFUSION_HTML = (
    "<p>In tissue fixation via perfusion, the fixative is pumped into the circulatory "
    "system. Perfusion fixation is commonly used to image brain tissue in rodents.</p>"
)


def test_perfusion_takes_a_section_of_another_article_as_its_lead(tmp_path: Path) -> None:
    """v227: no article's lead names it, so its source is a section, kept as its lead."""
    from synaptica.lab import sources, texts

    pages = {"Fixation (histology)": "Fixation preserves tissue for histology."}
    fake = FakeWiki(pages, {"Fixation (histology)": "Fijación"},
                    sections={"Perfusion": PERFUSION_HTML})  # fmt: skip
    path = tmp_path / "s.json"
    with make_client(httpx.MockTransport(fake)) as c:
        r = sources.update_sources(c, path=path, throttle=NO_WAIT)
        n = len(fake.parsed)
        again = sources.update_sources(c, path=path, throttle=NO_WAIT)
    en = json.loads(path.read_text())["techniques"]["perfusion"]["en"]
    assert en["accepted"] and en["section"] == "Perfusion"
    assert en["lead"].startswith("In tissue fixation via perfusion")
    assert en["url"].endswith(f"oldid={en['revid']}")
    assert not any(f.startswith("perfusion") for f in r.failed)
    assert len(fake.parsed) == n and not any(f.startswith("perfusion") for f in again.failed)
    # Her card says it is a section, not the lead.
    out = tmp_path / "t.json"
    rec = {"revid": en["revid"], "source": en["url"], "what": {
        "status": "drafted", "en": [{"text": "It fixes the brain.", "fact_ids": ["f1"]}],
        "es": [{"text": "Fija el cerebro.", "fact_ids": ["f1"]}]}}  # fmt: skip
    out.write_text(json.dumps({"techniques": {"perfusion": rec}}))
    (item,) = texts.review_items(out, path)
    assert "sección «Perfusion»" in item.content.sources[0].label
