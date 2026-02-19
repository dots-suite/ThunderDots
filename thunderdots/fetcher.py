# -*- coding: utf-8 -*-

"""fetcher.py

Fetcher implementations: HttpxFetcher (pure Python) and GoFetcher (via FFI).
"""

from __future__ import annotations

import time
import asyncio
import ctypes
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


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
            base_url=self.endpoint.rstrip("/"),
            timeout=float(self.timeout or 30.0),
            limits=limits,
            headers={"User-Agent": "ThunderDots/0.1 (python)"},
            http2=True,
        )

        self.retries = int(self.retries or 0)
        if self.retries < 0:
            self.retries = 0
        if self.retries > 5:
            self.retries = 5

        self.backoff_ms = int(self.backoff_ms or 200)
        if self.backoff_ms <= 0:
            self.backoff_ms = 200

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
                r = await self._client.get(path, params=params)
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


def _default_lib_name() -> str:
    """Determine the default library name for the ThunderDots Go fetcher based on the operating system."""
    if sys.platform == "darwin":
        return "libthunderdots.dylib"
    if os.name == "nt":
        return "thunderdots.dll"
    return "libthunderdots.so"


def _resolve_lib_path(lib_path: str | None) -> str:
    """Resolve the path to the ThunderDots Go library, either from the provided lib_path or by using the default library name in the native directory relative to this file.

    :param lib_path: Optional path to the ThunderDots Go library. If None, the default library name in the native directory will be used.
    :type lib_path: str | None
    :returns: The resolved absolute path to the ThunderDots Go library.
    :rtype: str
    """
    if lib_path:
        p = Path(lib_path)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parent / p).resolve()
        return str(p)
    return str((Path(__file__).resolve().parent / "native" / _default_lib_name()).resolve())


class GoFetcher(Fetcher):
    """Interface to the ThunderDots Go fetcher via ctypes.
    Go fetcher = only two fast functions:
      - TDGetJSON(cfg_json, path, params_json) -> {"ok":true,"status":200,"json":{...}} or {"ok":false,...}
      - TDGetText(cfg_json, path, params_json) -> {"ok":true,"status":200,"text":"..."} or {"ok":false,...}
    """

    def __init__(
        self,
        lib_path: str | None,
        endpoint: str,
        request_timeout: float,
        total_timeout: float,
        max_inflight: int,
        retries: int,
        backoff_ms: int,
    ) -> None:
        """Initialize the GoFetcher by loading the ThunderDots Go library and setting up the configuration for fetch operations.
        :param lib_path: Optional path to the ThunderDots Go library. If None, the default library name in the native directory will be used.
        :param endpoint:  Base URL of the ThunderDots API endpoint (e.g. "https://api.example.com").
        :param request_timeout: Timeout in seconds for individual HTTP requests made by the Go fetcher.
        :param total_timeout: Total timeout in seconds for the entire fetch operation (0 for no total timeout).
        :param max_inflight: Maximum number of concurrent in-flight requests allowed by the Go fetcher.
        :param retries: Number of retry attempts for failed requests in the Go fetcher.
        :param backoff_ms: Base backoff time in milliseconds for retries in the Go fetcher.
        """
        lib_path = _resolve_lib_path(lib_path)
        if not Path(lib_path).exists():
            raise FileNotFoundError(f"ThunderDots Go library not found: {lib_path}")

        self.lib = ctypes.CDLL(lib_path)

        # exported funcs
        self.lib.TDGetJSON.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self.lib.TDGetJSON.restype = ctypes.c_void_p

        self.lib.TDGetText.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self.lib.TDGetText.restype = ctypes.c_void_p

        # re-use ThunderDotsFree for returned buffers
        self.lib.ThunderDotsFree.argtypes = [ctypes.c_void_p]
        self.lib.ThunderDotsFree.restype = None

        cfg = {
            "endpoint_dts": (endpoint or "").rstrip("/"),
            "request_timeout": float(request_timeout or 20.0),
            "total_timeout": float(total_timeout or 0.0),
            "max_inflight": int(max_inflight or 100),
            "retries": int(retries or 2),
            "backoff_ms": int(backoff_ms or 200),
        }
        self._cfg_b = json.dumps(cfg, ensure_ascii=False).encode("utf-8")

    def _call(self, fn: callable, path: str, params: dict[str, Any] | None) -> bytes:
        """Internal method to call a function from the Go library with the given path and parameters, handling the conversion of inputs and outputs between Python and C types.

        :param fn: The function from the Go library to call (e.g. self.lib.TDGetJSON).
        :type fn: callable
        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: The raw bytes returned by the Go function, decoded from the C string pointer
        :rtype: bytes
        """
        path_b = (path or "").encode("utf-8")
        params_b = json.dumps(params or {}, ensure_ascii=False).encode("utf-8")

        ptr = fn(self._cfg_b, path_b, params_b)
        if not ptr:
            raise RuntimeError("Go fetcher returned NULL pointer")
        try:
            return ctypes.string_at(ptr)
        finally:
            self.lib.ThunderDotsFree(ptr)

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Fetch JSON data from the given path with optional query parameters using the Go fetcher, returning a dictionary if successful or None on failure.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: A dictionary representing the JSON response if the request was successful and the response body
                    could be parsed as JSON, otherwise None. The Go fetcher is expected to return a JSON string with the format {"ok":true,"status":200,"json":{...}} on success, or {"ok":false,...} on failure.
        :rtype: dict[str, Any] | None
        """
        b = await asyncio.to_thread(self._call, self.lib.TDGetJSON, path, params)
        s = b.decode("utf-8", errors="replace")
        env = json.loads(s)

        # envelope must be {"ok":bool,...}
        if not isinstance(env, dict):
            return None
        if env.get("ok") is not True:
            return None

        payload = env.get("json")
        if isinstance(payload, dict):
            return payload
        return None

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Fetch text data from the given path with optional query parameters using the Go fetcher, returning the text content if successful or raising an exception on failure.

        :param path: The API path to fetch (e.g. "/collection").
        :type path: str
        :param params: Optional dictionary of query parameters to include in the request.
        :type params: dict[str, Any] | None
        :returns: The text content of the response if the request was successful, otherwise raises an
        exception. The Go fetcher is expected to return a JSON string with the format {"ok":true,"status":200,"text":"..."} on success, or {"ok":false,...} on failure.
        :rtype: str
        """
        b = await asyncio.to_thread(self._call, self.lib.TDGetText, path, params)
        s = b.decode("utf-8", errors="replace")
        env = json.loads(s)

        if not isinstance(env, dict):
            raise RuntimeError("Go fetch error (bad envelope)")
        if env.get("ok") is not True:
            raise RuntimeError(env.get("error") or "Go fetch error")

        return str(env.get("text") or "")
