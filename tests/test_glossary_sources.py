"""Glossary terms and their Wikipedia sources, with real API answers behind
``httpx.MockTransport`` (no network). Fixtures: ``tests/fixtures/wikipedia/glossary_*.json``,
asked for DREADD (a redirect, no Spanish article), Dopamine, Pars compacta and a page
that does not exist, on 2026-11-15."""

import datetime as dt
import json
from dataclasses import replace

import httpx
import pytest

from synaptica.config import project_root
from synaptica.glossary import load_terms
from synaptica.glossary.sources import load_sources, update_sources
from synaptica.http import Throttle, make_client

FIXTURES = project_root() / "tests" / "fixtures" / "wikipedia"
DAY = dt.date(2026, 11, 15)
NO_WAIT = Throttle(1000, sleep=lambda _: None)
ANSWERS = {lang: json.loads((FIXTURES / f"glossary_{lang}.json").read_text("utf-8"))
           for lang in ("en", "es")}  # fmt: skip


class FakeWikipedia:
    """Answers each language's fixture, whatever titles are asked; records the calls."""

    def __init__(self, fail=False, api_error=False):
        self.calls = []
        self.fail = fail
        self.api_error = api_error

    def __call__(self, request):
        lang = request.url.host.split(".")[0]
        self.calls.append((lang, request.url.params["titles"]))
        if self.fail:
            return httpx.Response(404)
        if self.api_error:
            return httpx.Response(200, json={"error": {"code": "internal_api_error_DBQueryError"}})
        return httpx.Response(200, json=ANSWERS[lang])


def terms(*ids):
    by_id = {t.term_id: t for t in load_terms()}
    return [by_id[i] for i in ids]


def run(tmp_path, chosen, fake=None, **kw):
    fake = fake or FakeWikipedia()
    with make_client(httpx.MockTransport(fake)) as client:
        r = update_sources(client, chosen, path=tmp_path / "s.json", today=DAY,
                           throttle=NO_WAIT, **kw)  # fmt: skip
    return r, fake


def test_terms_file_has_the_proposal_and_her_terms():
    """The 17 samples of docs/propuesta.md and the 7 she proposed (issue #14 and #15)."""
    all_terms = load_terms()
    by_origin = {o: {t.term for t in all_terms if t.origin == o} for o in ("proposal", "sofia")}
    assert len(by_origin["proposal"]) == 17
    assert by_origin["sofia"] == {"NMDA", "BDNF", "5-HT", "PET", "LTD", "STN", "ROS"}
    table = (project_root() / "docs" / "propuesta.md").read_text("utf-8")
    block = table.split("## Neuro Glossary: primeros términos", 1)[1].split("\n## ", 1)[0]
    assert all(f"| {t} |" in block for t in by_origin["proposal"])


def test_acronyms_match_in_their_case_names_in_any():
    (da,) = terms("da")
    assert da.pattern.search("niveles de DA en el estriado")
    assert not da.pattern.search("eso da igual")
    assert da.pattern.search("La Dopamina es")


def test_accepted_sources_redirects_and_gaps(tmp_path):
    r, fake = run(tmp_path, terms("da", "dreadds", "snc"))
    src = load_sources(tmp_path / "s.json")
    assert src["da"]["en"]["accepted"] and src["da"]["es"]["title"] == "Dopamina"
    assert src["da"]["es"]["url"].startswith("https://es.wikipedia.org/w/index.php?oldid=")
    # The redirect is followed; RASSL has no Spanish article: a gap in Spanish.
    dreadd = src["dreadds"]
    assert dreadd["en"]["title"] == "Receptor activated solely by a synthetic ligand"
    assert dreadd["en"]["accepted"] and dreadd["es"] == {"title": None, "accepted": False}
    assert src["snc"]["es"]["accepted"]  # «pars compacta (SNpc)»
    assert (r.asked, r.accepted, r.failed) == (3, {"en": 3, "es": 2}, [])
    assert [lang for lang, _ in fake.calls] == ["en", "es"]


def test_a_lead_that_does_not_name_the_term_is_not_accepted(tmp_path):
    (da,) = terms("da")
    wrong = replace(da, forms_exact=("XYZ",), forms_any_case=("nothing like it",))
    run(tmp_path, [wrong])
    assert load_sources(tmp_path / "s.json")["da"]["en"] == {"title": "Dopamine",
                                                             "accepted": False}  # fmt: skip


def test_missing_page_is_not_accepted(tmp_path):
    (da,) = terms("da")
    run(tmp_path, [replace(da, source_en="No such neuro article xyz")])
    src = load_sources(tmp_path / "s.json")["da"]
    assert src == {"en": {"title": None, "accepted": False},
                   "es": {"title": None, "accepted": False}}  # fmt: skip


def test_idempotent_and_retrieved_date_kept(tmp_path):
    run(tmp_path, terms("da"))
    first = (tmp_path / "s.json").read_text()
    r, fake = run(tmp_path, terms("da"))
    assert fake.calls == [] and r.asked == 0
    with make_client(httpx.MockTransport(FakeWikipedia())) as client:
        r = update_sources(
            client,
            terms("da"),
            path=tmp_path / "s.json",
            today=DAY + dt.timedelta(days=9),
            throttle=NO_WAIT,
            refresh=True,
        )
    assert r.changed == 0 and (tmp_path / "s.json").read_text() == first


def test_failed_lookup_is_reported_and_keeps_what_was_there(tmp_path):
    run(tmp_path, terms("da"))
    r, _ = run(tmp_path, terms("da", "snc"), fake=FakeWikipedia(fail=True), refresh=True)
    assert sorted(r.failed) == ["da", "snc"]
    assert set(load_sources(tmp_path / "s.json")) == {"da"}


def test_an_api_error_is_a_failure_not_a_missing_page(tmp_path):
    """An API error (200, no pages) must not turn a good source into "no source"."""
    run(tmp_path, terms("da"))
    first = (tmp_path / "s.json").read_text()
    r, _ = run(tmp_path, terms("da"), fake=FakeWikipedia(api_error=True), refresh=True)
    assert r.failed == ["da"] and (tmp_path / "s.json").read_text() == first


@pytest.mark.parametrize("bad", ["origin", "repeat"])
def test_bad_terms_file_fails(tmp_path, bad):
    rows = (project_root() / "src/synaptica/glossary/terms.csv").read_text("utf-8").splitlines()
    if bad == "origin":
        rows[1] = rows[1].replace(",sofia,", ",someone,")
    else:
        rows.append(rows[1])
    path = tmp_path / "t.csv"
    path.write_text("\n".join(rows) + "\n", "utf-8")
    with pytest.raises(ValueError):
        load_terms(path)
