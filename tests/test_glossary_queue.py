"""Neuro Glossary terms in Sofía's daily queue, and her edits of them checked against the
committed Wikipedia leads. No network: the warehouse of ``test_site_news``."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from synaptica.glossary.texts import review_items
from synaptica.review import collect, intake
from synaptica.review.issue_block import encode
from synaptica.review.models import Action, ItemType, Queue
from test_review_collect import MONDAY, SATURDAY, data_dir, decide

GLOSSARY = review_items()


def queue(data: Path, today: dt.date = MONDAY) -> Queue:
    return collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", today)


def kinds(q: Queue) -> list[str]:
    return [i.item_type.value for i in q.items if i.item_type is not ItemType.NEWS_TOPIC]


def test_all_24_terms_become_items():
    assert len(GLOSSARY) == 24 and all(i.item_type is ItemType.GLOSSARY for i in GLOSSARY)


def test_eight_new_terms_a_weekday_before_the_spot_check(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    q = queue(data)
    assert kinds(q) == ["glossary"] * collect.GLOSSARY_WEEKDAY + ["news"]
    assert [i.item_id for i in q.items[:3]] == ["5-ht", "aav", "ad"]  # terms.csv order


def test_three_at_the_weekend_within_its_cap(tmp_path: Path) -> None:
    data = data_dir(tmp_path, **{f"s{n:02d}": 5 for n in range(12)})
    q = queue(data, SATURDAY)
    assert kinds(q).count("glossary") == collect.GLOSSARY_WEEKEND
    assert len(q.items) == collect.CAP_WEEKEND


def test_decided_terms_leave_and_the_next_ones_come_in(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    first = queue(data).items
    for n, item in enumerate(first[:2], 1):
        decide(data, item, Action.APPROVE, n=n)
    ids = [i.item_id for i in queue(data).items if i.item_type is ItemType.GLOSSARY]
    assert ids[:2] == [i.item_id for i in first[2:4]] and len(ids) == collect.GLOSSARY_WEEKDAY
    assert {first[0].item_id, first[1].item_id}.isdisjoint(ids)


def test_her_edit_is_checked_against_the_wikipedia_lead(tmp_path: Path) -> None:
    q = Queue(generated_at=dt.datetime(2026, 11, 16, tzinfo=dt.UTC), items=GLOSSARY)
    texts = intake.source_texts(q, tmp_path / "cache", [])
    da = q.get(ItemType.GLOSSARY, "da")
    assert texts["wikipedia-es-da"].startswith("La dopamina")
    lead = texts["wikipedia-en-da"].split()
    copied = "DA (Dopamine): " + " ".join(lead[10:22])
    warnings = intake.edit_warnings(da, {"en": copied}, texts)
    assert any("Copia 8 palabras" in w for w in warnings), warnings


def test_an_edit_waits_when_the_cited_revision_is_not_the_committed_one() -> None:
    """A queue item citing a revision other than ``sources.json`` (refreshed since): her
    edit waits for Aday instead of being checked without its source."""
    da = next(i for i in GLOSSARY if i.item_id == "da")
    src = da.content.sources[0].model_copy(update={"url": "https://x/w/index.php?oldid=1"})
    old = da.model_copy(update={"content": da.content.model_copy(
        update={"sources": [src, *da.content.sources[1:]]})})  # fmt: skip
    q = Queue(generated_at=dt.datetime(2026, 11, 16, tzinfo=dt.UTC), items=[old])
    texts = intake.glossary_source_texts(q)
    assert src.id not in texts and da.content.sources[1].id in texts
    edit = {"item_type": "glossary", "item_id": "da", "content_sha256": old.content_sha256,
            "action": "edit", "payload": {"en": "DA (Dopamine): a neurotransmitter."}}  # fmt: skip
    body = f"```text\n{encode('2026-11-16T00:00:00Z', 'public', [edit])}\n```"
    assert intake.missing_sources({"issue": {"body": body}}, q, texts) == [src.id]
