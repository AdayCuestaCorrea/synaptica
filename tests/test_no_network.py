import socket

import pytest


def test_network_is_blocked():
    with socket.socket() as s, pytest.raises(RuntimeError, match="must not use the network"):
        s.connect(("192.0.2.1", 80))  # TEST-NET-1, never routed
