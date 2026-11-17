"""Sources of Phase 2's fixed texts (src/synaptica/wiki.py, lab/sources.py,
atlas/sources.py; step 5 of the plan of 2026-11-17). No network: a fake Wikipedia and a
fake Wikidata behind ``httpx.MockTransport``, answering in their APIs' shapes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from synaptica.http import Throttle, make_client

NO_WAIT = Throttle(1000, sleep=lambda _: None)


class FakeWiki:
    """Wikipedia (formatversion 2) from ``pages`` (title -> lead, or None for a
    disambiguation page), with Spanish links from ``es``; Wikidata by the query's words."""

    def __init__(self, pages: dict[str, str | None], es: dict[str, str],
                 items: list[dict] | None = None, located: list[dict] | None = None,
                 sick: set[str] | None = None) -> None:  # fmt: skip
        self.pages, self.es = pages, es
        self.items, self.located, self.sick = items or [], located or [], sick or set()
        self.asked: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
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
    assert not got["perfusion"]["en"]["accepted"]  # no article: a gap
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
