"""News types (step 14a): what is classified, batches, cache by input and prompt, metrics.

The gold file in tests/fixtures/eval/ is synthetic, written for these tests: it is not a
label set and says nothing about the real classifier (Sofía's labels come in step 14b).
"""

import datetime as dt

import duckdb
import pytest

from synaptica.config import project_root
from synaptica.news import classify, evaluate

TODAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)
GOLD = project_root() / "tests" / "fixtures" / "eval" / "news_gold_synthetic.csv"


class FakeLLM:
    """Types by keyword; leaves out lines with "skip"."""

    label = "fake/model"

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(user)
        items = []
        for line in user.splitlines()[1:]:
            index, text = line.split(". ", 1)
            if "skip" in text:
                continue
            kind = "disease" if "alzheimer" in text.lower() else "healthy_brain"
            items.append({"index": int(index), "type": kind})
        return output.model_validate({"items": items})


def make_warehouse(path, nsc=False):
    with duckdb.connect(str(path)) as con:
        con.execute("create table dim_study (study_id varchar, title varchar, "
                    "news_candidate boolean, entered_on date, sources varchar[], "
                    "is_neuro boolean)")  # fmt: skip
        con.execute(
            "insert into dim_study values "
            "('10.1/a', 'Alzheimer study', true, '2026-11-09', ['pubmed'], true), "
            "('10.1/b', 'A review', false, '2026-11-09', ['pubmed'], true), "
            "('10.1/c', 'Old study', true, '2026-10-01', ['pubmed'], true), "
            "('10.1/d', 'Sleep spindles skip', true, '2026-11-08', ['pubmed'], true)"
        )
        if nsc:
            con.execute(
                "insert into dim_study values "
                "('10.1/n', 'Nature paper', false, '2026-11-09', ['journals'], true), "
                "('10.1/m', 'Nature, not neuro', false, '2026-11-09', ['journals'], false)"
            )
        con.execute(
            "create table fct_news_item (news_item_id varchar, title varchar, "
            "feed_summary varchar, lang varchar, is_neuro boolean, entered_on date)"
        )
        con.execute("insert into fct_news_item values "
                    "('news:x', 'El cerebro', 'Resumen del medio', 'es', true, '2026-11-09'), "
                    "('news:y', 'Volcanes', null, 'es', false, '2026-11-09')")  # fmt: skip
    return path


def test_only_prefiltered_studies_and_neuro_news_of_the_window_are_classified(tmp_path):
    items = classify.items_to_classify(TODAY, make_warehouse(tmp_path / "w.duckdb", nsc=True))
    # A Nature, Science or Cell paper is not a Latest candidate but is shown with its type.
    assert sorted(items) == ["news:x", "study:10.1/a", "study:10.1/d", "study:10.1/n"]
    assert items["news:x"]["summary"] == "Resumen del medio"


def test_batches_cache_and_prompt_version(tmp_path, monkeypatch):
    items = classify.items_to_classify(TODAY, make_warehouse(tmp_path / "w.duckdb"))
    monkeypatch.setattr(classify, "BATCH", 2)
    llm = FakeLLM()
    result = classify.classify(llm, items, derived_root=tmp_path, now=NOW)
    assert (result.total, result.classified, result.missing) == (3, 2, 1)
    assert len(llm.calls) == 2
    assert "[es] El cerebro — Resumen del medio" in "".join(llm.calls)
    rows = classify.load_types(classify.types_path(tmp_path))
    assert rows["study:10.1/a"]["type"] == "disease"
    assert rows["study:10.1/a"]["prompt_version"] == "types-v1"

    again = FakeLLM()
    second = classify.classify(again, items, derived_root=tmp_path, now=NOW)
    assert (second.up_to_date, second.classified) == (2, 0)
    assert len(again.calls) == 1 and "skip" in again.calls[0]  # only the left-out one

    changed = {**items, "news:x": {**items["news:x"], "title": "El cerebro, corregido"}}
    third = FakeLLM()
    classify.classify(third, changed, derived_root=tmp_path, now=NOW)
    assert "corregido" in third.calls[0]

    real = classify.prompt
    monkeypatch.setattr(classify, "prompt", lambda n: (real(n)[0], "types-v2"))
    bumped = classify.classify(FakeLLM(), items, derived_root=tmp_path, now=NOW)
    assert bumped.up_to_date == 0


def test_limit_takes_the_newest(tmp_path):
    items = classify.items_to_classify(TODAY, make_warehouse(tmp_path / "w.duckdb"))
    llm = FakeLLM()
    classify.classify(llm, items, derived_root=tmp_path, limit=1, now=NOW)
    assert llm.calls[0].count("\n") == 1 and "Alzheimer" in llm.calls[0]


def test_scores_per_class_and_macro_f1():
    gold = ["disease", "disease", "technique", "noise"]
    pred = ["disease", "technique", "technique", None]
    s = evaluate.scores(gold, pred)
    assert s["per_class"]["disease"] == {"precision": 1.0, "recall": 0.5,
                                         "f1": pytest.approx(2 / 3), "support": 2}  # fmt: skip
    assert s["per_class"]["technique"]["precision"] == 0.5
    assert s["macro_f1"] == pytest.approx((2 / 3 + 2 / 3 + 0) / 3)  # classes in the gold
    assert s["accuracy"] == 0.5 and s["confusion"]["noise"] == {None: 1}


def test_evaluate_scores_the_llm_and_a_cross_validated_baseline():
    gold = evaluate.load_gold(GOLD)
    llm = {r["key"]: r["type"] for r in gold[:-1]}  # one item without an answer
    result = evaluate.evaluate(gold, llm)
    assert result["labelled"] == 15 and result["llm_missing"] == 1
    assert result["llm"]["accuracy"] == pytest.approx(14 / 15)
    assert 0 <= result["baseline"]["macro_f1"] <= 1 and result["baseline"]["n"] == 15
    report = evaluate.report_markdown(result)
    assert "| llm | " in report and "| baseline | " in report


def test_unknown_types_in_the_gold_are_rejected(tmp_path):
    bad = tmp_path / "labels.csv"
    bad.write_text("key,lang,text,type\na,en,x,politics\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown type"):
        evaluate.load_gold(bad)
