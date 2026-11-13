"""Neuroscience filter for the general sources (step 13): OpenAlex rules, then a fake LLM."""

import datetime as dt
import json

from synaptica.ingest import journals, news, openalex
from synaptica.news import neuro

DAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)


class FakeLLM:
    """Says neuro when the line mentions the brain (EN/ES); leaves out lines with "skip"."""

    label = "fake/model"

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(user)
        items = []
        for line in user.splitlines()[1:]:
            index, text = line.split(". ", 1)
            if "skip" not in text:
                is_neuro = any(w in text.lower() for w in ("brain", "cerebro"))
                items.append({"index": int(index), "neuro": is_neuro})
        return output.model_validate({"items": items})


def topic(field, subfield="0000"):
    return {"field": field, "subfield": subfield}


def seed(tmp_path):
    journals.store(tmp_path).save({
        "10.1/neuro": {"doi": "10.1/neuro", "journal": "nature", "title": "Synapses A",
                       "url": "https://n/1", "published": "2026-11-08T00:00:00Z"},
        "10.1/neurology": {"doi": "10.1/neurology", "journal": "science", "title": "Stroke",
                           "url": "https://n/2"},
        "10.1/physics": {"doi": "10.1/physics", "journal": "cell", "title": "Brain-like quark",
                         "url": "https://n/3"},
        "10.1/second": {"doi": "10.1/second", "journal": "nature", "title": "Mouse brain fat",
                        "url": "https://n/4", "section": "Article"},
        "10.1/unknown": {"doi": "10.1/unknown", "journal": "nature", "title": "Black holes",
                         "url": "https://n/5"},
        "10.1/neuron": {"doi": "10.1/neuron", "journal": "neuron", "title": "Not asked",
                        "url": "https://n/6"},
    }, DAY)  # fmt: skip
    openalex.store(tmp_path).save({
        "10.1/neuro": {"primary_topic": topic("28"), "topics": [topic("28")]},
        "10.1/neurology": {"primary_topic": topic("27", "2728"), "topics": []},
        "10.1/physics": {"primary_topic": topic("31"), "topics": [topic("31")]},
        "10.1/second": {"primary_topic": topic("13"), "topics": [topic("13"), topic("28")]},
    }, DAY)  # fmt: skip
    news.store(tmp_path).save({
        "a": {"feed": "sinc_noticias", "title": "El cerebro y el sueño", "lang": "es",
              "url": "https://s/a", "summary": "Un estudio en ratones."},
        "b": {"feed": "sinc_noticias", "title": "Volcanes skip", "lang": "es",
              "url": "https://s/b"},
        "c": {"feed": "sciencedaily_neuroscience", "title": "Neuro feed: not asked",
              "lang": "en", "url": "https://sd/c"},
    }, DAY)  # fmt: skip


def run(tmp_path, llm=None, **kwargs):
    return neuro.decide(llm, today=DAY, raw_root=tmp_path, derived_root=tmp_path / "derived",
                        now=NOW, **kwargs)  # fmt: skip


def rows(tmp_path):
    return neuro.load_decisions(neuro.decisions_path(tmp_path / "derived"))


def test_rules_decide_from_openalex_and_leave_the_rest_undecided_without_llm(tmp_path):
    seed(tmp_path)
    result = run(tmp_path)
    assert result.items == 7  # 5 general journal items + 2 SINC; neuro sources not asked
    assert result.by_basis == {"openalex:neuro": 2, "openalex:not": 1}
    assert result.undecided == 4 and result.llm_asked == 0
    decided = rows(tmp_path)
    assert decided["journals:10.1/neuro"] == {
        "key": "journals:10.1/neuro",
        "is_neuro": True,
        "basis": "openalex",
    }
    assert decided["journals:10.1/neurology"]["is_neuro"]
    assert not decided["journals:10.1/physics"]["is_neuro"]  # "Brain-like" in the title
    assert "journals:10.1/second" not in decided  # neuro only as a secondary topic


def test_the_llm_gets_only_what_the_rules_could_not_decide(tmp_path):
    seed(tmp_path)
    llm = FakeLLM()
    result = run(tmp_path, llm)
    assert result.llm_asked == 3 and result.undecided == 1  # the model skipped one
    assert len(llm.calls) == 1
    asked = llm.calls[0]
    assert "(Article) Mouse brain fat" in asked and "Black holes" in asked
    assert "[es] El cerebro y el sueño — Un estudio en ratones." in asked
    assert "Synapses A" not in asked and "Not asked" not in asked
    decided = rows(tmp_path)
    assert decided["journals:10.1/second"]["is_neuro"]
    assert not decided["journals:10.1/unknown"]["is_neuro"]
    assert decided["news:a"] | {"decided_at": "x"} == {
        "key": "news:a", "is_neuro": True, "basis": "llm",
        "input_hash": neuro.input_hash({"title": "El cerebro y el sueño",
                                        "summary": "Un estudio en ratones."}),
        "prompt_version": "neuro-v1", "generator": "fake/model", "decided_at": "x",
    }  # fmt: skip


def test_answers_are_kept_until_the_input_or_the_prompt_changes(tmp_path, monkeypatch):
    seed(tmp_path)
    run(tmp_path, FakeLLM())
    again = FakeLLM()
    assert run(tmp_path, again).llm_asked == 0
    assert len(again.calls) == 1 and again.calls[0].count("\n") == 1  # only the skipped one
    assert "Volcanes skip" in again.calls[0]

    news.store(tmp_path).save(
        {"a": {"feed": "sinc_noticias", "title": "El cerebro, corregido", "lang": "es",
               "url": "https://s/a"}}, DAY + dt.timedelta(days=1))  # fmt: skip
    changed = FakeLLM()
    neuro.decide(changed, today=DAY + dt.timedelta(days=1), raw_root=tmp_path,
                 derived_root=tmp_path / "derived", now=NOW)  # fmt: skip
    assert "El cerebro, corregido" in changed.calls[0] and "Black holes" not in changed.calls[0]

    real_prompt = neuro.prompt
    monkeypatch.setattr(neuro, "prompt", lambda n: (real_prompt(n)[0], "neuro-v2"))
    bumped = FakeLLM()
    assert run(tmp_path, bumped).llm_asked == 3  # every LLM row asked again (+ the skip)
    assert bumped.calls[0].count("\n") == 4


def test_rules_override_an_older_llm_answer_once_openalex_knows(tmp_path):
    seed(tmp_path)
    run(tmp_path, FakeLLM())
    assert rows(tmp_path)["journals:10.1/unknown"]["basis"] == "llm"
    openalex.store(tmp_path).save(
        {"10.1/unknown": {"primary_topic": topic("31"), "topics": [topic("31")]}}, DAY
    )
    run(tmp_path)
    assert rows(tmp_path)["journals:10.1/unknown"] == {
        "key": "journals:10.1/unknown",
        "is_neuro": False,
        "basis": "openalex",
    }


def test_limit_asks_the_newest_first(tmp_path):
    seed(tmp_path)
    llm = FakeLLM()
    run(tmp_path, llm, limit=1)
    assert llm.calls[0].count("\n") == 1  # one item
    assert json.loads(neuro.decisions_path(tmp_path / "derived").read_text("utf-8"))
