"""OpenAlex lookups by DOI with the S1 fixture behind ``httpx.MockTransport`` (no network)."""

import datetime as dt
import json

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import journals, openalex

FIXTURE = project_root() / "tests" / "fixtures" / "openalex" / "works_most_cited_2016.json"
DAY = dt.date(2026, 11, 9)
NO_WAIT = Throttle(1000, sleep=lambda _: None)
WORKS = json.loads(FIXTURE.read_text(encoding="utf-8"))["results"]
DOIS = [w["doi"].removeprefix("https://doi.org/").lower() for w in WORKS]


class FakeOpenAlex:
    """Answers the works of the fixture whose DOI is in ``filter=doi:a|b``; ``unknown``
    DOIs are left out, as OpenAlex does with works it does not have yet."""

    def __init__(self, unknown=()):
        self.calls = []
        self.unknown = set(unknown)

    def __call__(self, request):
        params = dict(request.url.params)
        self.calls.append(params)
        asked = set(params["filter"].removeprefix("doi:").split("|"))
        found = [w for w, d in zip(WORKS, DOIS, strict=True)
                 if d in asked and d not in self.unknown]  # fmt: skip
        return httpx.Response(200, json={"results": found})


def seed_journal_items(tmp_path, day=DAY):
    """Fixture DOIs as Nature items (general), plus one Neuron item (neuro: not asked)."""
    items = {d: {"doi": d, "journal": "nature", "url": f"https://x/{i}"}
             for i, d in enumerate(DOIS[:6])}  # fmt: skip
    items[DOIS[6]] = {"doi": DOIS[6], "journal": "neuron", "url": "https://x/n"}
    journals.store(tmp_path).save(items, day)


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return openalex.ingest(client, today=today, raw_root=tmp_path, throttle=NO_WAIT)


def test_general_journal_dois_are_looked_up_with_filter_never_search(tmp_path):
    seed_journal_items(tmp_path)
    fake = FakeOpenAlex()
    result = run(tmp_path, fake)
    assert (result.asked, result.found, result.new_versions) == (6, 6, 6)
    assert len(fake.calls) == 1 and "search" not in fake.calls[0]
    assert fake.calls[0]["filter"].startswith("doi:") and "@" in fake.calls[0]["mailto"]
    work = openalex.store(tmp_path).read_day(DAY)[DOIS[0]]
    assert work["cited_by_count"] == 8951 and work["openalex_id"] == "W2320983896"
    assert work["primary_topic"]["field"] == "28"
    assert work["primary_topic"]["field_name"] == "Neuroscience"
    assert DOIS[6] not in openalex.store(tmp_path).read_day(DAY)  # Neuron is neuro already


def test_batches_of_fifty(tmp_path, monkeypatch):
    monkeypatch.setattr(openalex, "BATCH", 4)
    seed_journal_items(tmp_path)
    fake = FakeOpenAlex()
    run(tmp_path, fake)
    assert [len(c["filter"].split("|")) for c in fake.calls] == [4, 2]


def test_unknown_dois_are_asked_again_later_and_known_ones_never(tmp_path):
    seed_journal_items(tmp_path)
    first = run(tmp_path, FakeOpenAlex(unknown={DOIS[0]}))
    assert (first.asked, first.found) == (6, 5)
    fake = FakeOpenAlex()
    again = run(tmp_path, fake, today=DAY + dt.timedelta(days=1))
    assert (again.asked, again.found, again.new_versions) == (1, 1, 1)
    assert fake.calls[0]["filter"] == f"doi:{DOIS[0]}"
    assert run(tmp_path, FakeOpenAlex(), today=DAY + dt.timedelta(days=2)).asked == 0


def test_items_older_than_the_window_are_not_asked(tmp_path):
    seed_journal_items(tmp_path, day=DAY - dt.timedelta(days=openalex.LOOKBACK_DAYS))
    assert run(tmp_path, FakeOpenAlex()).asked == 0
