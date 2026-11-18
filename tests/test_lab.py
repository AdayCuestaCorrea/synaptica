"""Neuro Lab, B2 (src/synaptica/lab/, v202): the technique table, matching studies by MeSH
and text, and the pages. No network: the committed vocabulary and tiny warehouses."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb

from synaptica.lab import studies
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site

LICENSED = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}


def test_the_table_has_every_technique_of_scope_once_with_both_names() -> None:
    rows = studies.techniques()
    ids = [t["id"] for t in rows]
    assert len(ids) == len(set(ids)) == 11
    for t in rows:
        assert t["name_es"] and t["name_en"]
        assert t["mesh"] or t["text"], t["id"]  # something finds its studies


def test_every_descriptor_of_the_table_is_in_the_fetched_vocabulary() -> None:
    known = {r["ui"] for r in studies.vocabulary()}
    for t in studies.techniques():
        for ui in [*t["mesh"], *t.get("exclude", [])]:
            assert ui in known, (t["id"], ui)
    terms = {r["term"] for r in studies.vocabulary()}
    for t in studies.techniques():
        for w in t.get("exclude_terms", []):
            assert w in terms, (t["id"], w)


def test_excluded_branches_and_terms_find_nothing() -> None:
    """EEG's tree holds the brain rhythms (a phenomenon), the antibody tree immunoassays;
    «laser scanning microscopy» is two-photon too."""
    m = studies.matcher()
    assert m.mesh(["D013826"], []) == set()  # Theta Rhythm
    assert m.mesh(["D015200"], []) == set()  # Fluoroimmunoassay
    assert m.mesh(["D004569"], []) == {"eeg"}
    assert m.mesh(["D019084"], []) == {"immunofluorescence"}  # indirect: kept
    assert m.text("Theta rhythm in the rat hippocampus") == set()
    assert m.text("Two-photon laser scanning microscopy in vivo") == set()
    assert m.text("Confocal microscopy of dendritic spines") == {"confocal"}


def test_literal_words_whole_without_case_and_with_plurals() -> None:
    m = studies.matcher()
    assert m.text("DREADDs in the amygdala") == {"chemogenetics"}
    assert m.text("Fibre photometry of dopamine release") == {"fiber-photometry"}
    assert m.text("Resting-state fMRI in adolescents") == {"fmri"}
    assert m.text("Whole-cell recordings from CA1 neurons") == {"electrophysiology"}
    assert m.text("Peg tests in older adults") == set()  # not «EEG» inside a word
    # Twice in title and abstract together, not once.
    assert m.text("Amygdala circuits", "We used optogenetics. Optogenetic silencing…") == {
        "optogenetics"
    }
    assert m.text("Amygdala circuits", "Unlike optogenetics, lesions…") == set()


def warehouse(path: Path) -> Path:
    with duckdb.connect(str(path)) as con:
        con.execute("""create table dim_study (study_id varchar, pmid varchar, doi varchar,
            pmcid varchar, sources varchar[], title varchar, species varchar,
            entered_on date, published_on date, is_neuro boolean, news_type varchar)""")
        con.execute("create table int_pubmed__records (pmid varchar, mesh_uis varchar[], "
                    "keywords varchar[])")  # fmt: skip
        d = dt.date(2026, 11, 10)
        con.executemany("insert into dim_study values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("s1", "1", None, None, ["pubmed"], "Sleep spindles in older adults", "humans",
             d, d, True, None),
            ("s2", "2", None, None, ["pubmed"], "Optogenetic control of fear", "animals", d, d,
             True, None),
            ("s3", None, "10.1/x", None, ["biorxiv"], "Fiber photometry of VTA neurons",
             "unknown", d, d, True, None),
            ("s4", "4", None, None, ["pubmed"], "Optogenetics, noise", "animals", d, d, True,
             "noise"),
        ])  # fmt: skip
        con.executemany("insert into int_pubmed__records values (?, ?, ?)", [
            ("1", ["D004569"], []),  # MeSH: Electroencephalography
            ("2", ["D009474"], []),  # MeSH without the technique: the title still counts
        ])  # fmt: skip
    return path


def test_studies_by_mesh_or_by_text_even_with_mesh(tmp_path: Path) -> None:
    """Unlike the regions (text only without MeSH), a technique is looked for in the text
    of every study, so the abstract is read for all of them (from the cache only)."""
    asked = []

    def abstract(study, cache_root=None):
        asked.append(study["pmid"] or study["doi"])
        return None

    found = studies.technique_studies(warehouse(tmp_path / "w.duckdb"),
                                      ("study_id", "title", "species", "pmid", "doi",
                                       "sources"), abstract=abstract)  # fmt: skip
    assert {k: [(s["study_id"], s["basis"]) for s in v] for k, v in found.items()} == {
        "eeg": [("s1", "mesh")],
        "optogenetics": [("s2", "text")],
        "fiber-photometry": [("s3", "text")],
    }
    assert sorted(asked) == ["1", "10.1/x", "2"]  # never the noise
    c = studies.counts(found)
    assert list(c) == [t["id"] for t in studies.techniques()]
    assert c["eeg"] == {"studies": 1, "mesh": 1, "text": 0}
    assert c["perfusion"] == {"studies": 0, "mesh": 0, "text": 0}


def test_lab_pages_without_a_warehouse_are_gaps_and_linked(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED).build()
    assert check_site(out).passed  # also: every technique page is linked from another page
    index = (out / "es" / "lab.html").read_text()
    assert 'href="lab/western-blot.html"' in index and "gap-lab_texts" in index
    page = (out / "en" / "lab" / "fiber-photometry.html").read_text()
    for gap in ("gap-lab_texts", "gap-lab_studies", "gap-lab_regions"):
        assert gap in page
    home = (out / "es" / "index.html").read_text()
    assert 'class="card card--lab" href="lab.html"' in home
    assert 'href="lab.html"' in (out / "es" / "noticias.html").read_text()  # the header


def test_lab_pages_list_the_studies_as_a_proposal(tmp_path: Path) -> None:
    from test_site_news import STUDIES, study
    from test_site_news import warehouse as site_warehouse

    rows = [*STUDIES, study("doi:10.1/opto", title="Optogenetic silencing of the amygdala"),
            study("doi:10.1/fmri", title="Resting-state fMRI in adolescents",
                  species="humans")]  # fmt: skip
    data = site_warehouse(tmp_path / "data", studies=rows)
    out = tmp_path / "site"
    built = SiteBuilder(out, images=LICENSED, data_dir=data).build()
    assert check_site(out).passed
    assert built["lab"]["optogenetics"]["studies"] == 1 and built["lab"]["fmri"]["text"] == 1
    opto = (out / "es" / "lab" / "optogenetics.html").read_text()
    assert 'data-study="doi:10.1/opto"' in opto and 'href="#gap-lab_match"' in opto
    assert "gap-lab_studies" not in opto and "doi:10.1/fmri" not in opto
    none = (out / "en" / "lab" / "perfusion.html").read_text()
    assert "No recent study names this technique" in none
    assert "1 estudio reciente<" in (out / "es" / "lab.html").read_text()


# ---- her queue (B2-3, v204) ----------------------------------------------------------


def test_one_card_per_technique_with_its_words_once_each() -> None:
    from synaptica.review.models import ItemType

    items = studies.review_items({"eeg": [{"title": f"EEG study {n}"} for n in range(5)]})
    assert [i.item_id for i in items] == [f"lab-{t['id']}" for t in studies.techniques()]
    assert all(i.item_type is ItemType.SEARCH_TERMS for i in items)
    eeg = next(i for i in items if i.item_id == "lab-eeg")
    assert eeg.content.terms[0] == "Electroencephalography" and "ECoG" in eeg.content.terms
    assert eeg.content.examples == ["EEG study 0", "EEG study 1", "EEG study 2"]
    opto = next(i for i in items if i.item_id == "lab-optogenetics")
    assert [w.lower() for w in opto.content.terms].count("optogenetics") == 1
    confocal = next(i for i in items if i.item_id == "lab-confocal")
    assert "Laser Scanning Microscopy" not in confocal.content.terms  # excluded
    # New studies every day never bring back a card she answered.
    assert [i.content_sha256 for i in items] == [i.content_sha256 for i in studies.review_items({})]


def test_lab_cards_from_the_23rd_four_a_weekday_after_the_pairs(tmp_path: Path) -> None:
    from synaptica.review import collect
    from test_review_collect import data_dir

    data = data_dir(tmp_path, a=4)

    def techs(day: dt.date) -> list[str]:
        q = collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", day,
                            glossary=[])  # fmt: skip
        return [i.item_id for i in q.items if i.item_id.startswith("lab-")]

    assert techs(dt.date(2026, 11, 22)) == []
    monday = techs(dt.date(2026, 11, 23))
    assert monday == ["lab-perfusion", "lab-western-blot", "lab-immunofluorescence",
                      "lab-confocal"]  # fmt: skip
    assert len(techs(dt.date(2026, 11, 28))) == collect.LAB_TERMS_WEEKEND


def test_her_approval_takes_the_proposal_tag_off_the_technique(tmp_path: Path) -> None:
    from synaptica.review.models import Action
    from test_review_collect import decide
    from test_site_news import STUDIES, study
    from test_site_news import warehouse as site_warehouse

    rows = [*STUDIES, study("doi:10.1/opto", title="Optogenetic silencing of the amygdala")]
    data = site_warehouse(tmp_path / "data", studies=rows)
    items = {i.item_id: i for i in studies.review_items()}
    decide(data, items["lab-optogenetics"], Action.APPROVE)
    assert studies.reviewed(data / "review") == {"optogenetics": "2026-11-10"}
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    assert check_site(out).passed
    opto = (out / "es" / "lab" / "optogenetics.html").read_text()
    assert "gap-lab_match" not in opto
    assert "términos de búsqueda que revisó Sofía (2026-11-10)" in opto
    fmri = (out / "es" / "lab" / "fmri.html").read_text()
    assert 'href="#gap-lab_match"' in fmri
    # A correction leaves it a proposal until her words are on the table and approved.
    decide(data, items["lab-fmri"], Action.EDIT, {"terms": ["fMRI", "BOLD"]}, n=2)
    assert "fmri" not in studies.reviewed(data / "review")


# ---- technique <-> region (step 6, v206) -----------------------------------------------


def test_shared_needs_two_studies_and_sorts_by_count() -> None:
    found = {"a": [{"study_id": "1"}, {"study_id": "2"}], "b": [{"study_id": "1"}],
             "c": [{"study_id": x} for x in "123"]}  # fmt: skip
    assert studies.shared({"1", "2", "3"}, found) == [("c", 3), ("a", 2)]


def test_region_and_technique_pages_link_each_other_as_a_proposal(tmp_path: Path) -> None:
    from test_site_news import STUDIES, study
    from test_site_news import warehouse as site_warehouse

    rows = [*STUDIES,
            study("doi:10.1/o1", title="Optogenetic silencing of the hippocampus"),
            study("doi:10.1/o2", title="Hippocampus replay under optogenetic control"),
            study("doi:10.1/f1", title="Hippocampus activity in fMRI")]  # fmt: skip
    data = site_warehouse(tmp_path / "data", studies=rows)
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    assert check_site(out).passed
    hippo = (out / "es" / "atlas" / "regiones" / "waxholm-hippocampal-formation.html").read_text()
    assert 'href="../../lab/optogenetics.html"' in hippo and "2 estudios en común" in hippo
    assert "lab/fmri.html" not in hippo  # only one shared study
    assert 'href="#gap-region_methods_match"' in hippo and 'gap-region_methods"' not in hippo
    opto = (out / "en" / "lab" / "optogenetics.html").read_text()
    assert 'href="../atlas/regions/waxholm-hippocampal-formation.html"' in opto
    assert opto.index("waxholm-hippocampal") < opto.index("julich-ca1")  # rat first
    assert 'href="#gap-lab_regions_match"' in opto
    fmri = (out / "en" / "lab" / "fmri.html").read_text()
    assert "gap-lab_regions_match" not in fmri and 'href="#gap-lab_regions"' in fmri


def test_a_technique_shows_the_texts_she_approved_with_their_source(tmp_path: Path) -> None:
    from synaptica.lab.texts import review_items

    items = {i.item_id: i for i in review_items()}  # the committed drafts (v209)
    data, review = tmp_path / "data", tmp_path / "data" / "review"
    review.mkdir(parents=True)
    lines = [json.dumps({"item_type": "lab", "item_id": k,
                         "content_sha256": items[k].content_sha256, "action": "approve",
                         "payload": {}, "note": None, "reviewed_by": "sofia",
                         "reviewed_at": "2026-11-19T10:00:00Z", "source": f"issue#{n}"})
             for n, k in enumerate(("eeg-what", "eeg-limit", "fmri-what"), 1)]  # fmt: skip
    (review / "decisions.jsonl").write_text("\n".join(lines) + "\n")
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    assert check_site(out).passed
    eeg = (out / "en" / "lab" / "eeg.html").read_text()
    assert 'data-lab-text="what"' in eeg and 'data-lab-text="limit"' in eeg
    assert "gap-lab_texts" not in eeg and "Wikipedia (English)" in eeg
    assert items["eeg-what"].content.en[0].text in eeg
    fmri = (out / "es" / "lab" / "fmri.html").read_text()
    assert 'data-lab-text="what"' in fmri and "gap-lab_texts" in fmri  # limits: not yet
    assert items["fmri-what"].content.es[0].text in fmri
    assert "data-lab-text" not in (out / "es" / "lab" / "optogenetics.html").read_text()
