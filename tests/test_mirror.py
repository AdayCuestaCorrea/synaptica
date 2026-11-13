"""Weekly BigQuery mirror (plan, step 29): which tables leave, their size limit and the
usage log. No network and no BigQuery: `bq load` runs only in the workflow."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from synaptica import cli, mirror


def warehouse(path: Path) -> Path:
    with duckdb.connect(str(path)) as con:
        con.execute(
            "create table dim_study as select 'doi:10.1/a' as study_id, 'Neuron' as journal"
        )
        con.execute("create table fct_news_item as select 'news:a' as news_item_id")
        con.execute("create table stg_pubmed as select 'private' as abstract")  # not a mart
    return path


def test_only_the_marts_leave_and_their_size_is_counted(tmp_path: Path) -> None:
    tables = mirror.export(warehouse(tmp_path / "w.duckdb"), tmp_path / "out")
    assert [t.name for t in tables] == ["dim_study", "fct_news_item"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "dim_study.parquet", "fct_news_item.parquet"]  # fmt: skip
    assert all(t.rows == 1 and t.bytes > 0 for t in tables)
    with duckdb.connect() as con:
        back = con.execute(f"select * from '{tmp_path / 'out' / 'dim_study.parquet'}'").fetchall()
    assert back == [("doi:10.1/a", "Neuron")]


def test_an_export_above_the_limit_is_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mirror, "MAX_BYTES", 10)
    with pytest.raises(mirror.TooBig):
        mirror.export(warehouse(tmp_path / "w.duckdb"), tmp_path / "out")


def test_each_mirror_appends_its_measured_usage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    warehouse(tmp_path / "warehouse.duckdb")
    runner = CliRunner()
    out = tmp_path / "out"
    assert runner.invoke(cli.app, ["mirror", "export", "--out", str(out)]).exit_code == 0
    (tmp_path / "stored.json").write_text(json.dumps({"dim_study": 1234}))
    for _ in range(2):
        r = runner.invoke(cli.app, ["mirror", "record", "--dir", str(out),
                                    "--stored", str(tmp_path / "stored.json")])  # fmt: skip
        assert r.exit_code == 0, r.stdout
    lines = (tmp_path / "mirror" / "bigquery.jsonl").read_text().splitlines()
    entry = json.loads(lines[-1])
    assert len(lines) == 2 and entry["date"] == dt.datetime.now(dt.UTC).date().isoformat()
    assert entry["tables"]["dim_study"]["stored_bytes"] == 1234
    assert entry["tables"]["fct_news_item"]["stored_bytes"] is None  # not reported: empty
