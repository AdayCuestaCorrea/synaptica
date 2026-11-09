"""Project-wide configuration: paths and environment variables.

Adapted from paleo-atlas ``src/paleo/config.py``. Everything that can change between
environments (local, CI) is read from environment variables with sensible defaults, so the
same ``syn`` commands run unchanged anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    """Repository root (two levels above ``src/synaptica``)."""
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    """Filesystem layout for pipeline data."""

    data: Path

    @property
    def raw(self) -> Path:
        return self.data / "raw"


def get_paths() -> Paths:
    """Data paths, overridable with ``SYN_DATA_DIR`` (used by tests and CI)."""
    data = os.environ.get("SYN_DATA_DIR")
    return Paths(data=Path(data).resolve() if data else project_root() / "data")


@dataclass(frozen=True)
class EnvVar:
    """An environment variable the pipeline reads. Its value is never printed."""

    name: str
    purpose: str
    required: bool = False


# Variables checked by `syn doctor`. Keys are added only when a source or model needs them
# (spike S1 and decision D4), never in advance.
ENV_VARS: tuple[EnvVar, ...] = (EnvVar("SYN_DATA_DIR", "Data directory (default: ./data)"),)
