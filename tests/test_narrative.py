"""Summaries (step 16): abstract sources, facts, EN -> ES with checks, fallback text.

The abstract, facts and texts below are synthetic, written for these tests (no publisher
text in the repository). The model is always a fake.
"""

import datetime as dt
import json

import duckdb

from synaptica.narrative import checks, fallback, pipeline, sources
from synaptica.narrative import facts as facts_mod
from synaptica.narrative import write as write_mod

TODAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)
ABSTRACT = (
    "BACKGROUND: Sleep spindles are bursts of activity during sleep. METHODS: We recorded "
    "brain activity in 24 adult mice across 10 nights of sleep. RESULTS: Mice with more "
    "spindles remembered the location of a hidden platform better in a water maze test the "
    "next day. CONCLUSIONS: Spindles may support memory consolidation in mice, although "
    "this needs confirmation in other species."
)
FACTS = [
    ("The team recorded brain signals from 24 adult mice over 10 nights.",
     "We recorded brain activity in 24 adult mice across 10 nights of sleep", "animals"),
    ("Mice with more spindles did better at finding a hidden platform the following day.",
     "Mice with more spindles remembered the location of a hidden platform better", "animals"),
    ("The authors say spindles may help store memories in mice, pending confirmation.",
     "Spindles may support memory consolidation in mice", "animals"),
    ("Spindles cure insomnia.", "Spindles cure insomnia in every patient", "humans"),
]  # fmt: skip
GOOD_EN = [
    ("In a study of 24 adult mice recorded over 10 nights, researchers looked at sleep "
     "spindles, short bursts of brain activity during sleep.", ["f1"]),
    ("Animals with more spindles were better at locating a hidden platform the next day.",
     ["f2"]),
    ("The authors suggest that spindles may help consolidate memory in mice, but this still "
     "needs confirmation.", ["f3"]),
]  # fmt: skip
COPIED_EN = [
    GOOD_EN[0],
    ("Mice with more spindles remembered the location of a hidden platform better in a "
     "maze.", ["f2"]),
    GOOD_EN[2],
]  # fmt: skip
ES = [
    "En un estudio con 24 ratones adultos registrados durante 10 noches, el equipo analizó "
    "los husos del sueño, breves ráfagas de actividad cerebral.",
    "Los animales con más husos localizaron mejor una plataforma oculta al día siguiente.",
    "Los autores proponen que los husos podrían ayudar a consolidar la memoria en ratones, "
    "aunque falta confirmarlo.",
]


class FakeLLM:
    """Answers by output schema: facts, then English (good or copied), then Spanish."""

    label = "fake/model"

    def __init__(self, english=GOOD_EN):
        self.english = english
        self.calls = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(output.__name__)
        if output.__name__ == "Extraction":
            data = {"facts": [{"statement": s, "quote": q, "subject": k} for s, q, k in FACTS]}
        elif output.__name__ == "Summary":
            data = {"sentences": [{"text": t, "fact_ids": f} for t, f in self.english]}
        else:
            data = {"sentences": [{"index": i, "text": t} for i, t in enumerate(ES, 1)]}
        return output.model_validate(data)


class PassingJudge:
    label = "fake/judge"

    def complete_json(self, system, user, output, max_tokens):
        return output.model_validate({"faithful": True, "no_overclaim": True,
                                      "no_medical_advice": True, "spanish_matches": True,
                                      "passed": True, "spanish_natural": 4})  # fmt: skip


STUDY = {"study_id": "10.1/spindles", "doi": "10.1/spindles", "pmid": "111", "pmcid": None,
         "title": "Spindles and memory in mice", "journal": "Neuron",
         "published_on": dt.date(2026, 11, 5), "entered_on": dt.date(2026, 11, 8),
         "sources": ["pubmed"], "review_status": "journal", "species": "animals",
         "integrity": "none"}  # fmt: skip


def cache_abstract(cache_root, pmid="111", text=ABSTRACT):
    path = cache_root / "pubmed" / "abstract" / f"{pmid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pmid": pmid, "sections": [{"label": "", "text": text}]}))


def make_warehouse(path):
    with duckdb.connect(str(path)) as con:
        con.execute(
            "create table dim_study (study_id varchar, doi varchar, pmid varchar, pmcid "
            "varchar, title varchar, journal varchar, published_on date, entered_on date, "
            "sources varchar[], review_status varchar, species varchar, integrity varchar, "
            "news_candidate boolean, news_type varchar)"
        )
        con.execute(
            "insert into dim_study values "
            "('10.1/spindles', '10.1/spindles', '111', null, 'Spindles', 'Neuron', "
            " '2026-11-05', '2026-11-08', ['pubmed'], 'journal', 'animals', 'none', true, "
            " 'healthy_brain'), "
            "('10.1/noise', '10.1/noise', '222', null, 'Noise', 'Cell', '2026-11-05', "
            " '2026-11-09', ['pubmed'], 'journal', 'humans', 'none', true, 'noise'), "
            "('10.1/old', '10.1/old', '333', null, 'Old', 'Cell', '2026-10-01', "
            " '2026-10-01', ['pubmed'], 'journal', 'humans', 'none', true, 'disease'), "
            "('10.1/new', '10.1/new', null, null, 'No abstract', 'Cell', '2026-11-08', "
            " '2026-11-09', ['journals'], 'journal', 'unknown', 'none', true, 'technique')"
        )
    return path


# --- checks and sources -------------------------------------------------------------


def test_eight_copied_words_fail_and_own_words_pass():
    support = {f"f{i}": f"{s} {q}" for i, (s, q, _) in enumerate(FACTS, 1)}
    assert checks.check_text(GOOD_EN, support, [ABSTRACT]).passed
    report = checks.check_text(COPIED_EN, support, [ABSTRACT])
    assert not report.passed
    assert any("copies 8+ words" in p for p in report.summary())


def test_facts_whose_quote_is_not_in_the_abstract_are_rejected():
    assert checks.check_fact(*FACTS[0][:2], ABSTRACT) is None
    assert checks.check_fact(*FACTS[3][:2], ABSTRACT) == "quote not found verbatim in the source"


def test_abstract_from_pubmed_preprint_or_cached_full_text(tmp_path):
    cache_abstract(tmp_path)
    assert sources.abstract_for(STUDY, cache_root=tmp_path) == (ABSTRACT, "pubmed")

    preprint = {"study_id": "10.1101/x", "doi": "10.1101/x", "sources": ["biorxiv"]}
    path = tmp_path / "biorxiv" / "abstract" / "10.1101_x.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"doi": "10.1101/x", "version": 2, "abstract": ABSTRACT}))
    assert sources.abstract_for(preprint, cache_root=tmp_path) == (ABSTRACT, "biorxiv")

    jats = (
        "<article><front><article-meta>"
        "<abstract abstract-type='graphical'><p>Picture.</p></abstract>"
        f"<abstract><sec><title>Methods</title><p>{ABSTRACT}</p></sec></abstract>"
        "</article-meta></front><body><p>Full text never used.</p></body></article>"
    )
    full = tmp_path / "europepmc" / "fulltext" / "PMC9.xml"
    full.parent.mkdir(parents=True)
    full.write_text(jats)
    found = sources.abstract_for({"study_id": "x", "pmcid": "PMC9"}, cache_root=tmp_path)
    assert found == (f"Methods: {ABSTRACT}", "europepmc")
    assert sources.abstract_for({"study_id": "y", "pmcid": "PMC8"}, cache_root=tmp_path) is None


# --- the chain ------------------------------------------------------------------------


def test_studies_to_summarize_are_recent_typed_and_not_noise(tmp_path):
    rows = pipeline.studies_to_summarize(TODAY, make_warehouse(tmp_path / "w.duckdb"))
    assert [r["study_id"] for r in rows] == ["10.1/new", "10.1/spindles"]
    assert rows[1]["sources"] == ["pubmed"] and rows[1]["species"] == "animals"


def test_chain_publishes_verified_texts_and_skips_what_is_up_to_date(tmp_path):
    derived, cache = tmp_path / "derived", tmp_path / "cache"
    cache_abstract(cache)
    studies = pipeline.studies_to_summarize(TODAY, make_warehouse(tmp_path / "w.duckdb"))
    llm = FakeLLM()
    kw = {"derived_root": derived, "cache_root": cache, "now": NOW}

    result = pipeline.run_facts(llm, studies, **kw)
    assert (result.done, result.counts) == (1, {"no_abstract": 1, "ok": 1})
    doc = json.loads(facts_mod.facts_path("10.1/spindles", derived).read_text())
    assert [f["id"] for f in doc["facts"]] == ["f1", "f2", "f3"]
    assert doc["rejected"] == ["quote not found verbatim in the source"]
    assert "quote" not in json.dumps(doc["facts"])  # quotes stay in the cache
    assert json.loads(facts_mod.quotes_path("10.1/spindles", cache).read_text())["f1"]

    result = pipeline.run_write(llm, studies, **kw)
    assert result.counts == {"no_facts": 1, "en_verified": 1, "es_verified": 1}
    assert llm.calls == ["Extraction", "Summary", "AdaptedText"]
    assert fallback.summary_for(STUDY, "en", derived_root=derived)["kind"] == "fallback"
    assert pipeline.run_judge(PassingJudge(), studies, **kw).counts == {"passed": 1}
    for lang in ("en", "es"):
        shown = fallback.summary_for(STUDY, lang, derived_root=derived)
        assert shown["kind"] == "verified" and len(shown["sentences"]) == 3
    assert shown["sentences"][0]["fact_ids"] == ["f1"]

    again = FakeLLM()
    assert pipeline.run_facts(again, studies, **kw).up_to_date == 1
    assert pipeline.run_write(again, studies, **kw).up_to_date == 1
    assert again.calls == []


def test_a_text_that_fails_twice_goes_to_review_and_the_site_shows_the_fallback(tmp_path):
    derived, cache = tmp_path / "derived", tmp_path / "cache"
    cache_abstract(cache)
    studies = [STUDY]
    llm = FakeLLM(english=COPIED_EN)
    kw = {"derived_root": derived, "cache_root": cache, "now": NOW}
    pipeline.run_facts(llm, studies, **kw)
    result = pipeline.run_write(llm, studies, **kw)
    assert result.counts == {"en_failed": 1}
    assert llm.calls == ["Extraction", "Summary", "Summary"]  # one retry, then no Spanish
    review = json.loads(
        write_mod.text_path("10.1/spindles", "en", verified=False, derived_root=derived)
        .read_text()
    )  # fmt: skip
    assert review["status"] == "failed" and review["sentences"] == []  # nothing copied kept
    assert review["problems"] == ["sentence 2: copies 8+ words from a source"]
    assert fallback.summary_for(STUDY, "es", derived_root=derived) == {
        "kind": "fallback",
        "text": "Estudio en animales publicado en Neuron el 5 de noviembre de 2026.",
    }
    assert pipeline.run_write(FakeLLM(), studies, **kw).up_to_date == 1  # not asked again

    # A new prompt version writes it again; a verified text retires the failed one.
    real = write_mod.prompt
    write_mod.prompt = lambda n: (real(n)[0], real(n)[1] + "-next")
    try:
        assert pipeline.run_write(FakeLLM(), studies, **kw).counts["en_verified"] == 1
    finally:
        write_mod.prompt = real
    assert not write_mod.text_path("10.1/spindles", "en", verified=False,
                                   derived_root=derived).exists()  # fmt: skip


def test_limit_counts_model_calls(tmp_path):
    cache_abstract(tmp_path)
    cache_abstract(tmp_path, pmid="112")
    two = [STUDY, {**STUDY, "study_id": "10.1/other", "pmid": "112"}]
    result = pipeline.run_facts(FakeLLM(), two, limit=1, derived_root=tmp_path / "d",
                                cache_root=tmp_path, now=NOW)  # fmt: skip
    assert result.done == 1


def test_fallback_uses_only_the_data_and_leaves_gaps_out():
    preprint = {**STUDY, "review_status": "preprint", "journal": "bioRxiv",
                "species": "unknown", "integrity": "corrected"}  # fmt: skip
    assert fallback.fallback_text(preprint, "en") == (
        "Preprint published in bioRxiv on 5 November 2026. It has not been peer reviewed "
        "yet. A correction has been published."
    )
    bare = {"study_id": "pmid:1", "review_status": "unknown", "species": "humans"}
    assert fallback.fallback_text(bare, "es") == "Estudio en humanos publicado."


def test_spanish_that_fails_twice_keeps_the_english_and_falls_back_in_spanish(tmp_path):
    derived, cache = tmp_path / "derived", tmp_path / "cache"
    cache_abstract(cache)

    class TypoLLM(FakeLLM):
        def complete_json(self, system, user, output, max_tokens):
            answer = super().complete_json(system, user, output, max_tokens)
            if output.__name__ == "AdaptedText":
                answer.sentences[1].text = answer.sentences[1].text.replace("animales", "animlaes")
            return answer

    llm = TypoLLM()
    kw = {"derived_root": derived, "cache_root": cache, "now": NOW}
    pipeline.run_facts(llm, [STUDY], **kw)
    assert pipeline.run_write(llm, [STUDY], **kw).counts == {"en_verified": 1, "es_failed": 1}
    assert llm.calls.count("AdaptedText") == 2  # one retry with the problems
    review = json.loads(write_mod.text_path("10.1/spindles", "es", verified=False,
                                            derived_root=derived).read_text())  # fmt: skip
    assert review["problems"] == ["sentence 2: words not in the Spanish dictionary ['animlaes']"]
    pipeline.run_judge(PassingJudge(), [STUDY], **kw)  # judges the English alone
    assert fallback.summary_for(STUDY, "en", derived_root=derived)["kind"] == "verified"
    assert fallback.summary_for(STUDY, "es", derived_root=derived)["kind"] == "fallback"


def test_fallback_text_names_a_future_print_issue_not_a_day() -> None:
    from synaptica.narrative.fallback import fallback_text

    s = {"species": "animals", "journal": "Glia", "review_status": "journal",
         "published_on": "2027-01-01", "entered_on": "2026-11-13"}  # fmt: skip
    assert (
        fallback_text(s, "es")
        == "Estudio en animales publicado en Glia en el número de enero de 2027."
    )
    assert fallback_text(s | {"published_on": "2026-11-12"}, "en") == (
        "Study in animals published in Glia on 12 November 2026."
    )


def test_quota_order_is_by_tiers_then_newest(tmp_path):
    """SCOPE §8: (1) journal feeds, (2) linked to the media (empty for now), (3) the rest
    published in a journal, (4) preprints and unknown; newest first within each tier."""
    path = tmp_path / "w.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute(
            "create table dim_study (study_id varchar, doi varchar, pmid varchar, pmcid "
            "varchar, title varchar, journal varchar, published_on date, entered_on date, "
            "sources varchar[], review_status varchar, species varchar, integrity varchar, "
            "news_candidate boolean, news_type varchar)"
        )
        rows = [  # (id, entered, sources, review status, published)
            ("pre-new", "2026-11-09", ["biorxiv"], "preprint", "2026-11-09"),
            ("unknown", "2026-11-09", ["europepmc"], "unknown", "2026-11-09"),
            ("journal-old", "2026-11-05", ["pubmed"], "journal", "2026-11-04"),
            ("journal-issue", "2026-11-08", ["pubmed"], "journal", "2027-01-01"),
            ("journal-new", "2026-11-08", ["pubmed"], "journal", "2026-11-08"),
            ("nsc-old", "2026-11-04", ["journals"], "journal", "2026-11-04"),
        ]
        for sid, entered, sources, review, published in rows:
            con.execute(
                "insert into dim_study values (?, ?, null, null, 'T', 'J', ?, ?, ?, ?, "
                "'humans', 'none', true, 'disease')",
                [sid, sid, published, entered, sources, review],
            )
    got = [r["study_id"] for r in pipeline.studies_to_summarize(TODAY, path)]
    assert got == ["nsc-old", "journal-issue", "journal-new", "journal-old", "pre-new",
                   "unknown"]  # fmt: skip
