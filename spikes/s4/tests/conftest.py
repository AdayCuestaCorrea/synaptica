"""Spike S4 tests: same no-network guard as tests/conftest.py (copied, not imported).

Run from the repo root (the regular CI does not install the spike group):

    uv run --group spike-s4 pytest spikes/s4/tests
"""

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))  # the spike modules

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "review"


class NetworkBlockedError(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError(f"tests must not use the network (tried {address!r})")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
