# -*- coding: utf-8 -*-

"""fetcher.py

Fetcher implementations: HttpxFetcher (pure Python) and GoFetcher (via FFI).
"""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


def _http2_available() -> bool:
    """Return True when httpx can enable HTTP/2 support in the current environment."""
    try:
        import h2  # noqa: F401
    except ImportError:
        return False
    return True


class Fetcher:
    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Fetch JSON data from the given path with optional query parameters.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: A dictionary representing the JSON response, or None if the request failed or returned
                    a non-200 status code.
        :rtype: dict[str, Any] | None
        """
        raise NotImplementedError

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Fetch text data from the given path with optional query parameters.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: The text content of the response if the request was successful (status code 200),
                    otherwise raises an exception.
        :rtype: str
        """
        raise NotImplementedError

    async def aclose(self) -> None:
        """Close any resources held by the fetcher (e.g. HTTP client sessions)."""
        return


def _is_retry_status(code: int) -> bool:
    """Determine if the HTTP status code is one that should trigger a retry.

    :param code: The HTTP status code to check.
    :type code: int
    :returns: True if the status code indicates a retryable error (e.g.
    429 or 5xx), False otherwise.
    :rtype: bool
    """
    return code == 429 or (500 <= code <= 599)


async def _sleep_backoff(base_ms: int, attempt: int) -> None:
    """Exponential backoff sleep with jitter.
    description: Sleep for an exponentially increasing amount of time based on the retry attempt number, with added jitter to avoid thundering herd problems.

    :param base_ms: The base backoff time in milliseconds (default 200ms).
    :type base_ms: int
    :param attempt: The current retry attempt number (0 for first retry).
    :type attempt: int
    :returns: None (sleeps for the calculated backoff time).
    :rtype: None
    """
    base = (base_ms or 200) / 1000.0
    d = base * (2 ** max(0, attempt))
    jitter = (time.time_ns() % 50) / 1000.0
    await asyncio.sleep(d + jitter)


@dataclass
class HttpxFetcher(Fetcher):
    """HTTP fetcher implementation using httpx.AsyncClient, with retries and backoff."""

    endpoint: str
    timeout: float
    concurrency: int
    retries: int = 2
    backoff_ms: int = 200
    stats: Any | None = None

    def __post_init__(self) -> None:
        """Initialize the httpx.AsyncClient with appropriate limits and timeouts based on the configuration."""
        max_conn = max(1, min(int(self.concurrency or 20), 200))
        limits = httpx.Limits(
            max_connections=max_conn,
            max_keepalive_connections=max(5, max_conn // 2),
            keepalive_expiry=30.0,
        )
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            http2=_http2_available(),
            follow_redirects=True,
        )

        self.retries = int(self.retries or 0)
        if self.retries < 0:
            self.retries = 0
        if self.retries > 5:
            self.retries = 5

        self.backoff_ms = int(self.backoff_ms or 200)
        if self.backoff_ms <= 0:
            self.backoff_ms = 200

    def _build_url(self, path: str) -> str:
        """Build an absolute URL from the DTS endpoint and a relative or absolute path."""
        if path.startswith(("http://", "https://")):
            return path

        endpoint = self.endpoint.rstrip("/")
        path = path.lstrip("/")
        return f"{endpoint}/{path}"

    def _bump(self, name: str, n: int = 1) -> None:
        """Safely increment a named statistic by n, if stats is available.

        :param name: The name of the statistic to increment (e.g. "requests_total").
        :type name: str
        :param n: The amount to increment the statistic by (default 1).
        :type n: int
        :returns: None (updates the stats object if available).
        :rtype: None
        """
        s = self.stats
        if s is None:
            return
        try:
            setattr(s, name, getattr(s, name, 0) + n)
        except Exception:
            pass

    async def _get_raw(self, path: str, params: dict[str, Any] | None) -> httpx.Response:
        """Internal method to perform the HTTP GET request with retries and backoff. Returns the raw httpx.Response object if successful, or raises an exception on failure after exhausting retries.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: The httpx.Response object if the request was successful (status code 200
        and non-empty body), otherwise raises an exception.
        :rtype: httpx.Response
        """
        last_exc: Exception | None = None

        for attempt in range(self.retries + 1):
            self._bump("requests_total", 1)

            try:
                url = self._build_url(path)
                r = await self._client.get(url, params=params)
            except httpx.TimeoutException as e:
                last_exc = e
                self._bump("http_errors", 1)
                self._bump("timeouts", 1)
                if attempt < self.retries:
                    await _sleep_backoff(self.backoff_ms, attempt)
                    continue
                raise
            except Exception as e:
                last_exc = e
                self._bump("http_errors", 1)
                if attempt < self.retries:
                    await _sleep_backoff(self.backoff_ms, attempt)
                    continue
                raise

            code = r.status_code

            # non-2xx
            if code < 200 or code >= 300:
                self._bump("http_errors", 1)
                if code == 500:
                    self._bump("http_500", 1)

                if _is_retry_status(code) and attempt < self.retries:
                    await _sleep_backoff(self.backoff_ms, attempt)
                    continue

                # raise for non-retryable status or if retries exhausted
                r.raise_for_status()

            # empty body
            if not r.content:
                self._bump("http_errors", 1)
                if attempt < self.retries:
                    await _sleep_backoff(self.backoff_ms, attempt)
                    continue
                raise RuntimeError("empty body")

            return r

        # retries exhausted
        if last_exc:
            raise last_exc
        raise RuntimeError("http fetch failed")

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Fetch JSON data from the given path with optional query parameters, returning a dictionary if successful or None on failure.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: A dictionary representing the JSON response if the request was successful and the response body
                    could be parsed as JSON, otherwise None.
        :rtype: dict[str, Any] | None
        """
        try:
            r = await self._get_raw(path, params)
        except Exception:
            return None

        try:
            data = r.json()
        except Exception:
            self._bump("http_errors", 1)
            return None

        return data if isinstance(data, dict) else None

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Fetch text data from the given path with optional query parameters, returning the text content if successful or raising an exception on failure.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: The text content of the response if the request was successful (status code
        200 and non-empty body), otherwise raises an exception.
        :rtype: str
        """
        r = await self._get_raw(path, params)
        return r.text

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient session to free resources."""
        await self._client.aclose()
