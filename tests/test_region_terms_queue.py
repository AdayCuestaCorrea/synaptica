"""The Neuro Atlas pair -> MeSH table in Sofía's queue (v190, Aday's option 1): one
``search_terms`` item per pair, a few a day from 2026-11-18. No network: the warehouse of
``test_site_news``."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from synaptica.atlas import studies
from synaptica.review import collect
from synaptica.review.models import Action, ItemType, Queue
from test_review_collect import MONDAY, SATURDAY, data_dir, decide
from test_site_news import study, warehouse

FOUND = {"internal": [{"title": f"Hippocampus study {n}"} for n in range(5)]}
ITEMS = studies.review_items(FOUND)


def queue(data: Path, today: dt.date = MONDAY) -> Queue:
    return collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", today,
                           glossary=[], region_terms=ITEMS)  # fmt: skip


def pairs(q: Queue) -> list[str]:
    return [i.item_id for i in q.items if i.item_type is ItemType.SEARCH_TERMS]


def test_one_item_per_pair_with_its_mesh_terms_and_three_examples():
    assert len(ITEMS) == 14 and len({i.item_id for i in ITEMS}) == 14
    hippo = next(i for i in ITEMS if i.item_id == "waxholm-1021")
    assert hippo.content.terms[0] == "Hippocampus" and "Cornu Ammonis" in hippo.content.terms
    assert hippo.content.examples == ["Hippocampus study 0", "Hippocampus study 1",
                                      "Hippocampus study 2"]  # fmt: skip
    assert hippo.title_es.startswith("Hippocampal formation (rata) ↔ CA1 (Hippocampus)")


def test_the_examples_never_change_what_she_approves():
    """New studies every day must not bring back an item she already answered."""
    today, tomorrow = studies.review_items(FOUND), studies.review_items({})
    assert [i.content_sha256 for i in today] == [i.content_sha256 for i in tomorrow]


def test_none_before_the_18th_then_from_the_warehouse(tmp_path: Path) -> None:
    rows = [study("doi:10.1/h", title="Dopamine cells of the substantia nigra in rats")]
    data = warehouse(tmp_path / "data", rows)

    def default(day: dt.date) -> Queue:
        return collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", day,
                               glossary=[])  # fmt: skip

    assert pairs(default(dt.date(2026, 11, 17))) == []
    q = default(dt.date(2026, 11, 18))
    assert len(pairs(q)) == collect.REGION_TERMS_WEEKDAY
    sn = next(i for i in q.items if i.item_id == "waxholm-1098")  # 4th in her order (v240)
    assert sn.content.examples == ["Dopamine cells of the substantia nigra in rats"]


def test_four_a_weekday_two_at_the_weekend_and_decided_ones_leave(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    first = pairs(queue(data))
    # Sofía's order (v237): basal ganglia, zona incerta, substantia nigra, hippocampus, …
    assert first == ["waxholm-197", "waxholm-1028", "waxholm-1082", "waxholm-1098"]
    assert len(pairs(queue(data, SATURDAY))) == collect.REGION_TERMS_WEEKEND
    item = next(i for i in ITEMS if i.item_id == first[0])
    decide(data, item, Action.APPROVE)
    assert pairs(queue(data)) == [*first[1:], "waxholm-1021"]
