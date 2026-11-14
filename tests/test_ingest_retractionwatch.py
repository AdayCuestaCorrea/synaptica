"""Retraction Watch CSV with real rows (fixture) behind ``httpx.MockTransport`` (no network)."""

import csv
import datetime as dt
import io
import json

import httpx
import pytest

from synaptica.config import project_root
from synaptica.http import HttpError, make_client
from synaptica.ingest import retractionwatch as rw

FIXTURE = project_root() / "tests" / "fixtures" / "retractionwatch" / "retraction_watch.csv"
DAY = dt.date(2026, 11, 13)


class FakeGitLab:
    """Answers with ``text`` and an ETag; 304 when the request carries that ETag."""

    def __init__(self, text=None, etag='"v1"'):
        self.text = FIXTURE.read_text(encoding="utf-8") if text is None else text
        self.etag = etag
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if request.headers.get("If-None-Match") == self.etag:
            return httpx.Response(304)
        return httpx.Response(200, text=self.text, headers={"ETag": self.etag})


def run(tmp_path, fake, today=DAY):
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return rw.ingest(client, today=today, raw_root=tmp_path / "raw",
                         cache_root=tmp_path / "cache")  # fmt: skip


def without(text, record_ids):
    """The fixture CSV without some records (as if they left the database)."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    out = io.StringIO()
    csv.writer(out).writerows([rows[0], *(r for r in rows[1:] if r[0] not in record_ids)])
    return out.getvalue()


def test_rows_are_trimmed_to_facts_and_unmatchable_rows_dropped(tmp_path):
    result = run(tmp_path, FakeGitLab())
    assert (result.downloaded, result.rows, result.kept, result.removed) == (True, 9, 8, 0)
    stored = rw.store(tmp_path / "raw").read_day(DAY)
    assert "16405" not in stored  # no DOI and PubMed ID 0: nothing to match it with
    assert stored["54364"] == {  # Lesné et al. 2006, also retracted in Crossref
        "doi": "10.1038/nature04533", "pmid": "16541076", "nature": "retraction",
        "notice_doi": "10.1038/s41586-024-07691-8", "date": "2024-06-24",
    }  # fmt: skip
    assert stored["74241"]["doi"] == "10.1002/2013ja019349"  # lower case, as dbt joins
    assert stored["73062"]["doi"] is None and stored["73062"]["pmid"] == "23852909"
    assert stored["71659"]["notice_doi"] is None  # "unavailable"
    assert stored["72927"]["nature"] == "reinstatement"
    assert {p["nature"] for p in stored.values()} == {
        "retraction",
        "expression_of_concern",
        "correction",
        "reinstatement",
    }
    assert all(set(p) == {"doi", "pmid", "nature", "notice_doi", "date"}
               for p in stored.values())  # no title, authors, reasons or notes  # fmt: skip


def test_identified_request_and_a_304_reads_nothing(tmp_path):
    fake = FakeGitLab()
    run(tmp_path, fake)
    assert "synaptica" in fake.calls[0].headers["User-Agent"]
    assert "If-None-Match" not in fake.calls[0].headers  # no ETag cached yet
    again = run(tmp_path, fake)
    assert fake.calls[1].headers["If-None-Match"] == '"v1"'
    assert again == rw.RetractionWatchResult(False, 0, 0, 0, 0)


def test_idempotent_and_only_changes_are_stored_the_next_day(tmp_path):
    fake = FakeGitLab()
    run(tmp_path, fake)
    fake.etag = '"v2"'  # a new commit with the same content: nothing to write
    assert run(tmp_path, fake, DAY + dt.timedelta(days=1)).new_versions == 0
    # A retraction becomes a reinstatement in the same record (as Retraction Watch does).
    fake.text = fake.text.replace(",Retraction,", ",Reinstatement,", 1)
    fake.etag = '"v3"'
    later = DAY + dt.timedelta(days=2)
    assert run(tmp_path, fake, later).new_versions == 1
    day = rw.store(tmp_path / "raw").read_day(later)
    assert list(day) == ["54364"] and day["54364"]["nature"] == "reinstatement"


def test_a_record_that_leaves_the_csv_is_marked_removed(tmp_path):
    fake = FakeGitLab()
    run(tmp_path, fake)
    fake.text, fake.etag = without(fake.text, {"74241"}), '"v2"'
    result = run(tmp_path, fake, DAY + dt.timedelta(days=1))
    assert (result.new_versions, result.removed) == (1, 1)
    state = rw.store(tmp_path / "raw").all()
    assert state["74241"].payload == {"removed": True}
    assert state["54364"].first_seen == DAY  # untouched records keep their first file


def test_a_much_smaller_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "MIN_LIVE", 5)  # the fixture's 8 records are enough to guard
    fake = FakeGitLab()
    run(tmp_path, fake)
    ids = {r["Record ID"] for r in csv.DictReader(io.StringIO(fake.text, newline=""))}
    fake.text, fake.etag = without(fake.text, ids - {"54364"}), '"v2"'  # 1 of 8 left
    with pytest.raises(HttpError, match="refused"):
        run(tmp_path, fake, DAY + dt.timedelta(days=1))
    cached = json.loads((tmp_path / "cache" / "retractionwatch.json").read_text())
    assert cached["etag"] == '"v1"'  # not v2: tomorrow's run downloads it again
    assert (
        rw.store(tmp_path / "raw").all().keys() == rw.store(tmp_path / "raw").read_day(DAY).keys()
    )  # nothing marked removed


def test_a_changed_header_fails_loudly(tmp_path):
    with pytest.raises(HttpError, match="OriginalPaperDOI"):
        run(tmp_path, FakeGitLab(text="Record ID,Title\n1,A\n"))


@pytest.mark.parametrize(("value", "doi"), [
    ("10.1016/J.AGGP.2025.100215", "10.1016/j.aggp.2025.100215"),
    ("https://doi.org/10.1/X", "10.1/x"),
    ("Unavailable", None), ("unavailable", None), ("", None),
    ("xx10.1007/978-3-030-00524-5_9", None),  # a typo in the real CSV
])  # fmt: skip
def test_clean_doi(value, doi):
    assert rw.clean_doi(value) == doi


def test_clean_pmid_and_date():
    assert rw.clean_pmid("0") is None and rw.clean_pmid("") is None
    assert rw.clean_pmid("16541076") == "16541076"
    assert rw.clean_date("5/6/2026 0:00") == "2026-05-06"  # month first
    assert rw.clean_date("") is None
