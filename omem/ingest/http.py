"""Minimal HTTP transport for connectors. Stdlib urllib; injectable in tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")


class UrllibTransport:
    """Default transport. No extra dependencies."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def _open(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        data: Optional[bytes] = None,
    ) -> bytes:
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{qs}" if "?" not in url else f"{url}&{qs}"
        body = data
        hdrs = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise HttpError(exc.code, url, raw) from exc

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        raw = self._open(url, method="GET", headers=headers, params=params)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def post_json(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
    ) -> Any:
        raw = self._open(url, method="POST", headers=headers, json_body=json_body)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def get_text(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        raw = self._open(url, method="GET", headers=headers, params=params)
        return raw.decode("utf-8", errors="replace")

    def get_bytes(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        return self._open(url, method="GET", headers=headers, params=params)


class StaticTransport:
    """Test double: map URL prefixes to JSON/text/bytes responses."""

    def __init__(
        self,
        json_routes: Optional[Dict[str, Any]] = None,
        text_routes: Optional[Dict[str, str]] = None,
        bytes_routes: Optional[Dict[str, bytes]] = None,
        post_routes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.json_routes = json_routes or {}
        self.text_routes = text_routes or {}
        self.bytes_routes = bytes_routes or {}
        self.post_routes = post_routes or {}

    def _lookup(self, table: Dict[str, Any], url: str) -> Any:
        if url in table:
            return table[url]
        for prefix, val in table.items():
            if url.startswith(prefix):
                return val
        raise HttpError(404, url, "no static route")

    def get_json(self, url: str, **_kwargs: Any) -> Any:
        return self._lookup(self.json_routes, url)

    def post_json(self, url: str, **_kwargs: Any) -> Any:
        return self._lookup(self.post_routes or self.json_routes, url)

    def get_text(self, url: str, **_kwargs: Any) -> str:
        if self.text_routes:
            return self._lookup(self.text_routes, url)
        val = self._lookup({**self.json_routes, **self.text_routes}, url)
        return val if isinstance(val, str) else json.dumps(val)

    def get_bytes(self, url: str, **_kwargs: Any) -> bytes:
        if self.bytes_routes:
            return self._lookup(self.bytes_routes, url)
        return self.get_text(url).encode("utf-8")
