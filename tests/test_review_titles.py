"""Spanish titles in Sofía's queue (step 23c): a few a day at random, and what her decision
changes on the site. No network: the warehouse of ``test_site_news``; titles made up."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from synaptica.review import collect
from synaptica.review.models import Action, ItemType
from test_review_collect import MONDAY, build, decide, queue_of
from test_site_news import AS_OF, study, warehouse


def titled(tmp_path: Path, n: int = 8) -> Path:
    rows = [study(f"doi:10.1/t{k}", title=f"Sleep and memory in {k + 2} groups of mice",
                  title_es=f"Sueño y memoria en {k + 2} grupos de ratones",
                  entered_on=AS_OF - dt.timedelta(days=k % 5)) for k in range(n)]  # fmt: skip
    return warehouse(tmp_path / "data", [*rows, study("doi:10.1/plain")])


def titles_in(queue):
    return [i for i in queue.items if i.item_type is ItemType.TITLE]


def test_a_few_translated_titles_a_day_drawn_with_the_day_as_seed(tmp_path: Path) -> None:
    data = titled(tmp_path)
    monday = titles_in(queue_of(data))
    assert len(monday) == collect.TITLES_PER_DAY
    assert [i.item_id for i in monday] == [i.item_id for i in titles_in(queue_of(data))]
    other = titles_in(queue_of(data, MONDAY + dt.timedelta(days=1)))
    assert {i.item_id for i in other} != {i.item_id for i in monday}  # another draw
    item = monday[0]
    assert item.title_es.startswith("Sueño y memoria")
    assert item.content.en[0].text.startswith("Sleep and memory")  # the original beside it
    assert "doi_10.1_plain" not in {i.item_id for i in monday}  # untranslated: not queued


def test_decided_titles_are_not_drawn_again(tmp_path: Path) -> None:
    data = titled(tmp_path, n=6)
    first = titles_in(queue_of(data))
    for n, item in enumerate(first, 1):
        decide(data, item, Action.APPROVE, n=n)
    (left,) = titles_in(queue_of(data))  # 6 translated, 5 decided
    assert left.item_id not in {i.item_id for i in first}


def test_a_rejected_title_shows_the_original_and_an_edit_shows_hers(tmp_path: Path) -> None:
    data = titled(tmp_path, n=2)
    by_id = {i.item_id: i for i in titles_in(queue_of(data))}
    decide(data, by_id["doi_10.1_t0"], Action.REJECT, n=1)
    decide(data, by_id["doi_10.1_t1"], Action.EDIT,
           {"es": "El sueño y la memoria en 3 grupos de ratones"}, n=2)  # fmt: skip
    out = build(tmp_path, data)
    t0 = (out / "es/estudio/doi_10.1_t0.html").read_text()
    assert 'lang="en">Sleep and memory in 2 groups of mice</h1>' in t0 and "gap-title_es" in t0
    t1 = (out / "es/estudio/doi_10.1_t1.html").read_text()
    assert 'lang="es">El sueño y la memoria en 3 grupos de ratones</h1>' in t1  # no English wait
    assert "Sueño y memoria" not in (out / "en/study/doi_10.1_t1.html").read_text()


def test_a_decision_on_an_older_translation_changes_nothing(tmp_path: Path) -> None:
    data = titled(tmp_path, n=1)
    (item,) = titles_in(queue_of(data))
    decide(data, item, Action.REJECT)
    retranslated = study("doi:10.1/t0", title="Sleep and memory in 2 groups of mice",
                         title_es="El sueño y la memoria en 2 grupos de ratones")  # fmt: skip
    data = warehouse(tmp_path / "data2", [retranslated])
    (data / "review").mkdir()
    (data / "review" / "decisions.jsonl").write_text(
        (tmp_path / "data" / "review" / "decisions.jsonl").read_text()
    )
    html = (build(tmp_path, data) / "es/estudio/doi_10.1_t0.html").read_text()
    assert 'lang="es">El sueño y la memoria en 2 grupos de ratones</h1>' in html


def test_summary_items_carry_the_spanish_title_when_there_is_one(tmp_path: Path) -> None:
    from test_review_collect import summarize

    data = warehouse(tmp_path / "data", [study("doi:10.1/a", pmid="1", title_es="Título")])
    summarize(data, "doi:10.1/a")
    (news,) = [i for i in queue_of(data).items if i.item_type is ItemType.NEWS]
    assert news.title_es == "Título"
