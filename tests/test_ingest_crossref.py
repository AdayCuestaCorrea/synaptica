"""Crossref notices with the S1 fixtures behind ``httpx.MockTransport`` (no network)."""

import datetime as dt
import json
from urllib.parse import parse_qs

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import crossref

FIXTURES = project_root() / "tests" / "fixtures" / "crossref"
DAY = dt.date(2026, 11, 9)


def fixture_items(kind):
    path = FIXTURES / f"notices_{kind}.json"
    return json.loads(path.read_text(encoding="utf-8"))["message"]["items"] if path.exists() else []


class FakeCrossref:
    """First page: the S1 fixture of that kind (when there is one); then a short page."""

    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows

    def __call__(self, request):
        params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        self.calls.append(params)
        kind = params["filter"].split(",")[0].removeprefix("update-type:")
        items = fixture_items(kind) if params["cursor"] == "*" else []
        return httpx.Response(200, json={"message": {"items": items, "next-cursor": "next"}})


def run(tmp_path, fake, today=DAY, **kwargs):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return crossref.ingest(
            client, today=today, raw_root=tmp_path,
            throttle=Throttle(1000, sleep=lambda _: None), **kwargs,
        )  # fmt: skip


def test_notices_are_listed_per_kind_since_the_window_and_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(crossref, "ROWS", 10)  # the fixtures hold 10 items: ask for page 2
    fake = FakeCrossref()
    result = run(tmp_path, fake)
    assert result.notices["retraction"] == 10 and result.notices["correction"] == 10
    assert result.notices["erratum"] == 0
    assert result.new_versions == 20
    first = fake.calls[0]
    assert first["filter"] == "update-type:retraction,from-update-date:2026-11-06"
    assert first["select"] == "DOI,type,update-to" and "@" in first["mailto"]
    assert [c["cursor"] for c in fake.calls[:2]] == ["*", "next"]  # full page: next one

    notice = crossref.store(tmp_path).read_day(DAY)["10.1186/s41065-026-00753-z"]
    assert notice == {
        "doi": "10.1186/s41065-026-00753-z",
        "updates": [{"doi": "10.1186/s41065-025-00496-3", "type": "retraction",
                     "source": "publisher", "date": "2026-10-10"}],
    }  # fmt: skip


def test_a_short_page_ends_the_listing(tmp_path):
    fake = FakeCrossref()
    run(tmp_path, fake)
    assert len(fake.calls) == len(crossref.KINDS)  # every first page is short (< 1000)


def test_reruns_and_redeposits_within_the_window_write_nothing(tmp_path):
    run(tmp_path, FakeCrossref())
    before = crossref.store(tmp_path).path(DAY).read_bytes()
    assert run(tmp_path, FakeCrossref()).new_versions == 0
    assert crossref.store(tmp_path).path(DAY).read_bytes() == before
    next_day = DAY + dt.timedelta(days=1)
    assert run(tmp_path, FakeCrossref(), today=next_day).new_versions == 0
    assert not crossref.store(tmp_path).path(next_day).exists()


def test_publisher_text_never_reaches_the_store(tmp_path):
    run(tmp_path, FakeCrossref())
    text = crossref.store(tmp_path).path(DAY).read_text(encoding="utf-8")
    assert "title" not in text and "abstract" not in text and "author" not in text
