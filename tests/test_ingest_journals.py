"""Journal feeds (RSS 1.0 of Nature, Science, Cell) and the Crossref fallback, no network."""

import datetime as dt

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import feeds, journals

FIXTURES = project_root() / "tests" / "fixtures" / "journals"
DAY = dt.date(2026, 11, 9)
NO_WAIT = Throttle(1000, sleep=lambda _: None)
JOURNALS = journals.load_journals()
BY_FEED = {j.rss: j.journal for j in JOURNALS}
BY_ISSN = {j.issn: j.journal for j in JOURNALS}


class FakePublishers:
    """Each feed answers its S1 fixture; ``broken`` feeds answer 503 and fall back to
    Crossref by ISSN (also from S1)."""

    def __init__(self, broken=()):
        self.broken = set(broken)
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if request.url.host == "api.crossref.org":
            issn = request.url.path.split("/")[2]
            body = (FIXTURES / f"{BY_ISSN[issn]}.crossref.json").read_text(encoding="utf-8")
            return httpx.Response(200, text=body, headers={"content-type": "application/json"})
        key = BY_FEED[str(request.url)]
        if key in self.broken:
            return httpx.Response(503, text="down")
        return httpx.Response(200, text=(FIXTURES / f"{key}.rss.xml").read_text("utf-8"))


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return journals.ingest(client, today=today, raw_root=tmp_path, throttle=NO_WAIT)


def test_seed_lists_the_seven_journals_with_their_scope():
    assert [j.journal for j in JOURNALS if j.scope == "neuro"] == [
        "nature_neuroscience", "nature_reviews_neuroscience", "neuron",
    ]  # fmt: skip
    assert {j.journal: j.issn for j in JOURNALS}["cell"] == "0092-8674"  # print ISSN


def test_rdf_feeds_give_doi_date_authors_and_section():
    cell = feeds.parse_feed((FIXTURES / "cell.rss.xml").read_text("utf-8"))
    assert cell[0] == {
        "url": "https://www.cell.com/cell/fulltext/S0092-8674(26)01120-7",  # ?rss=yes gone
        "title": "Roads not taken: The mismatch between safety and regulation of plant "
        "breeding innovation",
        "published": "2026-10-29T00:00:00Z",
        "doi": "10.1016/j.cell.2026.09.018",
        "authors": ["Jonathan D.G. Jones, Caixia Gao"],
        "section": "Commentary",
    }
    science = feeds.parse_feed((FIXTURES / "science.rss.xml").read_text("utf-8"))
    assert science[0]["doi"] == "10.1126/science.ael6284"
    assert science[0]["published"] == "2026-11-05T07:00:13Z"


def test_every_item_of_every_feed_is_stored_by_doi_without_publisher_text(tmp_path):
    result = run(tmp_path, FakePublishers())
    assert result.items == {
        "nature": 75, "nature_neuroscience": 8, "nature_reviews_neuroscience": 8,
        "science": 45, "science_advances": 81, "cell": 25, "neuron": 14,
    }  # fmt: skip
    assert result.via_crossref == [] and result.failed == []
    day = journals.store(tmp_path).read_day(DAY)
    assert len(day) == result.new_versions == 256
    assert day["10.1016/j.neuron.2026.09.010"]["journal"] == "neuron"
    text = journals.store(tmp_path).path(DAY).read_text(encoding="utf-8")
    assert "REDACTED" not in text and '"summary"' not in text


def test_a_broken_feed_falls_back_to_crossref_by_issn(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)  # the 503 retries
    fake = FakePublishers(broken={"neuron"})
    result = run(tmp_path, fake)
    assert result.via_crossref == ["neuron"] and result.items["neuron"] == 5
    crossref_call = next(c for c in fake.calls if c.url.host == "api.crossref.org")
    assert crossref_call.url.params["filter"] == "from-pub-date:2026-10-26"
    item = journals.store(tmp_path).read_day(DAY)["10.1016/j.neuron.2026.10.011"]
    assert item["via"] == "crossref" and item["authors"][0] == "Dimitra Sokolova"
    assert item["title"].startswith("An astrocyte-microglia MFG-E8 axis")


def test_reruns_and_items_still_in_the_feed_write_nothing(tmp_path):
    run(tmp_path, FakePublishers())
    assert run(tmp_path, FakePublishers()).new_versions == 0
    next_week = DAY + dt.timedelta(days=7)
    assert run(tmp_path, FakePublishers(), today=next_week).new_versions == 0


def test_has_new_items(tmp_path):
    with make_client(transport=httpx.MockTransport(FakePublishers())) as client:
        assert journals.has_new_items(client, today=DAY, raw_root=tmp_path)
    run(tmp_path, FakePublishers())
    with make_client(transport=httpx.MockTransport(FakePublishers())) as client:
        assert not journals.has_new_items(client, today=DAY, raw_root=tmp_path)
