"""Weekly Clásicos (plan, step 24a): the OpenAlex listing, the proposal in Sofía's queue
and the block on Neuro News, which shows nothing until she has chosen. No network: an
``httpx.MockTransport`` answers for OpenAlex; titles and counts are made up."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from synaptica.http import Throttle
from synaptica.ingest import classics as listing
from synaptica.news import classics
from synaptica.review.models import Action, Decision, ItemType, Queue
from test_site_news import AS_OF, build, warehouse

MONDAY = dt.date(2026, 11, 16)  # ISO week 2026-W47


def fake_openalex(calls: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        sid = params["filter"].split("subfield.id:")[1].split(",")[0]
        works = [
            {
                "doi": f"https://doi.org/10.1/{sid}-{i}",
                "display_name": f"Work {sid}-{i}",
                "publication_year": 2001,
                "cited_by_count": 1000 - i,
            }
            for i in range(4)
        ]
        works.append({"doi": None, "display_name": "No DOI", "publication_year": 2001})
        return httpx.Response(200, json={"results": works})  # fmt: skip

    return httpx.Client(transport=httpx.MockTransport(handler))


def ingest(raw: Path, day: dt.date = MONDAY, calls: list | None = None):
    calls = calls if calls is not None else []
    return listing.ingest(fake_openalex(calls), today=day, raw_root=raw,
                          throttle=Throttle(1000))  # fmt: skip


def test_one_listing_a_week_of_old_most_cited_articles(tmp_path: Path) -> None:
    calls: list[dict] = []
    result = ingest(tmp_path, calls=calls)
    assert (result.subfields, result.works, result.skipped) == (8, 32, False)  # no-DOI out
    assert calls[0]["sort"] == "cited_by_count:desc"
    assert "publication_year:<2022" in calls[0]["filter"]  # at least 5 years old
    assert "is_retracted:false" in calls[0]["filter"] and "search" not in calls[0]
    again = ingest(tmp_path, MONDAY + dt.timedelta(days=3), calls)  # same ISO week
    assert again.skipped and len(calls) == 8


def decide_pick(review: Path, item, dois: list[str]) -> None:
    review.mkdir(parents=True, exist_ok=True)
    d = Decision(item_type=item.item_type, item_id=item.item_id,
                 content_sha256=item.content_sha256, action=Action.PICK,
                 payload={"dois": dois}, reviewed_by="sofia",
                 reviewed_at=dt.datetime(2026, 11, 16, 20, tzinfo=dt.UTC),
                 source="issue#9")  # fmt: skip
    with (review / "decisions.jsonl").open("a") as f:
        f.write(d.model_dump_json() + "\n")


def test_the_proposal_skips_her_picks_and_rests_what_was_proposed(tmp_path: Path) -> None:
    raw, review = tmp_path / "raw", tmp_path / "review"
    ingest(raw)
    item = classics.proposal(raw, review, MONDAY)
    assert item.item_type is ItemType.CLASSICS and item.item_id == "classics-2026-w47"
    dois = [c.doi for c in item.content.candidates]
    assert len(dois) == 16 and dois[:2] == ["10.1/2805-0", "10.1/2805-1"]  # 2 per subfield
    assert item.content.max_picks == 5

    decide_pick(review, item, ["10.1/2805-0"])
    queue = Queue(generated_at=dt.datetime(2026, 11, 16, tzinfo=dt.UTC), items=[item])
    (review / "queue-2026-11-16.json").write_text(queue.model_dump_json())
    next_week = MONDAY + dt.timedelta(days=7)
    ingest(raw, next_week)
    later = [c.doi for c in classics.proposal(raw, review, next_week).content.candidates]
    assert later[:2] == ["10.1/2805-2", "10.1/2805-3"]  # her pick and last week's rest
    assert classics.proposal(raw, review, MONDAY + dt.timedelta(days=14)) is None  # no listing


def test_nothing_on_the_site_until_she_has_chosen(tmp_path: Path) -> None:
    data = warehouse(tmp_path / "data")
    raw, review = data / "raw", data / "review"
    ingest(raw, AS_OF)
    assert classics.approved(raw, review, AS_OF) == []
    page = (build(tmp_path, data) / "es" / "noticias.html").read_text()
    assert "tab-classics" not in page and "p-classics" not in page

    item = classics.proposal(raw, review, AS_OF)
    decide_pick(review, item, ["10.1/2804-1", "10.1/2805-0"])
    shown = classics.approved(raw, review, AS_OF)
    assert [w["doi"] for w in shown] == ["10.1/2805-0", "10.1/2804-1"]  # most cited first
    assert shown[0]["subfield"]["es"] == "Neurociencia cognitiva"
    site = build(tmp_path / "again", data)
    es = (site / "es" / "noticias.html").read_text()
    en = (site / "en" / "news.html").read_text()
    assert "tab-classics" in es and "https://doi.org/10.1/2805-0" in es
    assert "1\N{NO-BREAK SPACE}000 citas" in es and "1,000 citations" in en
    assert "Work 2805-1" not in es  # proposed, not chosen


def test_the_queue_carries_the_weeks_classics(tmp_path: Path) -> None:
    from synaptica.review.collect import collect

    data = warehouse(tmp_path / "data")
    ingest(data / "raw", MONDAY)
    q = collect(data / "warehouse.duckdb", data / "derived", data / "review", MONDAY)
    assert [i.item_id for i in q.items] == ["classics-2026-w47"]
    assert json.loads(q.model_dump_json())["items"][0]["content"]["kind"] == "candidates"
