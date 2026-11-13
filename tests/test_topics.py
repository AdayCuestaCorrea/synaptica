"""Topics of Neuro News (MeSH or text) and Sofía's switches. No network: the MeSH branches
are in the package; studies and abstracts are made up."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from synaptica.news import topics
from synaptica.review.models import Action, Decision, ItemType
from test_site_news import build, study, warehouse


def test_no_emotion_until_sofia_confirms_it() -> None:
    assert "emotion" not in topics.TOPICS and len(topics.TOPICS) == 5


def test_the_text_rule_needs_the_title_or_two_mentions_and_skips_immune_memory() -> None:
    assert topics.text_topics("Sleep deprivation in adolescents") == {"sleep"}
    assert topics.text_topics("A cohort study", "Sleep deprivation, once.") == set()
    assert topics.text_topics("A study", "Sleep deprivation; sleep deprivation.") == {"sleep"}
    # The bare root word tags too much (v118): «sleep» alone is not enough by text.
    assert topics.text_topics("Sleep and mood in a cohort") == set()
    assert topics.text_topics("Memory T cells in the spleen") == set()
    assert "neurodegeneration" in topics.text_topics("Alzheimer disease in mice")


def test_indexed_studies_take_the_topics_of_their_mesh() -> None:
    assert topics.mesh_topics(["D012890"], []) == {"sleep"}  # the root descriptor, Sleep
    assert topics.mesh_topics([], ["Alzheimer Disease"]) == {"neurodegeneration"}
    assert topics.mesh_topics(["D000000"], []) == set()


def _switch(review: Path, key: str, action: Action, n: int = 1) -> None:
    item = next(i for i in topics.queue_items() if i.item_id == f"topic-{key}")
    review.mkdir(parents=True, exist_ok=True)
    d = Decision(item_type=ItemType.NEWS_TOPIC, item_id=item.item_id,
                 content_sha256=item.content_sha256, action=action, payload={},
                 reviewed_by="sofia", reviewed_at=dt.datetime(2026, 11, 14, 9, n, tzinfo=dt.UTC),
                 source=f"issue#{n}")  # fmt: skip
    with (review / "decisions.jsonl").open("a") as f:
        f.write(d.model_dump_json() + "\n")


def test_a_topic_needs_three_items_and_her_switch_on(tmp_path: Path) -> None:
    rows = [
        study(f"doi:10.1/s{i}", title=f"Sleep deprivation and episodic memory, part {i}")
        for i in range(3)
    ]
    rows.append(study("doi:10.1/x", title="Neuroinflammation in one study"))
    data = warehouse(tmp_path / "data", rows)
    out = build(tmp_path, data)
    home = (out / "es/index.html").read_text()
    assert "Explora por temas" in home and 'href="temas/sleep.html"' in home
    assert 'href="temas/neuroinflammation.html"' not in home  # one item: not shown
    page = (out / "en/topics/sleep.html").read_text()
    assert (
        page.count("Topic from its text") == 3
        and "Sleep deprivation and episodic memory, part 0" in page
    )
    assert (out / "es/temas/memory.html").exists()  # the same three studies

    _switch(data / "review", "sleep", Action.DISABLE)
    out = build(tmp_path / "off", data)
    assert not (out / "es/temas/sleep.html").exists()
    assert 'href="temas/sleep.html"' not in (out / "es/index.html").read_text()
    _switch(data / "review", "sleep", Action.ENABLE, n=2)  # her last decision wins
    assert (build(tmp_path / "on", data) / "es/temas/sleep.html").exists()


def test_without_topics_the_home_page_has_no_block(tmp_path: Path) -> None:
    home = (build(tmp_path, warehouse(tmp_path / "data")) / "es/index.html").read_text()
    assert "Explora por temas" not in home
