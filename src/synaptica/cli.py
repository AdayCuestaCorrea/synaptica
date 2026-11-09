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
from typing import Annotated

import typer

from synaptica import __version__, config

app = typer.Typer(help="SYNAPTICA data pipeline.", no_args_is_help=True)

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
