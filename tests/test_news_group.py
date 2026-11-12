"""Same-story grouping (step 15): candidate pairs, cached answers, union-find, metrics."""

import datetime as dt
import json

import pytest

from synaptica.news import evaluate, group

D = dt.datetime(2026, 11, 9, 10, tzinfo=dt.UTC)


def item(title, lang="en", days=0, summary=None):
    return {"title": title, "summary": summary, "lang": lang,
            "published": D - dt.timedelta(days=days)}  # fmt: skip


ITEMS = {
    "news:a": item("Mice sleep spindles boost memory"),
    "news:b": item("Los husos del sueño mejoran la memoria en ratones", "es", days=1),
    "news:c": item("Sleep spindles and memory, in mice", days=2),
    "news:d": item("A new drug for migraine", days=1),
    "news:e": item("Mice sleep spindles, old story", days=9),  # outside every window
}


class FakeJudge:
    """Same story when both lines mention spindles (or husos)."""

    label = "fake/model"

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(user)
        pairs = []
        lines = user.splitlines()[1:]
        for a_line, b_line in zip(lines[::2], lines[1::2], strict=True):
            index = int(a_line.split(".", 1)[0])
            same = all(any(w in x.lower() for w in ("spindle", "husos")) for x in (a_line, b_line))
            pairs.append({"index": index, "same": same})
        return output.model_validate({"pairs": pairs})


def test_candidates_are_the_pairs_within_five_days():
    pairs = group.candidate_pairs(ITEMS)
    assert ("news:a", "news:b") in pairs and ("news:a", "news:d") in pairs
    assert not any("news:e" in p for p in pairs)  # 7+ days from the rest


def test_same_story_across_languages_by_union_find_and_cached_answers(tmp_path):
    judge = FakeJudge()
    result = group.group_news(judge, ITEMS, derived_root=tmp_path)
    assert result == {"items": 5, "candidates": 6, "same": 3, "groups": 3, "grouped": 3}
    assert "[es] Los husos del sueño" in judge.calls[0]
    rows = {r["key"]: r["group"] for r in json.loads(group.groups_path(tmp_path).read_text())}
    assert rows["news:a"] == rows["news:b"] == rows["news:c"] == "news:a"
    assert rows["news:d"] == "news:d" and rows["news:e"] == "news:e"

    again = FakeJudge()
    group.group_news(again, ITEMS, derived_root=tmp_path)
    assert again.calls == []  # every pair answered for the same inputs and prompt

    changed = {**ITEMS, "news:d": item("A new drug for migraine, updated", days=1)}
    third = FakeJudge()
    group.group_news(third, changed, derived_root=tmp_path)
    assert all("migraine, updated" in line for line in third.calls[0].splitlines()[1::2]
               if "migraine" in line)  # fmt: skip


def test_groups_union_find_is_transitive():
    assert group.groups(["a", "b", "c", "d"], [("b", "c"), ("a", "c")]) == {
        "a": "a",
        "b": "a",
        "c": "a",
        "d": "d",
    }


def test_pair_metrics_for_answers_and_tfidf(tmp_path):
    gold = tmp_path / "pairs.csv"
    gold.write_text(
        "key_a,key_b,text_a,text_b,same\n"
        "a,b,Sleep spindles help mice remember,Sleep spindles help mice remember things,yes\n"
        "a,d,Sleep spindles help mice remember,A new drug for migraine,no\n"
        "c,d,Sleep spindles in mice,A new drug for migraine,no\n"
        "b,c,Sleep spindles help mice remember things,Spindles while mice sleep,yes\n",
        encoding="utf-8",
    )
    pairs = evaluate.load_pairs(gold)
    answers = {("a", "b"): True, ("a", "d"): True}  # one right, one wrong, one missing
    result = evaluate.evaluate_pairs(pairs, answers)
    assert result["llm"]["precision"] == 0.5 and result["llm"]["recall"] == 0.5
    assert result["tfidf"]["pairs"] == 4 and 0 <= result["tfidf"]["f1"] <= 1
    assert "| llm | 4 (2) |" in evaluate.pairs_markdown(result)


def test_pair_labels_must_be_yes_or_no(tmp_path):
    bad = tmp_path / "pairs.csv"
    bad.write_text("key_a,key_b,text_a,text_b,same\na,b,x,y,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="yes or no"):
        evaluate.load_pairs(bad)
