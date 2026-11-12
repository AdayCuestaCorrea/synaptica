"""Ingest the test fixtures as if they came from the sources, with no network.

Adapted from paleo-atlas ``scripts/seed_fixture_data.py`` (decision D2). Instead of copying
files, it runs the real ingestion steps (``synaptica.ingest.*``) against
``httpx.MockTransport`` answering with the recorded S1 responses, so CI checks the same
code path as production, and records one run in the log. Then dbt can build end to end:

    SYN_DATA_DIR=/tmp/syn-ci uv run python scripts/seed_fixture_data.py
    SYN_DATA_DIR=/tmp/syn-ci uv run syn build --as-of 2026-11-09
"""

import datetime as dt
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from synaptica import report
from synaptica.config import get_paths
from synaptica.http import Throttle, make_client
from synaptica.ingest import biorxiv, crossref, europepmc, journals, news, pubmed

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
DAY = dt.date(2026, 11, 9)  # the S1 fixtures were recorded that day
NO_WAIT = Throttle(1000, sleep=lambda _: None)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


FEED_FIXTURES = {
    **{j.rss: FIXTURES / "journals" / f"{j.journal}.rss.xml" for j in journals.load_journals()},
    **{f.url: FIXTURES / "news" / f"{f.feed}.xml" for f in news.load_feeds()},
}


def answer(request: httpx.Request) -> httpx.Response:
    """The recorded response for each request the ingestion steps make."""
    params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
    name = request.url.path.rsplit("/", 1)[-1]
    if request.url.host == "eutils.ncbi.nlm.nih.gov":
        if name == "esearch.fcgi":
            search = _json(FIXTURES / "pubmed" / "esearch.json")
            if params["retstart"] != "0":
                search["esearchresult"]["idlist"] = []
            return httpx.Response(200, json=search)
        if name == "esummary.fcgi":
            return httpx.Response(200, json=_json(FIXTURES / "pubmed" / "esummary.json"))
        return httpx.Response(200, text=(FIXTURES / "pubmed" / "efetch.xml").read_text("utf-8"))
    if str(request.url) in FEED_FIXTURES:
        return httpx.Response(200, text=FEED_FIXTURES[str(request.url)].read_text("utf-8"))
    if request.url.host == "api.crossref.org" and request.url.path.startswith("/journals/"):
        return httpx.Response(200, json={"message": {"items": []}})
    if request.url.host == "api.crossref.org":
        kind = params["filter"].split(",")[0].removeprefix("update-type:")
        path = FIXTURES / "crossref" / f"notices_{kind}.json"
        items = _json(path)["message"]["items"] if path.exists() and params["cursor"] == "*" else []
        return httpx.Response(200, json={"message": {"items": items}})
    if request.url.host == "api.biorxiv.org":
        _, _, server, _, _, cursor = request.url.path.split("/")
        body = _json(FIXTURES / server / f"details_{params['category']}.json")
        if cursor != "0":
            body["collection"] = []
        body["messages"][0]["total"] = str(len(body["collection"]))
        return httpx.Response(200, json=body)
    if request.url.host == "www.ebi.ac.uk":
        search = _json(FIXTURES / "europepmc" / "search_core.json")
        if params["cursorMark"] != "*":
            search["resultList"]["result"] = []
        return httpx.Response(200, json=search)
    return httpx.Response(404, text=f"no fixture for {request.url}")


def main() -> None:
    data = get_paths().data
    with make_client(transport=httpx.MockTransport(answer)) as client:
        print(pubmed.ingest(client, today=DAY, api_key="", throttle=NO_WAIT))
        print(crossref.ingest(client, today=DAY, throttle=NO_WAIT))
        print(europepmc.ingest(client, today=DAY, throttle=NO_WAIT))
        print(biorxiv.ingest(client, today=DAY, throttle=NO_WAIT))
        print(journals.ingest(client, today=DAY, throttle=NO_WAIT))
        print(news.ingest(client, today=DAY, throttle=NO_WAIT))
    moment = dt.datetime(2026, 11, 9, 6, 23, tzinfo=dt.UTC)
    report.start_run(data, trigger="manual", changed=True, now=moment)
    report.finish_run(data, now=moment)
    print(f"Seeded {data}")


if __name__ == "__main__":
    main()
