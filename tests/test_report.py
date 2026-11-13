"""Run log and run report (syn report start / finish / ran-today).

Adapted from paleo-atlas ``tests/test_report.py``: the warehouse totals come in as a plain
``summary`` dict instead of a DuckDB file.
"""

import datetime as dt
import json

import pytest
from typer.testing import CliRunner

from synaptica import cli, report

T0 = dt.datetime(2026, 11, 2, 6, 23, tzinfo=dt.UTC)
runner = CliRunner()


def test_a_run_is_started_finished_and_compared_with_the_previous_one(tmp_path):
    data = tmp_path / "data"
    store = data / "raw" / "pubmed" / "summary" / "41234567"
    store.mkdir(parents=True)
    (store / "2026-11-02.json").write_text("{}")
    target = tmp_path / "run_results.json"
    target.write_text(json.dumps({"results": [
        {"unique_id": "test.synaptica.assert_pubmed_is_fresh", "status": "warn", "failures": 3},
        {"unique_id": "model.synaptica.dim_study", "status": "success", "failures": None},
    ]}))  # fmt: skip

    report.start_run(data, trigger="schedule", changed=True, now=T0 - dt.timedelta(days=1))
    report.finish_run(data, run_results=target, summary={"totals": {"studies": 10}}, now=T0)
    assert not report.ran_today(data, today=T0.date())

    report.start_run(data, trigger="backup", changed=True, now=T0)
    run = report.finish_run(
        data, run_results=target, summary={"totals": {"studies": 12, "news": 4}}, now=T0
    )

    assert report.ran_today(data, today=T0.date())
    assert run["status"] == "ok"  # a dbt warning is not a failure
    assert run["sources_changed"] == {"pubmed/summary": 1}
    assert run["changes_since_previous"] == {"studies": 2}  # "news" had no previous value
    assert run["dbt"]["issues"] == [
        {"status": "warn", "node": "assert_pubmed_is_fresh", "failures": 3}
    ]
    text = report.markdown(run)
    assert "12 (+2)" in text and "| studies | news |" in text and "assert_pubmed_is_fresh" in text
    days = sorted(p.name for p in report.runs_dir(data).glob("*.json"))
    assert days == ["2026-11-01.json", "2026-11-02.json"]


def test_failed_steps_mark_the_run_and_skipped_ones_are_left_out(tmp_path):
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps({"jobs": [{"name": "update", "steps": [
        {"name": "Ingest", "conclusion": "success",
         "started_at": "2026-11-02T06:23:00Z", "completed_at": "2026-11-02T06:24:30Z"},
        {"name": "dbt build", "conclusion": "failure",
         "started_at": "2026-11-02T06:24:30Z", "completed_at": "2026-11-02T06:24:40Z"},
        {"name": "Build the website", "conclusion": "skipped",
         "started_at": "2026-11-02T06:24:40Z", "completed_at": "2026-11-02T06:24:40Z"},
        {"name": "Run report", "conclusion": None, "started_at": "2026-11-02T06:24:41Z",
         "completed_at": None},
    ]}]}))  # fmt: skip
    data = tmp_path / "data"
    report.start_run(data, trigger="manual", changed=False, now=T0)
    run = report.finish_run(data, run_results=tmp_path / "none.json", jobs=jobs)
    assert run["status"] == "failed" and run["summary"] is None and run["dbt"] is None
    assert [(s["name"], s["seconds"]) for s in run["steps"]] == [("Ingest", 90), ("dbt build", 10)]
    assert not report.ran_today(data, today=T0.date())


def test_a_dbt_error_marks_the_run_as_failed(tmp_path):
    target = tmp_path / "run_results.json"
    target.write_text(json.dumps({"results": [
        {"unique_id": "test.synaptica.unique_dim_study_doi.abc1234567", "status": "fail",
         "failures": 2},
    ]}))  # fmt: skip
    report.start_run(tmp_path, trigger="manual", changed=True, now=T0)
    assert report.finish_run(tmp_path, run_results=target, now=T0)["status"] == "failed"


def test_finish_needs_a_started_run_and_triggers_are_checked(tmp_path):
    with pytest.raises(RuntimeError):
        report.finish_run(tmp_path)
    with pytest.raises(ValueError):
        report.start_run(tmp_path, trigger="cron", changed=True)


def test_a_finished_run_cannot_be_finished_twice(tmp_path):
    report.start_run(tmp_path, trigger="local", changed=True, now=T0)
    report.finish_run(tmp_path, now=T0)
    with pytest.raises(RuntimeError):
        report.finish_run(tmp_path, now=T0)


def test_a_step_the_api_still_shows_running_is_kept_as_partial(tmp_path):
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps({"jobs": [{"name": "update", "steps": [
        {"name": "dbt build", "conclusion": "success",
         "started_at": "2026-11-02T06:24:00Z", "completed_at": "2026-11-02T06:24:20Z"},
        {"name": "Build the website", "conclusion": None,
         "started_at": "2026-11-02T06:24:20Z", "completed_at": None},
        {"name": "Run report", "conclusion": None,
         "started_at": "2026-11-02T06:26:20Z", "completed_at": None},
    ]}]}))  # fmt: skip
    now = dt.datetime(2026, 11, 2, 6, 26, 30, tzinfo=dt.UTC)
    steps = report.step_results(jobs, now=now)
    assert steps[1] == {"name": "Build the website", "conclusion": "in_progress", "seconds": 130,
                        "partial": True}  # fmt: skip
    assert [s["name"] for s in steps] == ["dbt build", "Build the website"]  # not the report


def test_dbt_counts_tell_data_tests_from_unit_tests(tmp_path):
    results = tmp_path / "run_results.json"
    results.write_text(json.dumps({"results": [
        {"unique_id": "model.p.m", "status": "success"},
        {"unique_id": "test.p.not_null_x.abc1234567", "status": "pass"},
        {"unique_id": "test.p.lag.abc1234567", "status": "warn", "failures": 3},
        {"unique_id": "unit_test.p.m.u1", "status": "pass"},
    ]}))  # fmt: skip
    out = report.dbt_issues(results)
    assert out["tests"] == {"data": {"pass": 1, "warn": 1}, "unit": {"pass": 1}}
    assert out["issues"] == [{"status": "warn", "node": "lag", "failures": 3}]


def test_cli_start_finish_and_ran_today(tmp_path, monkeypatch):
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    assert runner.invoke(cli.app, ["report", "ran-today"]).exit_code == 1
    started = runner.invoke(cli.app, ["report", "start", "--trigger", "manual", "--no-changed"])
    assert started.exit_code == 0, started.stdout
    finished = runner.invoke(cli.app, ["report", "finish"])
    assert finished.exit_code == 0, finished.stdout
    assert "**Status:** ok · **Sources changed:** no" in finished.stdout
    assert runner.invoke(cli.app, ["report", "ran-today"]).exit_code == 0
    again = runner.invoke(cli.app, ["report", "finish"])
    assert again.exit_code == 1 and "syn report start" in again.output


def test_spanish_titles_of_the_day_and_their_tokens(tmp_path):
    from synaptica.news import titles

    data = tmp_path / "data"
    derived = data / "derived"
    day = T0.date().isoformat()
    rows = {
        "a": {"study_id": "a", "status": "ok", "translated_at": f"{day}T06:40:00+00:00"},
        "b": {"study_id": "b", "status": "failed", "translated_at": f"{day}T06:40:00+00:00"},
        "c": {"study_id": "c", "status": "ok", "translated_at": "2026-11-01T06:40:00+00:00"},
    }
    titles.save_titles(titles.titles_path(derived), rows)
    spent = {"calls": 1, "cached": 0, "prompt_tokens": 900, "completion_tokens": 300}
    titles.record_usage(titles.usage_path(derived), day, spent)
    titles.record_usage(titles.usage_path(derived), day, spent)  # a second batch adds up
    report.start_run(data, trigger="schedule", changed=True, now=T0)
    run = report.finish_run(data, summary={}, now=T0)
    assert run["titles"] == {"translated": 1, "failed": 1, "calls": 2, "cached": 0,
                             "prompt_tokens": 1800, "completion_tokens": 600}  # fmt: skip
    assert "**Spanish titles today:** 1 passed, 1 failed" in report.markdown(run)
    assert "2 calls, 2400 tokens" in report.markdown(run)
