"""Shared HTTP helper for the data sources: retries, a User-Agent and uniform errors."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = "tenora-fx-dashboard/0.1 (data pipeline)"
NO_RETRY_STATUSES = frozenset({400, 401, 403, 404, 410})


class HttpError(RuntimeError):
    """A request failed after retries, or with a status that retrying cannot fix."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def get(
    url: str,
    *,
    session=None,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float | tuple[float, float] = 30,
    retries: int = 3,
    backoff: float = 1.5,
    stream: bool = False,
    label: str | None = None,
) -> requests.Response:
    """GET ``url``, retrying on network errors, 429 and 5xx. Returns only 2xx and 304 responses."""
    sess = session or requests.Session()
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    label = label or url
    last: HttpError | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, params=params, headers=merged_headers, timeout=timeout, stream=stream)
        except requests.RequestException as exc:
            last = HttpError(f"{label}: request failed ({exc})")
        else:
            if resp.status_code < 300 or resp.status_code == 304:
                return resp
            last = HttpError(f"{label}: HTTP {resp.status_code}", status=resp.status_code)
            if resp.status_code in NO_RETRY_STATUSES:
                raise last
        if attempt < retries:
            log.warning("%s (attempt %d/%d), retrying", last, attempt, retries)
            time.sleep(backoff * attempt)
    assert last is not None
    raise last
