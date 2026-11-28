import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    InvalidProviderResponse,
    RateLimitError,
    RequestBudgetExceeded,
)


class BaseHTTPClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30,
        max_retries: int = 3,
        backoff_seconds: float = 1,
        max_request_budget: int = 1000,
        api_key: str | None = None,
        api_key_header: str = "X-API-Key",
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_request_budget = max_request_budget
        self.requests_used = 0

        headers = {"Accept": "application/json"}
        if api_key:
            headers[api_key_header] = api_key

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def requests_remaining(self) -> int:
        return max(0, self.max_request_budget - self.requests_used)

    def _consume_request_budget(self) -> None:
        if self.requests_used >= self.max_request_budget:
            raise RequestBudgetExceeded(
                "External API request budget has been exhausted"
            )
        self.requests_used += 1

    def _validate_origin(self, url: httpx.URL) -> None:
        base_url = httpx.URL(self.base_url)
        if (
            url.scheme != base_url.scheme
            or url.host != base_url.host
            or url.port != base_url.port
            or url.username
            or url.password
        ):
            raise InvalidProviderResponse(
                "External API URL points to an untrusted origin"
            )

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0, float(retry_after))
                except ValueError:
                    try:
                        retry_date = parsedate_to_datetime(retry_after)
                    except (TypeError, ValueError):
                        retry_date = None
                    if retry_date is not None:
                        return max(
                            0,
                            retry_date.timestamp() - time.time(),
                        )

        return self.backoff_seconds * (2 ** attempt)

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_error: ExternalServiceError | None = None

        for attempt in range(self.max_retries + 1):
            request_url = self._client.build_request(
                "GET",
                path,
                params=params,
            ).url
            self._validate_origin(request_url)
            self._consume_request_budget()

            try:
                response = self._client.get(path, params=params)
            except httpx.TimeoutException:
                last_error = ExternalServiceError(
                    "External API request timed out"
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self._retry_delay(None, attempt))
                continue
            except httpx.RequestError:
                last_error = ExternalServiceError(
                    "External API request failed due to a network error"
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self._retry_delay(None, attempt))
                continue

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    "External API authentication failed"
                )

            if response.status_code == 429:
                last_error = RateLimitError(
                    "External API rate limit was reached"
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self._retry_delay(response, attempt))
                continue

            if response.status_code in (408, 500, 502, 503, 504):
                last_error = ExternalServiceError(
                    f"External API returned temporary HTTP status "
                    f"{response.status_code}"
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self._retry_delay(response, attempt))
                continue

            if response.is_error:
                raise ExternalServiceError(
                    f"External API returned HTTP status {response.status_code}"
                )

            try:
                return response.json()
            except ValueError:
                raise InvalidProviderResponse(
                    "External API returned a non-JSON response"
                )

        if last_error is not None:
            raise last_error
        raise ExternalServiceError("External API request failed")

    def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        data_key: str = "results",
        next_key: str = "next",
        max_pages: int | None = None,
    ) -> list[Any]:
        page_params = dict(params or {})
        records: list[Any] = []
        pages = 0
        requested_urls: set[str] = set()

        while True:
            if max_pages is not None and pages >= max_pages:
                break

            request_url = str(
                self._client.build_request(
                    "GET",
                    path,
                    params=page_params,
                ).url
            )
            if request_url in requested_urls:
                raise InvalidProviderResponse(
                    "External API pagination repeated a page URL"
                )
            requested_urls.add(request_url)

            payload = self.get(path, page_params)
            if not isinstance(payload, dict):
                raise InvalidProviderResponse(
                    "External API paginated response must be a JSON object"
                )

            page_records = payload.get(data_key)
            if not isinstance(page_records, list):
                raise InvalidProviderResponse(
                    f"External API response field '{data_key}' must be a list"
                )

            records.extend(page_records)
            pages += 1

            meta = payload.get("meta")
            next_url = None

            if isinstance(meta, dict):
                next_url = meta.get(next_key)
            elif isinstance(payload.get(next_key), str):
                next_url = payload.get(next_key)

            if not next_url:
                break

            if isinstance(next_url, dict):
                next_url = next_url.get("url")

            if not isinstance(next_url, str) or not next_url:
                raise InvalidProviderResponse(
                    "External API pagination link must be a URL string"
                )

            current_url = httpx.URL(request_url)
            parsed = current_url.join(next_url)
            self._validate_origin(parsed)

            path = str(parsed.copy_with(query=None, fragment=None))
            page_params = dict(parsed.params)

        return records
