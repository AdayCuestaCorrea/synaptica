"""Polite HTTP client shared by every ingestion step.

Copied and adapted from paleo-atlas ``src/paleo/http.py`` (same author, AGPL in both;
decision D2). Rules (CLAUDE.md, "Red y fuentes"): identifiable User-Agent with a contact,
requests in series (never in parallel), gzip, and retries with exponential backoff on
throttling or transient server errors. MediaWiki's ``maxlag`` errors are retried as well.

Added here: :class:`Throttle`, for sources that publish a requests-per-second limit
(PubMed: 3/s, or 10/s with an API key).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from synaptica.config import USER_AGENT

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class Throttle:
    """Keeps at least ``1 / per_second`` seconds between calls to :meth:`wait`.

    ``clock`` and ``sleep`` are injectable so tests check the pacing without waiting."""

    def __init__(
        self,
        per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = 1.0 / per_second
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self._last + self.interval - self.clock()
            if remaining > 0:
                self.sleep(remaining)
        self._last = self.clock()


class HttpError(RuntimeError):
    """Raised when a request fails (after every retry, for transient errors)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Client with our identity. ``transport`` lets tests inject a mock."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        transport=transport,
    )


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    read: Callable[[httpx.Response], tuple[bool, Any, str]],
    *,
    params: Mapping[str, Any] | None = None,
    json: Any = None,
    data: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    retries: int = 5,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Send a request and return what ``read`` makes of the response, retrying
    transient failures: HTTP 429/5xx, network errors and whatever ``read`` reports as
    not ready (``(False, None, reason)``). ``Retry-After`` is honoured. Client errors
    (4xx) are raised at once with the start of the response body, for debugging."""
    last_error = "unknown error"
    for attempt in range(retries + 1):
        wait = backoff * 2**attempt
        try:
            response = client.request(
                method, url, params=params, json=json, data=data, headers=headers,
                timeout=httpx.USE_CLIENT_DEFAULT if timeout is None else timeout,
            )  # fmt: skip
        except httpx.TransportError as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code in RETRY_STATUS:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if (retry_after := _retry_after(response)) is not None:
                    wait = max(wait, retry_after)
            elif response.is_error:
                raise HttpError(
                    f"HTTP {response.status_code} for {response.url}: {response.text[:300]}",
                    response.status_code,
                )
            else:
                ok, value, reason = read(response)
                if ok:
                    return value
                last_error = reason
        if attempt < retries:
            log.warning("Retrying %s in %.0fs (%s)", url, wait, last_error)
            sleep(wait)
    raise HttpError(f"Giving up on {url} after {retries + 1} attempts: {last_error}")


def _read_json(response: httpx.Response) -> tuple[bool, Any, str]:
    body = response.json()
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("code") == "maxlag":
        return False, None, "MediaWiki maxlag"
    if error:
        raise HttpError(f"API error: {error}")
    return True, body, ""


def request_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    """Send a request and return its JSON body (see :func:`_request`); MediaWiki
    ``maxlag`` errors are retried, other API errors raised."""
    return _request(client, method, url, _read_json, **kwargs)


def get_text(client: httpx.Client, url: str, **kwargs: Any) -> str:
    """GET ``url`` and return its body as text (feeds), with the same retries."""
    return _request(client, "GET", url, lambda r: (True, r.text, ""), **kwargs)


def get_json(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """GET ``url`` and return its JSON body (see :func:`request_json`)."""
    return request_json(client, "GET", url, params=params, **kwargs)


def post_json(client: httpx.Client, url: str, payload: Any, **kwargs: Any) -> dict[str, Any]:
    """POST ``payload`` as JSON and return the JSON body (see :func:`request_json`)."""
    return request_json(client, "POST", url, json=payload, **kwargs)
