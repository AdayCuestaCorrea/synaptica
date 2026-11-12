"""Versioned raw store for API responses (PubMed, Crossref, feeds…).

Copied and adapted from paleo-atlas ``src/paleo/store.py`` (same author, AGPL in both;
decision D2). Changes: dates default to today in UTC (CLAUDE.md convention) instead of the
local date.

Each entity (a PMID, a DOI, a feed…) gets its own folder with one file per *change*:

    data/raw/<source>/<kind>/<key>/<YYYY-MM-DD>.json

A new file is written only when the payload differs from the latest stored version,
ignoring volatile fields such as response timings. History is then computed from these
versions in SQL, which keeps the pipeline idempotent and reproducible from git (the state
lives in the ``data`` branch and the warehouse is rebuilt on every run; SCOPE §6, D1).

A small ``_checked.json`` per ``<source>/<kind>`` remembers when each key was last
*checked*, so unchanged entities are not requested again on every run.

High-volume sources (PubMed: ~700 new records a day) use :class:`BatchStore` instead, one
file per day; see its docstring.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synaptica.config import get_paths

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_KEY_LENGTH = 80


@dataclass(frozen=True)
class SaveResult:
    path: Path
    created: bool  # False when the payload matched the latest stored version


def safe_key(key: str) -> str:
    """Filesystem-safe folder name; a short hash keeps distinct keys distinct.

    ``41234567`` -> ``41234567``; ``10.1126/science.adx5486`` ->
    ``10.1126_science.adx5486-1a2b3c4d``.
    """
    slug = _UNSAFE.sub("_", key.strip()).strip("_")[:MAX_KEY_LENGTH]
    if slug != key:
        slug = f"{slug}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]}"
    return slug or hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _strip(value: Any, volatile: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v, volatile) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [_strip(v, volatile) for v in value]
    return value


def _canonical(payload: Any, volatile: frozenset[str]) -> str:
    return json.dumps(_strip(payload, volatile), sort_keys=True, ensure_ascii=False)


def utc_today() -> dt.date:
    """Today's date in UTC: runs in CI and on Aday's laptop must agree on the day."""
    return dt.datetime.now(dt.UTC).date()


class RawStore:
    """Versioned snapshots for one ``source``/``kind`` (e.g. ``pubmed``/``summary``)."""

    def __init__(
        self,
        source: str,
        kind: str,
        *,
        volatile: Iterable[str] = (),
        raw_root: Path | None = None,
    ) -> None:
        self.source = source
        self.kind = kind
        self.volatile = frozenset(volatile)
        self.root = (raw_root if raw_root is not None else get_paths().raw) / source / kind
        self._checked_path = self.root / "_checked.json"
        self._checked: dict[str, str] | None = None

    # ------------------------------------------------------------------ reads

    def key_dir(self, key: str) -> Path:
        return self.root / safe_key(key)

    def versions(self, key: str) -> list[Path]:
        directory = self.key_dir(key)
        return sorted(directory.glob("*.json")) if directory.is_dir() else []

    def latest(self, key: str) -> dict[str, Any] | None:
        """Latest stored record ``{key, version_date, fetched_at, payload}``."""
        versions = self.versions(key)
        if not versions:
            return None
        return json.loads(versions[-1].read_text(encoding="utf-8"))

    def stored_keys(self) -> list[str]:
        """Original keys of every stored entity."""
        out = []
        for directory in sorted(p for p in self.root.glob("*") if p.is_dir()):
            versions = sorted(directory.glob("*.json"))
            if versions:
                out.append(json.loads(versions[-1].read_text(encoding="utf-8"))["key"])
        return out

    # ------------------------------------------------------------- freshness

    def _load_checked(self) -> dict[str, str]:
        if self._checked is None:
            self._checked = (
                json.loads(self._checked_path.read_text(encoding="utf-8"))
                if self._checked_path.exists()
                else {}
            )
        return self._checked

    def checked_on(self, key: str) -> str | None:
        """ISO date of the last check of ``key`` (None if never checked)."""
        return self._load_checked().get(key)

    def is_fresh(self, key: str, max_age_days: int, today: dt.date | None = None) -> bool:
        """True when ``key`` was checked less than ``max_age_days`` ago."""
        checked = self._load_checked().get(key)
        if checked is None:
            return False
        today = today or utc_today()
        return (today - dt.date.fromisoformat(checked)).days < max_age_days

    def mark_checked(self, key: str, today: dt.date | None = None) -> None:
        self._load_checked()[key] = (today or utc_today()).isoformat()

    def flush(self) -> None:
        """Persist the checked-at index (sorted, so diffs stay small)."""
        if self._checked is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        text = json.dumps(dict(sorted(self._checked.items())), indent=1, ensure_ascii=False)
        _atomic_write(self._checked_path, text + "\n")

    # ----------------------------------------------------------------- writes

    def save_if_changed(
        self, key: str, payload: Any, today: dt.date | None = None, *, mark_checked: bool = True
    ) -> SaveResult:
        """Store ``payload`` for ``key`` unless it equals the latest version.

        ``mark_checked=False`` keeps the checked-at date: for payloads partly
        rebuilt from local data without asking the source again.
        """
        today = today or utc_today()
        if mark_checked:
            self.mark_checked(key, today)
        previous = self.latest(key)
        directory = self.key_dir(key)
        if previous is not None and _canonical(previous["payload"], self.volatile) == _canonical(
            payload, self.volatile
        ):
            return SaveResult(self.versions(key)[-1], created=False)
        record = {
            "key": key,
            "source": self.source,
            "kind": self.kind,
            "version_date": today.isoformat(),
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "payload": _strip(payload, self.volatile),
        }
        path = directory / f"{today.isoformat()}.json"  # same-day changes: latest wins
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
        return SaveResult(path, created=True)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --- daily batches, for high-volume sources ------------------------------------------


@dataclass(frozen=True)
class BatchEntry:
    first_seen: dt.date  # date of the oldest file (within the window) holding the key
    last_seen: dt.date  # date of the newest one
    payload: Any  # payload in the newest one


class BatchStore:
    """Daily batch files for sources with hundreds of new entities a day (PubMed).

    Not in Paleo Atlas: added for SYNAPTICA, where one folder per entity (:class:`RawStore`)
    would mean ~500 000 files and a ``_checked.json`` of several MB rewritten every day
    after a year. Layout, one JSON object per line, sorted by key::

        data/raw/<source>/<kind>/<YYYY-MM-DD>.jsonl   {"key": ..., "payload": ...}

    A day's file holds the entities that were new or changed that day. What is already
    stored is read from the files of the last few days only (:meth:`recent`), which is
    enough when a source can be asked "what is new since date X". Same-day reruns merge
    into the day's file, so saving the same records twice writes nothing new.
    """

    def __init__(
        self,
        source: str,
        kind: str,
        *,
        volatile: Iterable[str] = (),
        raw_root: Path | None = None,
    ) -> None:
        self.source = source
        self.kind = kind
        self.volatile = frozenset(volatile)
        self.root = (raw_root if raw_root is not None else get_paths().raw) / source / kind

    def path(self, day: dt.date) -> Path:
        return self.root / f"{day.isoformat()}.jsonl"

    def read_day(self, day: dt.date) -> dict[str, Any]:
        path = self.path(day)
        if not path.exists():
            return {}
        rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        return {row["key"]: row["payload"] for row in rows}

    def recent(self, days: int, today: dt.date | None = None) -> dict[str, BatchEntry]:
        """Every key stored in the files of the last ``days`` days (today included)."""
        today = today or utc_today()
        out: dict[str, BatchEntry] = {}
        for offset in range(days - 1, -1, -1):  # oldest first, so the newest payload wins
            day = today - dt.timedelta(days=offset)
            for key, payload in self.read_day(day).items():
                first = out[key].first_seen if key in out else day
                out[key] = BatchEntry(first_seen=first, last_seen=day, payload=payload)
        return out

    def save(
        self,
        records: dict[str, Any],
        today: dt.date | None = None,
        *,
        previous: dict[str, Any] | None = None,
    ) -> int:
        """Add to today's file the records that differ from ``previous`` (key -> payload
        last stored, usually from :meth:`recent`). Returns how many lines were added or
        changed; 0 leaves the file untouched."""
        today = today or utc_today()
        previous = previous or {}
        day = self.read_day(today)
        changed = 0
        for key, payload in records.items():
            payload = _strip(payload, self.volatile)
            canonical = _canonical(payload, frozenset())
            if key in previous and _canonical(previous[key], self.volatile) == canonical:
                continue
            if key in day and _canonical(day[key], frozenset()) == canonical:
                continue
            day[key] = payload
            changed += 1
        if changed:
            self.root.mkdir(parents=True, exist_ok=True)
            lines = (
                json.dumps({"key": k, "payload": day[k]}, ensure_ascii=False, sort_keys=True)
                for k in sorted(day)
            )
            _atomic_write(self.path(today), "\n".join(lines) + "\n")
        return changed
