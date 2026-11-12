"""Weekly summary (step 25): which studies, the same chain, checks and judge, the
fallback from data. Synthetic texts; fake models only."""

import datetime as dt
import json

import duckdb
import pytest

from synaptica.narrative import pipeline, weekly
from test_narrative import ES, GOOD_EN, STUDY, FakeLLM, cache_abstract
from test_narrative_judge import FakeJudge

NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)
WEEK = "2026-W45"  # 2 to 8 November 2026
OTHER = {**STUDY, "study_id": "10.1/second", "doi": "10.1/second", "pmid": "112",
         "journal": "bioRxiv", "review_status": "preprint"}  # fmt: skip
WEEKLY_EN = [
    (GOOD_EN[0][0], ["s1-f1"]),
    (GOOD_EN[1][0], ["s1-f2"]),
    (GOOD_EN[2][0], ["s1-f3"]),
    ("A second team, also working with 24 adult mice over 10 nights, looked at the same "
     "question in a preprint.", ["s2-f1"]),
    ("There too, animals with more spindles were better at finding a hidden platform the "
     "following day.", ["s2-f2"]),
    ("Its authors also say spindles may help store memories, pending confirmation in other "
     "species.", ["s2-f3"]),
]  # fmt: skip
WEEKLY_ES = [
    *ES,
    "Un segundo equipo, también con 24 ratones adultos durante 10 noches, estudió la misma "
    "cuestión en un preprint.",
    "También allí, los animales con más husos encontraron mejor una plataforma oculta al día "
    "siguiente.",
    "Sus autores señalan que los husos podrían ayudar a guardar recuerdos, a falta de "
    "confirmarlo en otras especies.",
]


class WeeklyLLM(FakeLLM):
    label = "groq/qwen/qwen3.8-27b"

    def complete_json(self, system, user, output, max_tokens):
        if "Study s1" in user:  # the weekly prompt
            self.calls.append("Weekly")
            data = {"sentences": [{"text": t, "fact_ids": f} for t, f in WEEKLY_EN]}
            return output.model_validate(data)
        if output.__name__ == "AdaptedText" and "6. " in user:
            data = {"sentences": [{"index": i, "text": t} for i, t in enumerate(WEEKLY_ES, 1)]}
            return output.model_validate(data)
        return super().complete_json(system, user, output, max_tokens)


@pytest.fixture
def week(tmp_path):
    derived, cache = tmp_path / "derived", tmp_path / "cache"
    warehouse = tmp_path / "w.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute(
            "create table dim_study (study_id varchar, doi varchar, pmid varchar, pmcid "
            "varchar, title varchar, journal varchar, published_on date, entered_on date, "
            "sources varchar[], review_status varchar, species varchar, integrity varchar, "
            "news_candidate boolean, news_type varchar)"
        )
        con.execute(
            "insert into dim_study values "
            "('10.1/spindles', '10.1/spindles', '111', null, 'Spindles', 'Neuron', "
            " '2026-11-05', '2026-11-06', ['pubmed'], 'journal', 'animals', 'none', true, "
            " 'healthy_brain'), "
            "('10.1/second', '10.1/second', '112', null, 'Second', 'bioRxiv', "
            " '2026-11-05', '2026-11-05', ['pubmed'], 'preprint', 'animals', 'none', true, "
            " 'technique'), "
            "('10.1/unwritten', '10.1/unwritten', '113', null, 'No text', 'Cell', "
            " '2026-11-05', '2026-11-07', ['pubmed'], 'journal', 'humans', 'none', true, "
            " 'disease'), "
            "('10.1/later', '10.1/later', '114', null, 'Next week', 'Cell', "
            " '2026-11-05', '2026-11-09', ['pubmed'], 'journal', 'humans', 'none', true, "
            " 'disease')"
        )
    for pmid in ("111", "112", "113"):
        cache_abstract(cache, pmid=pmid)
    kw = {"derived_root": derived, "cache_root": cache, "now": NOW}
    writer = WeeklyLLM()
    for study in (STUDY, OTHER):
        pipeline.run_facts(writer, [study], **kw)
        pipeline.run_write(writer, [study], **kw)
        pipeline.run_judge(FakeJudge(), [study], **kw)
    return kw, warehouse


def test_the_week_takes_studies_with_a_published_summary_by_type(week):
    kw, warehouse = week
    rows = weekly.candidates(WEEK, warehouse)
    assert [r["study_id"] for r in rows] == ["10.1/unwritten", "10.1/spindles", "10.1/second"]
    chosen = weekly.choose(rows, kw["derived_root"])
    assert [r["study_id"] for r in chosen] == ["10.1/spindles", "10.1/second"]  # by type
    assert weekly.last_week(dt.date(2026, 11, 12)) == WEEK


def test_the_weekly_summary_goes_through_the_chain_and_the_judge(week):
    kw, warehouse = week
    chosen = weekly.choose(weekly.candidates(WEEK, warehouse), kw["derived_root"])
    writer, judge = WeeklyLLM(), FakeJudge()
    status = weekly.write_weekly(writer, judge, WEEK, chosen, **kw)
    assert status == "published" and writer.calls == ["Weekly"]
    assert "[Study s2] Second" in judge.users[0] and "ES 6. " in judge.users[0]
    for lang in ("en", "es"):
        shown = weekly.weekly_for(WEEK, chosen, lang, derived_root=kw["derived_root"])
        assert shown["kind"] == "verified" and len(shown["sentences"]) == 6
    assert weekly.is_up_to_date(WEEK, chosen, kw["derived_root"])


def test_a_rejected_week_falls_back_to_a_sentence_from_the_data(week):
    kw, warehouse = week
    chosen = weekly.choose(weekly.candidates(WEEK, warehouse), kw["derived_root"])
    status = weekly.write_weekly(WeeklyLLM(), FakeJudge(passed=False), WEEK, chosen, **kw)
    assert status == "rejected_by_judge"
    path = weekly.weekly_path(WEEK, "es", verified=False, derived_root=kw["derived_root"])
    review = json.loads(path.read_text())
    assert review["problems"] == ["judge: Says … as a fact"]
    assert weekly.weekly_for(WEEK, chosen, "es", derived_root=kw["derived_root"]) == {
        "kind": "fallback",
        "text": "Semana del 2 de noviembre al 8 de noviembre de 2026: 2 estudios resumidos, "
        "2 en animales, 1 sin revisión por pares (preprints).",
    }
    assert weekly.is_up_to_date(WEEK, chosen, kw["derived_root"])  # not asked again


def test_one_study_is_not_a_week(week):
    kw, _ = week
    assert weekly.write_weekly(WeeklyLLM(), FakeJudge(), WEEK, [STUDY], **kw) == "too_few"
    assert weekly.weekly_fallback(WEEK, [], "en") == (
        "Week of 2 November to 8 November 2026: no studies summarized."
    )
