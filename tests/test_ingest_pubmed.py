"""PubMed ingestion with the S1 fixtures behind ``httpx.MockTransport`` (no network)."""

import datetime as dt
import json
from urllib.parse import parse_qs

import httpx
import pytest

from synaptica.config import project_root
from synaptica.http import HttpError, Throttle, make_client
from synaptica.ingest import pubmed

FIXTURES = project_root() / "tests" / "fixtures" / "pubmed"
ESEARCH = json.loads((FIXTURES / "esearch.json").read_text(encoding="utf-8"))
ESUMMARY = json.loads((FIXTURES / "esummary.json").read_text(encoding="utf-8"))
EFETCH = (FIXTURES / "efetch.xml").read_text(encoding="utf-8")
PMIDS = ESEARCH["esearchresult"]["idlist"]
DAY = dt.date(2026, 11, 9)


class FakePubMed:
    """Answers esearch, esummary and efetch from the fixtures and records each call."""

    def __init__(self, efetch: str = EFETCH, pmids: list[str] = PMIDS):
        self.pmids = pmids
        self.calls: list[tuple[str, dict[str, list[str]]]] = []
        self.efetch = efetch

    def __call__(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1].removesuffix(".fcgi")
        params = parse_qs(request.url.query.decode())
        self.calls.append((name, params))
        if name == "esearch":
            first_page = params["retstart"] == ["0"]
            idlist = self.pmids if first_page else []
            return httpx.Response(200, json={"esearchresult": {**ESEARCH["esearchresult"],
                                                               "idlist": idlist}})  # fmt: skip
        if name == "esummary":
            ids = params["id"][0].split(",")
            result = {"uids": ids, **{i: ESUMMARY["result"][i] for i in ids}}
            return httpx.Response(200, json={"result": result})
        return httpx.Response(200, text=self.efetch)

    def ids(self, name: str) -> list[str]:
        return [i for n, p in self.calls if n == name for i in p["id"][0].split(",")]


def run(tmp_path, fake, today=DAY, **kwargs):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return pubmed.ingest(
            client, today=today, raw_root=tmp_path / "raw", cache_root=tmp_path / "cache",
            throttle=Throttle(1000, sleep=lambda _: None), api_key="", **kwargs,
        )  # fmt: skip


def test_first_run_stores_metadata_and_indexing_and_caches_abstracts(tmp_path):
    fake = FakePubMed()
    result = run(tmp_path, fake)
    assert result.found == 10 and result.summaries_new_versions == 10
    assert result.medline_new_versions == 10 and result.abstracts_cached == 10
    assert sorted(p.name for p in (tmp_path / "raw/pubmed").rglob("*.jsonl")) == [
        "2026-11-09.jsonl", "2026-11-09.jsonl",
    ]  # one daily batch per kind  # fmt: skip

    summary = pubmed.summary_store(tmp_path / "raw").read_day(DAY)["43002189"]
    assert summary["fulljournalname"] == "Journal of neuro-oncology"
    assert summary["articleids"]["doi"] == "10.1007/s11060-026-05870-3"
    assert set(summary) <= set(pubmed.SUMMARY_FIELDS)  # trimmed: no history, sort keys…
    assert all(isinstance(a, str) for a in summary["authors"])

    medline = pubmed.medline_store(tmp_path / "raw").read_day(DAY)
    assert medline["43002171"]["status"] == "MEDLINE"
    humans = {"ui": "D006801", "name": "Humans", "major": False, "qualifiers": []}
    assert humans in medline["43002171"]["mesh"]
    assert medline["43002189"]["status"] == "Publisher" and medline["43002189"]["mesh"] == []


def test_abstracts_never_reach_the_versioned_store(tmp_path):
    run(tmp_path, FakePubMed())
    raw_text = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "raw").rglob("*.jsonl"))
    assert "REDACTED" not in raw_text and "AbstractText" not in raw_text
    cached = json.loads((tmp_path / "cache/pubmed/abstract/43002189.json").read_text())
    assert cached["sections"][0]["label"] == "BACKGROUND"


def test_requests_identify_us_and_page_until_the_results_end(tmp_path):
    fake = FakePubMed()
    run(tmp_path, fake, days=1)
    searches = [p for n, p in fake.calls if n == "esearch"]
    assert [s["retstart"] for s in searches] == [["0"], ["10"]]  # second page is empty
    assert searches[0]["reldate"] == ["1"] and searches[0]["datetype"] == ["edat"]
    assert all(p["tool"] == ["synaptica"] and "@" in p["email"][0] for _, p in fake.calls)
    assert all("api_key" not in p for _, p in fake.calls)


def snapshot(tmp_path):
    return {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json*")}


def test_a_second_run_the_same_day_requests_nothing_new_and_writes_nothing(tmp_path):
    run(tmp_path, FakePubMed())
    before = snapshot(tmp_path)
    fake = FakePubMed()
    result = run(tmp_path, fake)
    assert fake.ids("esummary") == [] and fake.ids("efetch") == []
    assert result.summaries_new_versions == result.medline_new_versions == 0
    assert snapshot(tmp_path) == before


def test_the_next_day_only_new_pmids_are_requested(tmp_path):
    run(tmp_path, FakePubMed())
    fake = FakePubMed()
    run(tmp_path, fake, today=DAY + dt.timedelta(days=1))  # same 10 PMIDs still in window
    assert fake.ids("esummary") == [] and fake.ids("efetch") == []


def test_records_waiting_for_indexing_are_rechecked_weekly_until_too_old(tmp_path):
    run(tmp_path, FakePubMed())
    waiting = {"43002189", "43002187", "43002166", "43002157", "43002151", "43002149"}
    for offset in (6, 8):
        fake = FakePubMed()
        run(tmp_path, fake, today=DAY + dt.timedelta(days=offset))
        assert fake.ids("efetch") == []  # only on 7, 14… days of age

    fake = FakePubMed()
    result = run(tmp_path, fake, today=DAY + dt.timedelta(days=7))
    assert set(fake.ids("efetch")) == waiting  # indexed ones (MEDLINE) are never asked again
    assert result.medline_new_versions == 0  # same answer: nothing written

    fake = FakePubMed(pmids=[])  # long out of the search window
    run(tmp_path, fake, today=DAY + dt.timedelta(days=98))
    assert fake.ids("efetch") == []


def test_a_record_that_gets_indexed_is_stored_again_and_then_left_alone(tmp_path):
    run(tmp_path, FakePubMed())
    indexed = EFETCH.replace('Status="Publisher"', 'Status="MEDLINE"')
    day7 = DAY + dt.timedelta(days=7)
    result = run(tmp_path, FakePubMed(efetch=indexed), today=day7)
    assert result.medline_new_versions == 6
    assert pubmed.medline_store(tmp_path / "raw").read_day(day7)["43002189"]["status"] == "MEDLINE"
    fake = FakePubMed(efetch=indexed)
    run(tmp_path, fake, today=DAY + dt.timedelta(days=14))
    assert fake.ids("efetch") == []


def test_final_statuses_are_not_rechecked():
    first = dt.date(2026, 1, 1)
    day7 = first + dt.timedelta(days=7)
    assert not pubmed.medline_recheck_due("PubMed-not-MEDLINE", first, day7)
    assert not pubmed.medline_recheck_due("MEDLINE", first, day7)
    assert pubmed.medline_recheck_due("In-Process", first, day7)


def test_the_throttle_keeps_the_published_rate():
    now = [0.0]
    waits = []

    def sleep(seconds):
        waits.append(round(seconds, 3))
        now[0] += seconds

    throttle = Throttle(3, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        throttle.wait()
    assert waits == [0.333, 0.333]


def test_the_api_key_raises_the_rate_and_is_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("NCBI_API_KEY", "k")
    assert pubmed.base_params("k")["api_key"] == "k"
    fake = FakePubMed()
    with make_client(transport=httpx.MockTransport(fake)) as client:
        pubmed.ingest(
            client, today=DAY, raw_root=tmp_path / "raw", cache_root=tmp_path / "cache",
            throttle=Throttle(1000, sleep=lambda _: None),
        )  # fmt: skip
    assert all(p["api_key"] == ["k"] for _, p in fake.calls)


def test_an_esearch_error_is_raised(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"esearchresult": {"ERROR": "Invalid query"}})

    with make_client(transport=httpx.MockTransport(handler)) as client, pytest.raises(HttpError):
        pubmed.search(client, 1, pubmed.base_params(None), Throttle(1000, sleep=lambda _: None))
