"""Tests never use the network (CLAUDE.md): any internet socket connection fails loudly."""

import socket

import pytest


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
