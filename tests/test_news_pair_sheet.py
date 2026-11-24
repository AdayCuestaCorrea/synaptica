"""Blind sheet of same-story pairs (step 15, option A), on a small warehouse, without network
and without any LLM."""

import csv
import datetime as dt
import json

import duckdb
import pytest
from typer.testing import CliRunner

from synaptica.news import evaluate, pair_sheet

D = dt.datetime(2026, 11, 14, 9, tzinfo=dt.UTC)
# key, lang, outlet, title, summary (synthetic: no feed text in the fixtures)
ROWS = [
    ("news:a", "en", "ScienceDaily", "Sleep spindles help mice remember", "Spindles in sleep."),
    ("news:b", "en", "The Conversation", "Sleep spindles help mice remember", "Spindles, sleep."),
    ("news:c", "es", "SINC", "Los husos del sueño y la memoria", "Ratones que duermen."),
    ("news:d", "en", "ScienceDaily", "A new drug for migraine", "Headache trial."),
    ("news:e", "en", "ScienceDaily", "Zebrafish fins regrow", "Regeneration study."),
    ("news:f", "en", "The Conversation", "Bees count to four", "Insect numeracy."),
    ("news:g", "en", "ScienceDaily", "Octopus arms decide alone", "Distributed control."),
]


def make_warehouse(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute("create table fct_news_item (news_item_id varchar, lang varchar, "
                    "outlet varchar, title varchar, feed_summary varchar, "
                    "published_at timestamptz)")  # fmt: skip
        for i, row in enumerate(ROWS):
            con.execute("insert into fct_news_item values (?, ?, ?, ?, ?, ?)",
                        [*row, D - dt.timedelta(hours=i)])  # fmt: skip
    return path


def answers() -> dict[tuple[str, str], bool]:
    """What the LLM said about every pair among a to g, as in derived/news/pairs.json."""
    keys = [r[0] for r in ROWS]
    out = {(a, b): False for i, a in enumerate(keys) for b in keys[i + 1 :]}
    out[("news:d", "news:g")] = True  # a "yes" that TF-IDF would never rank high
    return out


@pytest.fixture
def items(tmp_path):
    return evaluate.news_texts([r[0] for r in ROWS], make_warehouse(tmp_path / "w.duckdb"))


def test_texts_are_read_from_the_warehouse(items):
    assert items["news:c"]["lang"] == "es" and items["news:c"]["outlet"] == "SINC"
    assert evaluate.pair_text(items["news:d"]) == "A new drug for migraine Headache trial."


def test_the_sheet_has_every_yes_the_most_alike_and_every_cross_language_pair(items):
    pairs = pair_sheet.select(answers(), items, top=1, sample=0)
    assert ("news:d", "news:g") in pairs  # the LLM's yes
    assert ("news:a", "news:b") in pairs  # the most alike
    cross = {p for p in answers() if "news:c" in p}
    assert cross <= set(pairs)  # all six pairs with the one Spanish item
    assert len(pairs) == 1 + 1 + 6


def test_a_random_control_and_the_same_sheet_every_time(items):
    first = pair_sheet.select(answers(), items, top=1, sample=3)
    assert len(first) == 8 + 3
    assert first == pair_sheet.select(answers(), items, top=1, sample=3)  # seeded
    assert first != sorted(first)  # shuffled: the order says nothing about why


def test_pairs_whose_items_are_not_in_the_warehouse_are_left_out(items):
    judged = answers() | {("news:a", "news:zz"): True}
    assert ("news:a", "news:zz") not in pair_sheet.select(judged, items, top=1, sample=50)


def test_the_sheet_is_blind_and_stays_out_of_the_repository(items, tmp_path):
    pairs = pair_sheet.select(answers(), items, top=1, sample=0)
    out = tmp_path / "sheet.csv"
    pair_sheet.write_sheet(out, pairs, items)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert tuple(rows[0]) == pair_sheet.SHEET_COLUMNS
    assert {r["same"] for r in rows} == {""}  # no answer, no hint
    assert not any("llm" in c or "reason" in c for c in pair_sheet.SHEET_COLUMNS)
    with pytest.raises(ValueError, match="outside the repository"):
        pair_sheet.write_sheet(pair_sheet.REPO / "eval" / "news" / "sheet.csv", pairs, items)
    assert pair_sheet.outside_repo(pair_sheet.REPO / "data" / "sheet.csv")


def test_the_gold_keeps_only_keys_and_answers(items, tmp_path):
    sheet = tmp_path / "sheet.csv"
    pair_sheet.write_sheet(sheet, pair_sheet.select(answers(), items, top=1, sample=0), items)
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    with pytest.raises(ValueError, match="8 pairs without yes/no"):
        pair_sheet.to_gold(sheet, tmp_path / "gold.csv")
    for r in rows:
        r["same"] = "Yes " if r["key_a"] == "news:a" and r["key_b"] == "news:b" else "no"
    with sheet.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pair_sheet.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    assert pair_sheet.to_gold(sheet, tmp_path / "gold.csv") == 8
    gold = evaluate.load_pairs(tmp_path / "gold.csv")  # the strict loader accepts it
    assert [p for p in gold if p["same"]] == [{"key_a": "news:a", "key_b": "news:b", "same": True}]
    text = (tmp_path / "gold.csv").read_text("utf-8")
    assert "Sleep" not in text and "ScienceDaily" not in text


def test_commands_end_to_end(tmp_path, monkeypatch):
    """pairs-sheet → (Aday labels) → pairs-gold → eval news --pairs, from the warehouse."""
    from synaptica.cli import app

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path / "syn"))
    from synaptica.news import classify, group

    make_warehouse(classify.warehouse_path())
    judged = group.pairs_path()
    judged.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"key_a": a, "key_b": b, "same": s} for (a, b), s in answers().items()]
    judged.write_text(json.dumps(rows), encoding="utf-8")
    run = CliRunner().invoke
    sheet = tmp_path / "sheet.csv"
    result = run(app, ["eval", "pairs-sheet", "--out", str(sheet), "--top", "1", "--sample", "0"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("8 pairs of 21 judged")
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    for r in rows:  # Aday's labels: a-b and d-g are the same story
        same = (r["key_a"], r["key_b"]) in {("news:a", "news:b"), ("news:d", "news:g")}
        r["same"] = "yes" if same else "no"
    with sheet.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pair_sheet.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    gold = tmp_path / "pairs.csv"
    assert (
        run(app, ["eval", "pairs-gold", "--sheet", str(sheet), "--out", str(gold)]).exit_code == 0
    )
    result = run(app, ["eval", "news", "--gold", str(tmp_path / "none.csv"), "--pairs", str(gold)])
    assert result.exit_code == 0, result.output
    assert "| llm | 8 (2) | 1 / 0 | 1 | 1.00 | 0.50 | 0.67 | — |" in result.output
    in_repo = pair_sheet.REPO / "eval" / "sheet.csv"
    assert run(app, ["eval", "pairs-sheet", "--out", str(in_repo)]).exit_code == 1
    assert not in_repo.exists()
