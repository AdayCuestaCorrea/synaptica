"""Run log and run report (SCOPE §6: "Cada ejecución deja un informe en la rama data").

Copied and adapted from paleo-atlas ``src/paleo/report.py`` (same author, AGPL in both;
decision D2). The generic part is kept: the run record, change counts from the raw store,
GitHub step durations, dbt warnings and LLM tokens. Paleo's warehouse totals (taxa, PBDB,
images) and Wikipedia revisions are dropped; SYNAPTICA's totals arrive with the first marts
(plan, step 10) through ``finish_run(summary=...)``, so this module does not need DuckDB.

Every pipeline run, including the ones that find nothing new, leaves a record in
``$SYN_DATA_DIR/runs/<YYYY-MM-DD>.json`` (a JSON array, one item per run):

* ``start_run`` writes it right after change detection, so dbt (freshness tests) and the
  website ("Estado de los datos") already see today's check;
* ``finish_run`` completes it at the end with the step results and durations, new raw
  versions per source, warehouse totals and their change since the previous run, dbt
  warnings and errors, and the LLM tokens used that day.

The record is committed to the ``data`` branch: a daily proof that the schedule works, and
the activity GitHub needs to keep scheduled workflows enabled. The file is a log, so each
``start`` appends a run on purpose; ``finish`` completes the last running one and fails if
there is none, so it cannot complete the same run twice.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from synaptica.store import _atomic_write

TRIGGERS = ("schedule", "backup", "manual", "local")
FAILED = ("error", "fail", "runtime error")


def runs_dir(data: Path) -> Path:
    return data / "runs"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _iso(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _read(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _write(path: Path, runs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(runs, ensure_ascii=False, indent=1) + "\n")


def all_runs(data: Path) -> list[dict[str, Any]]:
    """Every recorded run, oldest first."""
    out: list[dict[str, Any]] = []
    for path in sorted(runs_dir(data).glob("*.json")):
        out += _read(path)
    return sorted(out, key=lambda r: r["started_at"])


def start_run(
    data: Path, *, trigger: str, changed: bool, now: dt.datetime | None = None
) -> dict[str, Any]:
    """Append a ``running`` record for a run that has just passed change detection."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}")
    moment = now or _now()
    run = {"started_at": _iso(moment), "trigger": trigger, "changed": changed, "status": "running"}
    path = runs_dir(data) / f"{moment.date().isoformat()}.json"
    _write(path, [*_read(path), run])
    return run


def ran_today(data: Path, today: dt.date | None = None) -> bool:
    """True when a run finished without failures today (the backup schedule then skips)."""
    today = today or _now().date()
    return any(r.get("status") == "ok" for r in _read(runs_dir(data) / f"{today}.json"))


# --- what the report measures -------------------------------------------------------


def changed_sources(data: Path, day: dt.date) -> dict[str, int]:
    """New raw versions written on ``day``, per source/kind (synaptica.store layout)."""
    counts: dict[str, int] = {}
    for path in (data / "raw").glob(f"*/*/*/{day}.json"):
        kind = f"{path.parents[2].name}/{path.parents[1].name}"
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def dbt_issues(run_results: Path | None) -> dict[str, Any] | None:
    """Warnings and failures of the last dbt build (target/run_results.json)."""
    if run_results is None or not run_results.exists():
        return None
    results = json.loads(run_results.read_text(encoding="utf-8")).get("results", [])
    counts: dict[str, int] = {}
    tests: dict[str, dict[str, int]] = {"data": {}, "unit": {}}  # data tests vs unit tests
    issues = []
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        kind = {"test": "data", "unit_test": "unit"}.get(r["unique_id"].split(".", 1)[0])
        if kind:
            tests[kind][r["status"]] = tests[kind].get(r["status"], 0) + 1
        if r["status"] in ("warn", *FAILED):
            name = re.sub(r"\.[0-9a-f]{10}$", "", r["unique_id"].split(".", 2)[-1])
            issues.append({"status": r["status"], "node": name, "failures": r.get("failures")})
    return {
        "counts": dict(sorted(counts.items())),
        "tests": {k: dict(sorted(v.items())) for k, v in tests.items()},
        "issues": issues,
    }


REPORT_STEP = "Run report"  # the step that calls `syn report finish`: never finished yet


def step_results(
    jobs: Path, job_name: str = "update", now: dt.datetime | None = None
) -> list[dict[str, Any]]:
    """Name, conclusion and seconds of the steps of this job (GitHub API dump).

    The API can still show a step that has just ended as in progress: such a step
    (started, not completed, not the report itself) is kept with its time up to ``now``
    and ``partial: true``, instead of being lost."""
    if not jobs.exists():
        return []
    doc = json.loads(jobs.read_text(encoding="utf-8") or "{}")
    job = next((j for j in doc.get("jobs", []) if j.get("name") == job_name), None)
    out = []
    for step in (job or {}).get("steps", []):
        if step.get("conclusion") == "skipped" or not step.get("started_at"):
            continue
        started = dt.datetime.fromisoformat(step["started_at"])
        if step.get("completed_at"):
            completed = dt.datetime.fromisoformat(step["completed_at"])
            out.append({"name": step["name"], "conclusion": step["conclusion"],
                        "seconds": int((completed - started).total_seconds())})  # fmt: skip
        elif step["name"] != REPORT_STEP and now is not None:
            out.append({"name": step["name"], "conclusion": "in_progress",
                        "seconds": max(0, int((now - started).total_seconds())),
                        "partial": True})  # fmt: skip
    return out


def llm_usage(data: Path, day: dt.date) -> dict[str, Any]:
    """Tokens per model on ``day``, as the LLM client logs them (from plan step 16)."""
    path = data / "cache" / "llm_usage.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get(day.isoformat(), {})


def _changes(now: dict[str, Any] | None, before: dict[str, Any] | None) -> dict[str, int]:
    if not now or not before:
        return {}
    old = before.get("totals", {})
    return {k: v - old[k] for k, v in now.get("totals", {}).items() if k in old and v != old[k]}


def finish_run(
    data: Path,
    *,
    run_results: Path | None = None,
    jobs: Path | None = None,
    summary: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Complete the run started last with everything the report measures.

    ``summary`` holds the warehouse figures (``{"totals": {name: count}, ...}``); it is
    ``None`` until the first marts exist."""
    files = sorted(runs_dir(data).glob("*.json"))
    path = next(
        (p for p in reversed(files) if any(r["status"] == "running" for r in _read(p))), None
    )
    if path is None:
        raise RuntimeError("no running run to finish: call `syn report start` first")
    runs = _read(path)
    index = max(i for i, r in enumerate(runs) if r["status"] == "running")
    run = runs[index]
    moment = now or _now()
    day = dt.date.fromisoformat(run["started_at"][:10])
    previous = next(
        (r for r in reversed(all_runs(data))
         if r.get("summary") and r["started_at"] < run["started_at"]),
        None,
    )  # fmt: skip
    steps = step_results(jobs, now=moment) if jobs else []
    dbt = dbt_issues(run_results)
    failed = any(s["conclusion"] == "failure" for s in steps) or bool(
        dbt and any(i["status"] in FAILED for i in dbt["issues"])
    )
    run.update(
        {
            "finished_at": _iso(moment),
            "status": "failed" if failed else "ok",
            "steps": steps,
            "sources_changed": changed_sources(data, day),
            "summary": summary,
            "changes_since_previous": _changes(summary, previous and previous.get("summary")),
            "dbt": dbt,
            "llm_tokens": llm_usage(data, day),
        }
    )
    runs[index] = run
    _write(path, runs)
    return run


# --- Markdown for $GITHUB_STEP_SUMMARY -----------------------------------------------


def markdown(run: dict[str, Any]) -> str:
    """The run as Markdown, for the Actions job summary (and the terminal)."""
    lines = [
        f"## SYNAPTICA — run {run['started_at']} ({run['trigger']})",
        "",
        f"**Status:** {run['status']} · **Sources changed:** {'yes' if run['changed'] else 'no'}",
        "",
    ]
    if run.get("sources_changed"):
        lines.append(
            "New raw versions: " + ", ".join(f"{k} {v}" for k, v in run["sources_changed"].items())
        )
    totals = (run.get("summary") or {}).get("totals")
    if totals:
        changes = run.get("changes_since_previous") or {}
        cells = [
            f"{v}" + (f" ({changes[k]:+d})" if changes.get(k) else "") for k, v in totals.items()
        ]
        lines += [
            "",
            "| " + " | ".join(totals) + " |",
            "|" + "---|" * len(totals),
            "| " + " | ".join(cells) + " |",
        ]
    dbt = run.get("dbt")
    if dbt:
        lines += ["", "**dbt:** " + ", ".join(f"{k} {v}" for k, v in dbt["counts"].items())]
        lines += [f"- {i['status']}: `{i['node']}` ({i['failures']})" for i in dbt["issues"][:20]]
    if run.get("llm_tokens"):
        lines.append(
            "**LLM tokens today:** "
            + ", ".join(f"{m} {u.get('tokens', 0)}" for m, u in run["llm_tokens"].items())
        )
    if run.get("steps"):
        lines += ["", "| Step | Result | Seconds |", "|---|---|---|"]
        lines += [f"| {s['name']} | {s['conclusion']} | {s['seconds']} |" for s in run["steps"]]
    return "\n".join(lines) + "\n"
