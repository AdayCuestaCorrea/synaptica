"""News feeds (SINC, The Conversation, ScienceDaily) with the S1 fixtures, no network."""

import datetime as dt

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import feeds, news

FIXTURES = project_root() / "tests" / "fixtures" / "news"
DAY = dt.date(2026, 11, 9)
NO_WAIT = Throttle(1000, sleep=lambda _: None)
FEEDS = news.load_feeds()
BY_URL = {f.url: f.feed for f in FEEDS}


class FakeOutlets:
    def __init__(self, broken=()):
        self.broken = set(broken)

    def __call__(self, request):
        key = BY_URL[str(request.url)]
        if key in self.broken:
            return httpx.Response(404, text="gone")
        return httpx.Response(200, text=(FIXTURES / f"{key}.xml").read_text("utf-8"))


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return news.ingest(client, today=today, raw_root=tmp_path, throttle=NO_WAIT)


def test_seed_has_a_licence_for_every_feed_and_both_languages():
    assert {f.lang for f in FEEDS} == {"es", "en"}
    assert all(f.license for f in FEEDS)
    assert "sinc_salud" not in BY_URL.values()  # Aday chose Noticias (2026-11-11)


def test_every_article_is_stored_once_with_outlet_language_and_date(tmp_path):
    result = run(tmp_path, FakeOutlets())
    assert result.failed == [] and result.feeds == 5
    day = news.store(tmp_path).read_day(DAY)
    assert len(day) == result.items == result.new_versions
    article = next(a for a in day.values() if a["outlet"] == "SINC")
    assert article["lang"] == "es" and article["published"].endswith("Z")
    assert article["url"].startswith("https://www.agenciasinc.es/Noticias/")


def test_an_article_in_two_feeds_of_the_same_outlet_is_one_item(tmp_path):
    es = [feeds.parse_feed((FIXTURES / f"conversation_es_{t}.xml").read_text("utf-8"))
          for t in ("neurociencia", "cerebro")]  # fmt: skip
    shared = {i["url"] for i in es[0]} & {i["url"] for i in es[1]}
    assert shared  # the fixtures do overlap
    result = run(tmp_path, FakeOutlets())
    total = sum(
        len(feeds.parse_feed((FIXTURES / f"{f.feed}.xml").read_text("utf-8"))) for f in FEEDS
    )
    assert result.items == total - len(shared)


def test_a_failing_feed_is_skipped(tmp_path, monkeypatch):
    result = run(tmp_path, FakeOutlets(broken={"sinc_noticias"}))
    assert result.failed == ["sinc_noticias"]
    assert all(a["outlet"] != "SINC" for a in news.store(tmp_path).read_day(DAY).values())


def test_reruns_write_nothing(tmp_path):
    run(tmp_path, FakeOutlets())
    assert run(tmp_path, FakeOutlets()).new_versions == 0
    assert run(tmp_path, FakeOutlets(), today=DAY + dt.timedelta(days=30)).new_versions == 0


def test_has_new_items(tmp_path):
    with make_client(transport=httpx.MockTransport(FakeOutlets())) as client:
        assert news.has_new_items(client, today=DAY, raw_root=tmp_path)
    run(tmp_path, FakeOutlets())
    with make_client(transport=httpx.MockTransport(FakeOutlets())) as client:
        assert not news.has_new_items(client, today=DAY, raw_root=tmp_path)
