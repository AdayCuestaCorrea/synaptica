"""Weekly mirror of the marts in the BigQuery sandbox (plan, step 29; decision D1, ADR 0001).

DuckDB stays the warehouse, rebuilt every day. Once a week the marts are exported to
Parquet (DuckDB's ``COPY … TO``, no new dependency) and the pipeline loads them with
``bq load --replace``: load jobs are free and need no DML, which the sandbox does not
allow (spike S2). This module only chooses and exports; ``bq`` runs in the workflow,
authenticated by Workload Identity Federation (no stored key).

The sandbox gives 10 GiB of storage (S2), so an export bigger than :data:`MAX_BYTES` is
refused before anything is sent, and each mirror appends its tables, rows and bytes to
``mirror/bigquery.jsonl`` on the data branch: the usage stays measured, run after run.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

MARTS = ("dim_study", "fct_news_item")  # dbt/models/marts; nothing from staging or cache
MAX_BYTES = 1 * 1024**3  # 1 GiB per mirror: a tenth of the sandbox, far above today's size


@dataclass(frozen=True)
class Table:
    name: str
    rows: int
    bytes: int
    path: Path


class TooBig(RuntimeError):
    pass


def export(warehouse: Path, out: Path, marts: tuple[str, ...] = MARTS) -> list[Table]:
    """Each mart to ``out/<name>.parquet``; raises :class:`TooBig` above :data:`MAX_BYTES`."""
    out.mkdir(parents=True, exist_ok=True)
    tables = []
    with duckdb.connect(str(warehouse), read_only=True) as con:
        for name in marts:
            path = out / f"{name}.parquet"
            con.execute(f"copy (select * from main.{name}) to '{path}' (format parquet)")
            rows = con.execute(f"select count(*) from main.{name}").fetchone()[0]
            tables.append(Table(name, rows, path.stat().st_size, path))
    total = sum(t.bytes for t in tables)
    if total > MAX_BYTES:
        raise TooBig(f"{total} bytes to mirror, above the {MAX_BYTES} allowed")
    return tables


def record(log: Path, tables: list[Table], stored: dict[str, int] | None = None,
           today: dt.date | None = None) -> dict:  # fmt: skip
    """Append one mirror to the usage log: rows and Parquet bytes per table, and the bytes
    BigQuery reports as stored (``bq show``), when known."""
    entry = {
        "date": (today or dt.datetime.now(dt.UTC).date()).isoformat(),
        "tables": {t.name: {"rows": t.rows, "parquet_bytes": t.bytes,
                            "stored_bytes": (stored or {}).get(t.name)} for t in tables},
        "parquet_bytes": sum(t.bytes for t in tables),
    }  # fmt: skip
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry
