"""Sofía's labels of Neuro News headlines (plan, step 14b, option C): a few a day in her
review page, only keys and types in her log, the gold file ``key,type``. No network: a
small warehouse in ``tmp_path`` and made-up headlines."""

from __future__ import annotations

import datetime as dt
import json
import typing
from collections import Counter
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from synaptica.config import project_root
from synaptica.news import classify, evaluate, labels
from synaptica.review import collect
from synaptica.review.apply import Event, read_log, state
from synaptica.review.models import Action, Decision, ItemType, Label, Queue
from synaptica.review.page import render
from test_review_collect import decide
from test_site_news import study, warehouse

WEDNESDAY, SATURDAY = dt.date(2026, 11, 25), dt.date(2026, 11, 28)
# Ten of each type: studies for the first four, outlet news for "noise".
LLM = {f"study:doi:10.1/{t}{n}": t for t in classify.TYPES[:4] for n in range(10)} | {
    f"news:{n}": "noise" for n in range(10)
}


def data_dir(tmp_path: Path) -> Path:
    studies = [study(k.removeprefix("study:"), title=f"Headline {k}") for k in LLM if "study" in k]
    news = [{"news_item_id": f"news:{n}", "story_id": f"news:{n}", "origin": "outlet",
             "feed": "sinc", "outlet": "SINC", "lang": "es", "url": f"https://sinc.es/{n}",
             "title": f"Titular {n}", "published_at": dt.datetime(2026, 11, 20, 9),
             "entered_on": dt.date(2026, 11, 20), "is_neuro": True} for n in range(10)]  # fmt: skip
    data = warehouse(tmp_path / "data", studies, news)
    with duckdb.connect(str(data / "warehouse.duckdb")) as con:
        con.execute("alter table fct_news_item add column feed_summary varchar")
        con.execute("update fct_news_item set feed_summary = 'Resumen del medio'")
    path = classify.types_path(data / "derived")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"key": k, "type": t} for k, t in LLM.items()]))
    return data


def queue(data: Path, today: dt.date = WEDNESDAY) -> Queue:
    return collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", today,
                           glossary=[], region_terms=[])  # fmt: skip


def to_label(q: Queue) -> list:
    return [i for i in q.items if i.item_type is ItemType.NEWS_LABEL]


def test_her_types_are_the_classifier_types():
    assert typing.get_args(Label.model_fields["type"].annotation) == classify.TYPES
    page = (project_root() / "src/synaptica/review/template.html").read_text("utf-8")
    assert all(f'["{t}", ' in page for t in classify.TYPES)


def test_stratified_takes_the_types_in_turns_and_is_stable():
    order = labels.stratified(LLM)
    assert sorted(order) == sorted(LLM)
    first = [LLM[k] for k in order[:10]]
    assert first == list(classify.TYPES) * 2
    assert labels.stratified(dict(reversed(LLM.items()))) == order


def test_a_label_decision_carries_only_the_type():
    base = {
        "item_type": "news_label",
        "item_id": "news_1",
        "content_sha256": "0" * 64,
        "reviewed_by": "sofia",
        "reviewed_at": "2026-11-19T10:00:00Z",
        "source": "issue#20",
    }
    assert Decision.model_validate(base | {"action": "label", "payload": {"type": "noise"}})
    with pytest.raises(ValidationError):
        Decision.model_validate(base | {"action": "label", "payload": {"type": "politics"}})
    with pytest.raises(ValidationError):
        Decision.model_validate(base | {"action": "approve", "payload": {}})
    with pytest.raises(ValidationError):
        Decision.model_validate(base | {"item_type": "glossary", "action": "label",
                                        "payload": {"type": "noise"}})  # fmt: skip


def test_none_before_the_19th(tmp_path: Path):
    data = data_dir(tmp_path)
    assert to_label(queue(data, dt.date(2026, 11, 18))) == []
    assert len(to_label(queue(data, dt.date(2026, 11, 19)))) == labels.PER_WEEKDAY


def test_ten_a_weekday_with_every_type_three_at_the_weekend(tmp_path: Path):
    data = data_dir(tmp_path)
    items = to_label(queue(data))
    assert Counter(LLM[i.content.key] for i in items) == {t: 2 for t in classify.TYPES}
    assert len(to_label(queue(data, SATURDAY))) == labels.PER_WEEKEND
    news = next(i for i in items if i.content.key.startswith("news:"))
    assert news.item_id == news.content.key.replace(":", "_")
    assert (news.content.lang, news.content.source) == ("es", "SINC")
    assert news.content.url.startswith("https://sinc.es/")
    trial = next(i for i in items if LLM[i.content.key] == "clinical_trial")
    assert trial.content.url.startswith("https://doi.org/10.1/")
    assert "Resumen del medio" not in render(queue(data), "public")  # the page is public


def test_labelled_ones_leave_and_the_target_stops_them(tmp_path: Path, monkeypatch):
    data = data_dir(tmp_path)
    first = to_label(queue(data))
    for n, item in enumerate(first[:3], 1):
        decide(data, item, Action.LABEL, {"type": "disease"}, n=n)
    keys = {i.key for i in to_label(queue(data))}
    assert len(keys) == labels.PER_WEEKDAY and not keys & {i.key for i in first[:3]}
    monkeypatch.setattr(collect, "LABELS_TARGET", 5)  # two left: only two today
    assert len(to_label(queue(data))) == 2
    monkeypatch.setattr(labels, "TARGET", 3)  # reached: none at all
    assert to_label(queue(data)) == []


def test_her_label_settles_the_item(tmp_path: Path):
    data = data_dir(tmp_path)
    item = to_label(queue(data))[0]
    decide(data, item, Action.LABEL, {"type": "technique"})
    st = state(item, read_log(data / "review"))
    assert (st.status, st.label) == ("decided", "technique")


def test_gold_rows_undo_the_item_ids_and_keep_her_last_type(tmp_path: Path):
    data = data_dir(tmp_path)
    a, b = to_label(queue(data))[:2]
    decide(data, a, Action.LABEL, {"type": "noise"}, n=1)
    decide(data, b, Action.LABEL, {"type": "disease"}, n=2)
    decide(data, a, Action.LABEL, {"type": "technique"}, n=3)
    rows = labels.gold_rows(read_log(data / "review"), LLM)
    assert rows == sorted([(a.content.key, "technique"), (b.content.key, "disease")])
    assert labels.gold_csv(rows).splitlines()[0] == "key,type"
    with pytest.raises(ValueError, match="share the item id"):
        labels.gold_rows([], ["news:a/b", "news:a_b"])
    with pytest.raises(ValueError, match="no longer classified"):
        labels.gold_rows(read_log(data / "review"), ["news:other"])


def test_gold_file_round_trips_into_the_evaluation(tmp_path: Path):
    data = data_dir(tmp_path)
    events = [
        Event(Decision(item_type=ItemType.NEWS_LABEL, item_id=labels.item_id(k),
                       action=Action.LABEL, content_sha256="0" * 64, payload={"type": t},
                       reviewed_by="sofia",
                       reviewed_at=dt.datetime(2026, 11, 19, tzinfo=dt.UTC), source="issue#1"))
        for k, t in LLM.items()
    ]  # fmt: skip
    gold = tmp_path / "labels.csv"
    gold.write_text(labels.gold_csv(labels.gold_rows(events, LLM)), encoding="utf-8")
    rows = evaluate.load_gold(gold)
    texts = labels.label_texts([r["key"] for r in rows], data / "warehouse.duckdb")
    assert texts["news:3"] == "Titular 3 — Resumen del medio"  # what the classifier saw
    result = evaluate.evaluate(rows, LLM, texts)
    assert result["llm"]["accuracy"] == 1.0 and result["no_text"] == 0
