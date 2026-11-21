"""HTTP helper shared by connectors: retries on rate limits / server errors, clear auth errors."""

import time
from collections.abc import Callable

import httpx

from .base import ConnectorError


def request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    source: str,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> httpx.Response:
    for attempt in range(max_retries + 1):
        response = client.request(method, url, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == max_retries:
                break
            sleep(_retry_delay(response, attempt))
            continue
        if response.status_code in (401, 403):
            raise ConnectorError(
                f"{source}: access denied ({response.status_code}) for {url}. "
                "Check the token and that it has access to this resource."
            )
        if response.status_code == 404:
            raise ConnectorError(f"{source}: not found (404) for {url}.")
        break
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ConnectorError(f"{source}: request failed ({response.status_code}) for {url}") from exc
    return response


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        body = response.json()
        if isinstance(body, dict) and "retry_after" in body:  # Discord
            return float(body["retry_after"])
    except ValueError:
        pass
    return float(2**attempt)
