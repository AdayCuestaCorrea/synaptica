"""bioRxiv / medRxiv with the S1 fixtures behind ``httpx.MockTransport`` (no network)."""

import copy
import datetime as dt
import json

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import biorxiv

FIXTURES = project_root() / "tests" / "fixtures"
DAY = dt.date(2026, 11, 9)
NO_WAIT = Throttle(1000, sleep=lambda _: None)


def fixture(server, category):
    path = FIXTURES / server / f"details_{category}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FakeBiorxiv:
    """Path /details/<server>/<from>/<to>/<cursor>: the S1 fixture at cursor 0 (with its
    total trimmed to the 10 recorded items), empty afterwards. ``extra`` adds entries."""

    def __init__(self, extra=()):
        self.calls = []
        self.extra = list(extra)

    def __call__(self, request):
        _, _, server, since, until, cursor = request.url.path.split("/")
        category = request.url.params["category"]
        self.calls.append((server, category, since, until, cursor))
        body = fixture(server, category)
        if cursor != "0":
            body["collection"] = []
        else:
            body["collection"] += [e for e in self.extra if e["server"].lower() == server]
        body["messages"][0]["total"] = str(len(body["collection"]))
        return httpx.Response(200, json=body)


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return biorxiv.ingest(
            client, today=today, raw_root=tmp_path, cache_root=tmp_path / "cache",
            throttle=NO_WAIT,
        )  # fmt: skip


def test_each_category_is_listed_for_the_window_and_trimmed(tmp_path):
    fake = FakeBiorxiv()
    result = run(tmp_path, fake)
    assert result.found == {
        "biorxiv/neuroscience": 10, "medrxiv/neurology": 10,
        "medrxiv/psychiatry_and_clinical_psychology": 10,
    }  # fmt: skip
    assert fake.calls[0] == ("biorxiv", "neuroscience", "2026-11-02", "2026-11-09", "0")
    assert result.new_versions == {"biorxiv": 10, "medrxiv": 20}

    preprint = biorxiv.store("biorxiv", tmp_path).read_day(DAY)["10.1101/2023.12.11.571113"]
    assert preprint["version"] == 2 and preprint["license"] == "cc_by_nc"
    assert preprint["authors"][0] == "Rahman, K. F." and preprint["published_doi"] is None
    assert "abstract" not in preprint


def test_two_versions_of_a_doi_are_one_preprint_and_the_newest_wins(tmp_path):
    v1 = copy.deepcopy(fixture("biorxiv", "neuroscience")["collection"][0])
    v1.update(doi="10.1101/2026.01.01.000001", version="1", date="2026-11-03")
    v2 = {**v1, "version": "2", "date": "2026-11-08", "published": "10.1038/S41593-026-1"}
    result = run(tmp_path, FakeBiorxiv(extra=[v2, v1]))
    assert result.found["biorxiv/neuroscience"] == 11
    stored = biorxiv.store("biorxiv", tmp_path).read_day(DAY)["10.1101/2026.01.01.000001"]
    assert stored["version"] == 2 and stored["published_doi"] == "10.1038/s41593-026-1"


def test_an_older_version_never_replaces_a_newer_one_stored_before(tmp_path):
    v1 = copy.deepcopy(fixture("biorxiv", "neuroscience")["collection"][0])
    v1.update(doi="10.1101/2026.01.01.000002", version="1")
    v2 = {**v1, "version": "2"}
    run(tmp_path, FakeBiorxiv(extra=[v2]))
    next_day = DAY + dt.timedelta(days=1)
    run(tmp_path, FakeBiorxiv(extra=[v1]), today=next_day)
    latest = biorxiv.store("biorxiv", tmp_path).recent(3, next_day)
    assert latest["10.1101/2026.01.01.000002"].payload["version"] == 2


def test_reruns_write_nothing(tmp_path):
    run(tmp_path, FakeBiorxiv())
    assert run(tmp_path, FakeBiorxiv()).new_versions == {"biorxiv": 0, "medrxiv": 0}
    next_day = DAY + dt.timedelta(days=1)
    assert run(tmp_path, FakeBiorxiv(), today=next_day).new_versions == {
        "biorxiv": 0, "medrxiv": 0,
    }  # fmt: skip


def test_abstracts_go_only_to_the_cache(tmp_path):
    entry = copy.deepcopy(fixture("biorxiv", "neuroscience")["collection"][0])
    entry.update(doi="10.1101/2026.01.01.000003", abstract="Authors' own words.")
    result = run(tmp_path, FakeBiorxiv(extra=[entry]))
    assert result.abstracts_cached >= 1
    cached = tmp_path / "cache" / "biorxiv" / "abstract" / "10.1101_2026.01.01.000003.json"
    assert "Authors' own words." in cached.read_text(encoding="utf-8")
    for server in ("biorxiv", "medrxiv"):
        text = biorxiv.store(server, tmp_path).path(DAY).read_text(encoding="utf-8")
        assert "Authors' own words." not in text and "REDACTED" not in text


def test_has_new_preprints_sees_new_dois_and_new_versions(tmp_path):
    item = {"doi": "10.1101/X", "version": "1"}
    body = {"collection": [item], "messages": [{"total": "1"}]}
    with make_client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as c:
        assert biorxiv.has_new_preprints(c, today=DAY, raw_root=tmp_path)
        biorxiv.store("biorxiv", tmp_path).save({"10.1101/x": {"version": 1}}, DAY)
        assert not biorxiv.has_new_preprints(c, today=DAY, raw_root=tmp_path)
        item["version"] = "2"
        assert biorxiv.has_new_preprints(c, today=DAY, raw_root=tmp_path)
