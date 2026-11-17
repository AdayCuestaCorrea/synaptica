"""OpenAlex lookups by DOI with the S1 fixture behind ``httpx.MockTransport`` (no network)."""

import datetime as dt
import json

import httpx
import pytest

from synaptica.config import project_root
from synaptica.http import HttpError, Throttle, get_json, make_client, redact
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


@pytest.mark.parametrize("command", ["openalex", "classics"])
def test_a_used_up_budget_ends_the_command_green_and_says_so(tmp_path, monkeypatch, command):
    """D10: running out of a daily quota is not something to look at (not red); the DOIs
    stay due and are asked again on the next run."""
    from typer.testing import CliRunner

    from synaptica import cli, http
    from synaptica.ingest import openalex as oa

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(oa, "due_dois", lambda *a, **k: ["10.1/x"])
    busy = httpx.Response(429, headers={"Retry-After": "23444"}, text="Insufficient budget")
    real = http.make_client
    monkeypatch.setattr(http, "make_client",
                        lambda: real(transport=httpx.MockTransport(lambda r: busy)))  # fmt: skip
    result = CliRunner().invoke(cli.app, ["ingest", command])
    assert result.exit_code == 0, result.output
    assert "rate limited for today" in result.output


def test_the_free_key_is_sent_only_when_set(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    seed_journal_items(tmp_path)
    fake = FakeOpenAlex()
    run(tmp_path, fake)
    assert "api_key" not in fake.calls[0]
    monkeypatch.setenv("OPENALEX_API_KEY", " k-123 ")
    assert openalex.auth_params()["api_key"] == "k-123"
    monkeypatch.setenv("OPENALEX_API_KEY", "")
    assert "api_key" not in openalex.auth_params()


def test_the_key_never_appears_in_an_error():
    def refuse(request):
        return httpx.Response(403, text="forbidden", request=request)

    with (
        make_client(transport=httpx.MockTransport(refuse)) as client,
        pytest.raises(HttpError) as err,
    ):
        get_json(client, openalex.WORKS, params={"filter": "doi:x", "api_key": "k-123"})
    assert "k-123" not in str(err.value) and "api_key=%2A%2A%2A" in str(err.value)
    assert redact("https://a.org/w?x=1") == "https://a.org/w?x=1"
