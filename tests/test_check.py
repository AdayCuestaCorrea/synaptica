"""``syn check``: cheap change detection, with the exit codes of paleo-atlas ADR D10."""

import datetime as dt

import httpx
from typer.testing import CliRunner

from synaptica import cli
from synaptica.http import make_client
from synaptica.ingest import crossref, pubmed

runner = CliRunner()
TODAY = dt.date(2026, 11, 9)


def esearch(ids):
    return {"esearchresult": {"count": str(len(ids)), "idlist": ids}}


def crossref_page(dois):
    return {"message": {"items": [{"DOI": d} for d in dois]}}


FEED_HOSTS = {"www.nature.com", "www.science.org", "www.cell.com", "www.sciencedaily.com",
              "theconversation.com", "www.agenciasinc.es"}  # fmt: skip
EMPTY_FEED = "<rss><channel></channel></rss>"


def answer(pmids, dois):
    def handler(request):
        if request.url.host in FEED_HOSTS:
            return httpx.Response(200, text=EMPTY_FEED)
        if request.url.host == "eutils.ncbi.nlm.nih.gov":
            return httpx.Response(200, json=esearch(pmids))
        return httpx.Response(200, json=crossref_page(dois))

    return handler


def test_new_pmids_and_notices_are_detected_against_the_store(tmp_path):
    pubmed.summary_store(tmp_path).save({"1": {"uid": "1"}}, TODAY)
    crossref.store(tmp_path).save({"10.1/n": {"doi": "10.1/n", "updates": []}}, TODAY)
    with make_client(transport=httpx.MockTransport(answer(["1"], ["10.1/N"]))) as client:
        assert not pubmed.has_new_records(client, today=TODAY, raw_root=tmp_path, api_key="")
        assert not crossref.has_new_notices(client, today=TODAY, raw_root=tmp_path)
    with make_client(transport=httpx.MockTransport(answer(["1", "2"], ["10.1/x"]))) as client:
        assert pubmed.has_new_records(client, today=TODAY, raw_root=tmp_path, api_key="")
        assert crossref.has_new_notices(client, today=TODAY, raw_root=tmp_path)


def patch_client(monkeypatch, handler):
    real = make_client
    monkeypatch.setattr("synaptica.http.make_client", lambda: real(httpx.MockTransport(handler)))


def test_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    patch_client(monkeypatch, answer(["1"], []))
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 0 and "changed: pubmed" in result.stdout

    patch_client(monkeypatch, answer([], []))
    assert runner.invoke(cli.app, ["check"]).exit_code == 1


def test_a_failing_source_exits_2_never_no_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))

    def down(request):
        raise httpx.ConnectError("down", request=request)

    patch_client(monkeypatch, down)
    monkeypatch.setattr("synaptica.http.time.sleep", lambda _: None)  # skip the backoff
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 2 and "check failed" in result.output
