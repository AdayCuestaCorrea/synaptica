"""Command-line entry point: ``syn <command>``.

Adapted from paleo-atlas ``src/paleo/cli.py``. Every pipeline step is a command with a
reliable exit code, so GitHub Actions (or any orchestrator) calls exactly the same thing.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from synaptica import __version__, config

app = typer.Typer(help="SYNAPTICA data pipeline.", no_args_is_help=True)
report_app = typer.Typer(help="Run log in data/runs/ (one record per pipeline run).")
app.add_typer(report_app, name="report")
ingest_app = typer.Typer(help="Download new items from each source to data/raw/.")
app.add_typer(ingest_app, name="ingest")

REQUIRED_PYTHON = (3, 14)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"syn {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_checks() -> list[Check]:
    """Environment checks for `syn doctor`. No network access."""
    py = sys.version_info[:2]
    checks = [
        Check(
            "Python",
            py == REQUIRED_PYTHON,
            f"{py[0]}.{py[1]} (needs {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]})",
        ),
        Check(
            "git",
            shutil.which("git") is not None,
            "on PATH" if shutil.which("git") else "not found",
        ),
    ]
    data = config.get_paths().data
    checks.append(
        Check(
            "Data directory",
            True,
            f"{data} ({'exists' if data.is_dir() else 'not created yet'})",
            required=False,
        )
    )
    for var in config.ENV_VARS:
        is_set = bool(os.environ.get(var.name))
        checks.append(
            Check(
                var.name,
                is_set or not var.required,
                f"{'set' if is_set else 'not set'} · {var.purpose}",
                required=var.required,
            )
        )
    return checks


@app.command()
def doctor() -> None:
    """Check the environment and the variables the pipeline needs (exit 1 on a failure)."""
    checks = run_checks()
    for c in checks:
        mark = "✓" if c.ok else "✗"
        note = "" if c.required else " (optional)"
        typer.echo(f"{mark} {c.name}{note}: {c.detail}")
    if any(c.required and not c.ok for c in checks):
        raise typer.Exit(code=1)


@report_app.command("start")
def report_start(
    trigger: Annotated[str, typer.Option(help="schedule, backup, manual or local.")] = "local",
    changed: Annotated[bool, typer.Option(help="Change detection found something new.")] = True,
) -> None:
    """Record that a run started and what change detection found (data/runs/)."""
    from synaptica import report

    try:
        run = report.start_run(config.get_paths().data, trigger=trigger, changed=changed)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--trigger") from exc
    typer.echo(f"Run started {run['started_at']} ({trigger}, changed={changed})")


@report_app.command("finish")
def report_finish(
    jobs: Annotated[
        Path | None, typer.Option(help="GitHub API dump of this run's jobs (step durations).")
    ] = None,
) -> None:
    """Complete the current run record and print the report as Markdown."""
    from synaptica import report

    try:
        run = report.finish_run(
            config.get_paths().data,
            run_results=config.project_root() / "dbt" / "target" / "run_results.json",
            jobs=jobs,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report.markdown(run))


@report_app.command("ran-today")
def report_ran_today() -> None:
    """Exit 0 if a run already finished without failures today (UTC), 1 otherwise."""
    from synaptica import report

    raise typer.Exit(0 if report.ran_today(config.get_paths().data) else 1)


@ingest_app.command("pubmed")
def ingest_pubmed(
    days: Annotated[
        int, typer.Option(min=1, max=30, help="Records that entered PubMed in the last N days.")
    ] = 3,
) -> None:
    """New neuroscience records from PubMed: metadata, MeSH; abstracts only to the cache."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import pubmed

    try:
        with make_client() as client:
            result = pubmed.ingest(client, days=days)
    except HttpError as exc:
        typer.echo(f"PubMed failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"PubMed: {result.found} records in {days} day(s); "
        f"{result.summaries_requested} new summaries ({result.summaries_new_versions} stored); "
        f"{result.medline_requested} MEDLINE records checked "
        f"({result.medline_new_versions} new versions, {result.abstracts_cached} abstracts cached)"
    )


@ingest_app.command("crossref")
def ingest_crossref(
    days: Annotated[
        int, typer.Option(min=1, max=60, help="Notices deposited in the last N days.")
    ] = 3,
) -> None:
    """Retraction, correction and other notices from Crossref, for the study signals."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import crossref

    try:
        with make_client() as client:
            result = crossref.ingest(client, days=days)
    except HttpError as exc:
        typer.echo(f"Crossref failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    listed = ", ".join(f"{k} {v}" for k, v in result.notices.items())
    typer.echo(f"Crossref: {listed}; {result.new_versions} new or changed notices stored")
