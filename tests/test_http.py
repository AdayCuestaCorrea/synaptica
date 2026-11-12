"""Tests for the polite HTTP client, with ``httpx.MockTransport`` (never the network)."""

import httpx
import pytest

from synaptica.config import USER_AGENT
from synaptica.http import HttpError, get_json, get_text, make_client, post_json

URL = "https://api.example.org/items"


def client_with(*responses):
    """Client whose transport returns ``responses`` in order (callables raise or answer)."""
    seen = []
    queue = list(responses)

    def handler(request):
        seen.append(request)
        item = queue.pop(0)
        return item(request) if callable(item) else item

    return make_client(transport=httpx.MockTransport(handler)), seen


def test_requests_carry_the_user_agent_with_a_contact():
    client, seen = client_with(httpx.Response(200, json={"ok": True}))
    assert get_json(client, URL) == {"ok": True}
    assert seen[0].headers["User-Agent"] == USER_AGENT
    assert "@" in USER_AGENT  # CLAUDE.md: requests are identified with a contact


def test_transient_errors_are_retried_with_exponential_backoff():
    client, seen = client_with(
        httpx.Response(503), httpx.Response(429), httpx.Response(200, json={"n": 1})
    )
    waits = []
    assert get_json(client, URL, sleep=waits.append) == {"n": 1}
    assert len(seen) == 3
    assert waits == [2.0, 4.0]


def test_retry_after_is_honoured_when_longer_than_the_backoff():
    client, _ = client_with(
        httpx.Response(429, headers={"Retry-After": "30"}), httpx.Response(200, json={})
    )
    waits = []
    get_json(client, URL, sleep=waits.append)
    assert waits == [30.0]


def test_network_errors_are_retried():
    def fail(request):
        raise httpx.ConnectError("boom", request=request)

    client, _ = client_with(fail, httpx.Response(200, text="<rss/>"))
    assert get_text(client, URL, sleep=lambda _: None) == "<rss/>"


def test_client_errors_are_raised_at_once():
    client, seen = client_with(httpx.Response(404, text="not found"))
    with pytest.raises(HttpError) as excinfo:
        get_json(client, URL, sleep=lambda _: None)
    assert excinfo.value.status_code == 404
    assert len(seen) == 1


def test_gives_up_after_the_last_retry():
    client, seen = client_with(*[httpx.Response(500)] * 3)
    with pytest.raises(HttpError, match="after 3 attempts"):
        get_json(client, URL, retries=2, sleep=lambda _: None)
    assert len(seen) == 3


def test_mediawiki_maxlag_is_retried_and_other_api_errors_raised():
    client, _ = client_with(
        httpx.Response(200, json={"error": {"code": "maxlag"}}), httpx.Response(200, json={})
    )
    assert get_json(client, URL, sleep=lambda _: None) == {}
    client, _ = client_with(httpx.Response(200, json={"error": {"code": "badquery"}}))
    with pytest.raises(HttpError, match="API error"):
        get_json(client, URL, sleep=lambda _: None)


def test_post_sends_json():
    client, seen = client_with(httpx.Response(200, json={"id": 7}))
    assert post_json(client, URL, {"q": "hippocampus"}) == {"id": 7}
    assert seen[0].method == "POST"
    assert seen[0].read() == b'{"q":"hippocampus"}'
