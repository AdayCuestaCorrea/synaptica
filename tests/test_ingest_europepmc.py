"""Europe PMC with the S1 fixture behind ``httpx.MockTransport`` (no network)."""

import datetime as dt
import json
from urllib.parse import parse_qs

import httpx

from synaptica.config import project_root
from synaptica.http import Throttle, make_client
from synaptica.ingest import europepmc

FIXTURE = project_root() / "tests" / "fixtures" / "europepmc" / "search_core.json"
DAY = dt.date(2026, 11, 9)
NO_WAIT = Throttle(1000, sleep=lambda _: None)


class FakeEuropePmc:
    """First page: the S1 fixture (10 records); then an empty page. Full text: a tiny XML
    for PMC13730387, 404 for anything else."""

    def __init__(self):
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if request.url.path.endswith("/fullTextXML"):
            if "PMC13730387" in request.url.path:
                return httpx.Response(200, text="<article>body</article>")
            return httpx.Response(404, text="not found")
        params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        body = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if params["cursorMark"] != "*":
            body["resultList"]["result"] = []
        return httpx.Response(200, json=body)


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return europepmc.ingest(client, today=today, raw_root=tmp_path, throttle=NO_WAIT)


def test_open_access_records_indexed_in_the_window_are_trimmed_and_stored(tmp_path):
    fake = FakeEuropePmc()
    result = run(tmp_path, fake)
    assert (result.found, result.new_versions) == (10, 10)
    params = parse_qs(fake.calls[0].url.query.decode())
    assert params["query"][0].endswith("OPEN_ACCESS:y AND FIRST_IDATE:[2026-11-06 TO 2026-11-09]")
    assert params["resultType"] == ["core"] and "@" in params["email"][0]
    assert len(fake.calls) == 1  # a short page is the last one; no full text requested

    record = europepmc.store(tmp_path).read_day(DAY)["MED:42976197"]
    assert record["doi"] == "10.1371/journal.pone.0362090"
    assert record["pmcid"] == "PMC13730387" and record["license"] == "cc by"
    assert record["is_open_access"] and record["first_indexed"] == "2026-11-04"
    assert record["journal"] == "PloS one" and "Cerebral Cortex" in record["mesh"]
    assert record["authors"][0] == "Lachinova DA"


def test_full_pages_follow_the_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(europepmc, "PAGE", 10)
    fake = FakeEuropePmc()
    run(tmp_path, fake)
    cursors = [parse_qs(c.url.query.decode())["cursorMark"][0] for c in fake.calls]
    assert cursors == ["*", "AoIIQD1OJSg1Njg0NDcyMg=="]


def test_reruns_write_nothing(tmp_path):
    run(tmp_path, FakeEuropePmc())
    before = europepmc.store(tmp_path).path(DAY).read_bytes()
    assert run(tmp_path, FakeEuropePmc()).new_versions == 0
    assert europepmc.store(tmp_path).path(DAY).read_bytes() == before
    next_day = DAY + dt.timedelta(days=1)
    assert run(tmp_path, FakeEuropePmc(), today=next_day).new_versions == 0


def test_publisher_text_never_reaches_the_store(tmp_path):
    run(tmp_path, FakeEuropePmc())
    text = europepmc.store(tmp_path).path(DAY).read_text(encoding="utf-8")
    assert "abstract" not in text.lower() and "REDACTED" not in text and "affiliation" not in text


def test_full_text_on_demand_goes_to_the_cache_once(tmp_path):
    fake = FakeEuropePmc()
    with make_client(transport=httpx.MockTransport(fake)) as client:
        xml = europepmc.fetch_fulltext(client, "PMC13730387", cache_root=tmp_path)
        again = europepmc.fetch_fulltext(client, "PMC13730387", cache_root=tmp_path)
        missing = europepmc.fetch_fulltext(client, "PMC1", cache_root=tmp_path)
    assert xml == again == "<article>body</article>" and missing is None
    assert len(fake.calls) == 2  # the second read came from the cache
    assert europepmc.fulltext_path(tmp_path, "PMC13730387").exists()
    assert not (tmp_path / "raw").exists()


def test_has_new_records(tmp_path):
    body = {"resultList": {"result": [{"source": "MED", "id": "1"}]}}
    handler = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    with make_client(transport=handler) as client:
        assert europepmc.has_new_records(client, today=DAY, raw_root=tmp_path)
        europepmc.store(tmp_path).save({"MED:1": {"id": "1"}}, DAY)
        assert not europepmc.has_new_records(client, today=DAY, raw_root=tmp_path)
