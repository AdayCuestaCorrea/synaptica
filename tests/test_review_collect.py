"""Sofía's daily queue and what her decisions change on the site (plan, step R). No
network: the warehouse of ``test_site_news`` and texts written in ``tmp_path``; the
summaries and the abstract are made up for the tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from synaptica.narrative.facts import facts_path
from synaptica.narrative.write import text_path
from synaptica.review import collect, intake
from synaptica.review.apply import read_log
from synaptica.review.models import Action, Decision, ItemType
from synaptica.site.build import SiteBuilder
from test_site_news import AS_OF, LICENSED, study, warehouse

MONDAY, SATURDAY = dt.date(2026, 11, 9), dt.date(2026, 11, 14)
EDIT_ES = "Los ratones durmieron algo más.\nEl efecto duró 3 días."
EDIT_EN = "Mice slept a little more.\nThe effect lasted 3 days."
TEXTS = {"es": ["Los ratones durmieron más.", "El efecto duró 3 días."],
         "en": ["Mice slept more.", "The effect lasted 3 days."]}  # fmt: skip


def summarize(data: Path, sid: str, natural: int = 4, origin: str = "pubmed") -> None:
    """A summary that passed its checks and the judge, and the facts it was written from."""
    derived = data / "derived"
    for lang, lines in TEXTS.items():
        path = text_path(sid, lang, verified=True, derived_root=derived)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"study_id": sid, "status": "verified", "generator": "groq/qwen",
                  "sentences": [{"text": t, "fact_ids": ["f1"]} for t in lines],
                  "judge": {"passed": True, "generator": "groq/oss",
                            "spanish_natural": natural}}  # fmt: skip
        path.write_text(json.dumps(record), encoding="utf-8")
    path = facts_path(sid, derived)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"study_id": sid, "abstract_from": origin, "facts": []}))


def data_dir(tmp_path: Path, **natural: int) -> Path:
    rows = [study(f"doi:10.1/{k}", pmid=str(n), entered_on=AS_OF - dt.timedelta(days=n))
            for n, k in enumerate(natural, 1)]  # fmt: skip
    data = warehouse(tmp_path / "data", rows)
    for k, score in natural.items():
        summarize(data, f"doi:10.1/{k}", score)
    return data


def queue_of(data: Path, today: dt.date = MONDAY):
    return collect.collect(data / "warehouse.duckdb", data / "derived", data / "review", today)


def decide(data: Path, item, action: Action, payload: dict | None = None, n: int = 1) -> None:
    review = data / "review"
    review.mkdir(exist_ok=True)
    d = Decision(item_type=item.item_type, item_id=item.item_id,
                 content_sha256=item.content_sha256, action=action, payload=payload or {},
                 reviewed_by="sofia", reviewed_at=dt.datetime(2026, 11, 10, 9, n, tzinfo=dt.UTC),
                 source=f"issue#{n}")  # fmt: skip
    with (review / "decisions.jsonl").open("a") as f:
        f.write(d.model_dump_json() + "\n")


def test_news_item_cites_the_abstract_its_facts_came_from(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    (item,) = queue_of(data).items
    assert item.item_type is ItemType.NEWS and item.item_id == "doi_10.1_a"
    assert [s.text for s in item.content.es] == TEXTS["es"]
    (source,) = item.content.sources
    assert source.id == "pubmed-1" and source.url == "https://pubmed.ncbi.nlm.nih.gov/1/"
    assert all(s.cites == ["pubmed-1"] for s in item.content.es + item.content.en)


def test_preprint_sources_are_read_by_the_intake(tmp_path: Path) -> None:
    row = study("doi:10.1/p", sources=["biorxiv"])
    src = collect.study_source(row, "biorxiv")
    assert src.id == "biorxiv-10.1/p" and src.url == "https://doi.org/10.1/p"
    assert intake.study_source(src.id) == {"doi": "10.1/p", "sources": ["biorxiv"]}
    assert collect.study_source(row, "europepmc") is None  # no PMCID: no item, no check
    cache = tmp_path / "cache" / "biorxiv" / "abstract"
    cache.mkdir(parents=True)
    abstract = "Mice slept more for 3 days after the treatment. " * 10
    (cache / "10.1_p.json").write_text(json.dumps({"abstract": abstract}))
    data = warehouse(tmp_path / "data", [row])
    summarize(data, "doi:10.1/p", origin="biorxiv")
    q = queue_of(data)
    texts = intake.source_texts(q, tmp_path / "cache", [])
    assert texts == {"biorxiv-10.1/p": abstract}


def test_unjudged_or_one_language_summaries_are_not_queued(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4, b=4)
    text_path("doi:10.1/b", "en", verified=True, derived_root=data / "derived").unlink()
    assert [i.item_id for i in queue_of(data).items] == ["doi_10.1_a"]


def test_worst_spanish_first_then_newest_and_capped_at_the_weekend(tmp_path: Path) -> None:
    natural = {f"s{n:02d}": 5 for n in range(12)} | {"s11": 2}
    data = data_dir(tmp_path, **natural)
    ids = [i.item_id for i in queue_of(data).items]
    assert ids[:3] == ["doi_10.1_s11", "doi_10.1_s00", "doi_10.1_s01"]  # s00 entered last
    assert len(ids) == 12 and len(queue_of(data, SATURDAY).items) == collect.CAP_WEEKEND


def test_decided_items_leave_the_queue_and_held_edits_come_first(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=1, b=3, c=5)
    a, b, _ = queue_of(data).items
    decide(data, a, Action.APPROVE)
    review = data / "review"
    held = Decision(item_type=b.item_type, item_id=b.item_id, content_sha256=b.content_sha256,
                    action=Action.EDIT, payload={"es": "Los ratones durmieron 9 horas más."},
                    reviewed_by="sofia", reviewed_at=dt.datetime(2026, 11, 10, tzinfo=dt.UTC),
                    source="issue#2")  # fmt: skip
    with (review / "held.jsonl").open("a") as f:
        f.write(json.dumps({"decision": held.model_dump(mode="json"), "warnings": ["9"]}) + "\n")
    q = queue_of(data)
    assert [(i.item_id, bool(i.warnings)) for i in q.items] == [
        ("doi_10.1_b", True), ("doi_10.1_c", False)]  # fmt: skip


def test_queue_is_the_same_file_twice(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    assert queue_of(data).model_dump_json() == queue_of(data).model_dump_json()


def build(tmp_path: Path, data: Path) -> Path:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    return out


def test_a_rejected_summary_shows_the_fallback(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    (item,) = queue_of(data).items
    assert "Los ratones durmieron más." in (build(tmp_path, data) / "es/index.html").read_text()
    decide(data, item, Action.REJECT)
    out = build(tmp_path, data)
    for page in ("es/estudio/doi_10.1_a.html", "en/study/doi_10.1_a.html"):
        html = (out / page).read_text()
        assert "durmieron" not in html and "slept" not in html, page
        assert "summary--fallback" in html


def test_a_spanish_only_edit_waits_for_its_english(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    (item,) = queue_of(data).items
    decide(data, item, Action.EDIT, {"es": EDIT_ES})
    html = (build(tmp_path, data) / "es/estudio/doi_10.1_a.html").read_text()
    assert "algo más" not in html and "summary--fallback" in html  # never one language only


def test_an_edit_in_both_languages_is_shown_and_marked(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    (item,) = queue_of(data).items
    decide(data, item, Action.EDIT, {"es": EDIT_ES, "en": EDIT_EN})
    out = build(tmp_path, data)
    es = (out / "es/estudio/doi_10.1_a.html").read_text()
    assert "Los ratones durmieron algo más." in es and "corrigió después" in es
    assert "Mice slept a little more." in (out / "en/study/doi_10.1_a.html").read_text()
    assert len(read_log(data / "review")) == 1


def test_a_decision_on_an_older_text_changes_nothing(tmp_path: Path) -> None:
    data = data_dir(tmp_path, a=4)
    (item,) = queue_of(data).items
    decide(data, item, Action.REJECT)
    summarize(data, "doi:10.1/a", natural=5)  # same text: still rejected
    TEXTS["es"][0] = "Los ratones durmieron bastante más."
    try:
        summarize(data, "doi:10.1/a")  # a new version of the summary: her reject was of another
        html = (build(tmp_path, data) / "es/estudio/doi_10.1_a.html").read_text()
    finally:
        TEXTS["es"][0] = "Los ratones durmieron más."
    assert "bastante más" in html and "summary--verified" in html
