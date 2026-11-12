"""Tests for the raw store. Adapted from paleo-atlas ``tests/test_store.py``."""

import datetime as dt
import json

from synaptica.store import RawStore, safe_key, utc_today

DAY1 = dt.date(2026, 11, 1)
DAY2 = dt.date(2026, 11, 8)


def make(tmp_path, **kwargs):
    return RawStore("pubmed", "summary", raw_root=tmp_path, **kwargs)


def test_first_save_creates_a_version(tmp_path):
    store = make(tmp_path)
    result = store.save_if_changed("41234567", {"found": True}, DAY1)
    assert result.created
    assert result.path == tmp_path / "pubmed" / "summary" / "41234567" / "2026-11-01.json"
    record = json.loads(result.path.read_text(encoding="utf-8"))
    assert record["key"] == "41234567"
    assert record["version_date"] == "2026-11-01"
    assert record["payload"] == {"found": True}


def test_same_payload_does_not_create_a_new_version(tmp_path):
    store = make(tmp_path)
    store.save_if_changed("41234567", {"found": True, "n": 1}, DAY1)
    again = store.save_if_changed("41234567", {"n": 1, "found": True}, DAY2)  # key order
    assert not again.created
    assert len(store.versions("41234567")) == 1


def test_changed_payload_creates_a_new_version(tmp_path):
    store = make(tmp_path)
    store.save_if_changed("41234568", {"found": False}, DAY1)
    result = store.save_if_changed("41234568", {"found": True}, DAY2)
    assert result.created
    assert [p.name for p in store.versions("41234568")] == ["2026-11-01.json", "2026-11-08.json"]
    assert store.latest("41234568")["payload"] == {"found": True}


def test_volatile_fields_are_ignored_and_not_stored(tmp_path):
    store = make(tmp_path, volatile={"elapsed_time"})
    store.save_if_changed("T", {"records": [1], "elapsed_time": 0.1}, DAY1)
    again = store.save_if_changed("T", {"records": [1], "elapsed_time": 0.9}, DAY2)
    assert not again.created
    assert store.latest("T")["payload"] == {"records": [1]}


def test_volatile_fields_are_ignored_when_nested(tmp_path):
    store = make(tmp_path, volatile={"score"})
    store.save_if_changed("doi", {"work": {"title": "A", "score": 1}}, DAY1)
    assert not store.save_if_changed("doi", {"work": {"title": "A", "score": 7}}, DAY2).created


def test_freshness_uses_the_last_check_not_the_last_change(tmp_path):
    store = make(tmp_path)
    store.save_if_changed("41234567", {"found": True}, DAY1)
    store.save_if_changed("41234567", {"found": True}, DAY2)  # unchanged, but checked
    store.flush()
    reloaded = make(tmp_path)
    assert reloaded.is_fresh("41234567", 7, today=DAY2 + dt.timedelta(days=6))
    assert not reloaded.is_fresh("41234567", 7, today=DAY2 + dt.timedelta(days=7))
    assert not reloaded.is_fresh("Never seen", 7, today=DAY2)


def test_stored_keys_returns_original_keys(tmp_path):
    store = make(tmp_path)
    store.save_if_changed("10.1126/science.adx5486", {"found": True}, DAY1)
    store.save_if_changed("41234569", {"found": True}, DAY1)
    assert sorted(store.stored_keys()) == ["10.1126/science.adx5486", "41234569"]


def test_safe_key_keeps_distinct_keys_distinct():
    assert safe_key("41234567") == "41234567"
    assert safe_key("10.1/a/b") != safe_key("10.1/a_b")
    assert "/" not in safe_key("10.1126/science.adx5486")


def test_saving_without_marking_checked_keeps_the_freshness_date(tmp_path):
    import datetime as dt

    store = RawStore("s", "k", raw_root=tmp_path)
    store.save_if_changed("a", {"v": 1}, dt.date(2026, 1, 1))
    store.save_if_changed("a", {"v": 2}, dt.date(2026, 1, 20), mark_checked=False)
    assert store.latest("a")["payload"] == {"v": 2}
    assert not store.is_fresh("a", 7, dt.date(2026, 1, 20))  # still due for a real check


def test_default_date_is_utc(tmp_path, monkeypatch):
    import datetime as real_dt

    class FakeDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            # 23:30 UTC on 1 Nov is already 2 Nov in UTC+1: the store must use UTC.
            return real_dt.datetime(2026, 11, 1, 23, 30, tzinfo=real_dt.UTC).astimezone(tz)

    monkeypatch.setattr("synaptica.store.dt.datetime", FakeDateTime)
    assert utc_today() == real_dt.date(2026, 11, 1)
    result = make(tmp_path).save_if_changed("41234567", {"found": True})
    assert result.path.name == "2026-11-01.json"
