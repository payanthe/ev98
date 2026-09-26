import time

import httpx


class UpstreamError(Exception):
    def __init__(self, source: str, message: str):
        super().__init__(message)
        self.source = source
        self.message = message


def request_json(client: httpx.Client, method: str, url: str, *, source: str, retries: int = 3, **kwargs):
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise UpstreamError(source, f"HTTP {response.status_code} from {url}")
            if response.status_code >= 400:
                raise UpstreamError(source, f"HTTP {response.status_code}: {response.text[:300]}")
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        except UpstreamError as exc:
            last = exc
            if exc.message.startswith("HTTP 4") and "HTTP 429" not in exc.message:
                raise
            time.sleep(0.35 * (2**attempt))
        except httpx.HTTPError as exc:
            last = exc
            time.sleep(0.35 * (2**attempt))
    raise UpstreamError(source, f"upstream failed: {last}")
