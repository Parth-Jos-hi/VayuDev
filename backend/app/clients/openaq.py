from datetime import datetime, timezone
from typing import Any, Protocol

from app.clients.base import BaseHTTPClient
from app.core.config import Settings, settings
from app.core.exceptions import (
    AuthenticationError,
    InvalidProviderResponse,
)


class AirQualityProvider(Protocol):
    def fetch_locations(
        self,
        bbox: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_location(self, location_id: int) -> dict[str, Any]: ...

    def fetch_sensors(self, location_id: int) -> list[dict[str, Any]]: ...

    def fetch_sensor(self, sensor_id: int) -> dict[str, Any]: ...

    def fetch_measurements(
        self,
        sensor_id: int,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_hourly_measurements(
        self,
        sensor_id: int,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_latest(
        self,
        location_id: int,
        datetime_min: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]: ...


class OpenAQClient:
    def __init__(
        self,
        http_client: BaseHTTPClient | None = None,
        config: Settings = settings,
    ):
        self.config = config
        self._owns_http_client = http_client is None

        if http_client is not None:
            self.http = http_client
            return

        if config.openaq_api_key is None:
            raise AuthenticationError("OpenAQ API key is required")

        self.http = BaseHTTPClient(
            base_url=config.openaq_base_url,
            timeout_seconds=config.openaq_http_timeout_seconds,
            max_retries=config.openaq_max_retries,
            backoff_seconds=config.openaq_retry_backoff_seconds,
            max_request_budget=config.openaq_max_request_budget,
            api_key=config.openaq_api_key.get_secret_value(),
            api_key_header="X-API-Key",
        )

    def close(self) -> None:
        if self._owns_http_client:
            self.http.close()

    @staticmethod
    def _validate_id(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")

    @staticmethod
    def _timestamp(value: datetime | None, name: str) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include timezone information")
        return (
            value.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _results(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not isinstance(payload, dict):
            raise InvalidProviderResponse(
                "OpenAQ response must be a JSON object"
            )

        results = payload.get("results")
        meta = payload.get("meta")
        if not isinstance(results, list) or not isinstance(meta, dict):
            raise InvalidProviderResponse(
                "OpenAQ response must include results and meta objects"
            )
        if any(not isinstance(item, dict) for item in results):
            raise InvalidProviderResponse(
                "OpenAQ response results must contain JSON objects"
            )
        return results, meta

    @classmethod
    def _single_result(cls, payload: Any) -> dict[str, Any]:
        results, _ = cls._results(payload)
        if len(results) != 1:
            raise InvalidProviderResponse(
                "OpenAQ detail response must contain exactly one result"
            )
        return results[0]

    def _fetch_pages(
        self,
        path: str,
        params: dict[str, Any],
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        limit = self.config.openaq_page_limit
        page = 1
        records: list[dict[str, Any]] = []

        while max_pages is None or page <= max_pages:
            response_params = {
                **params,
                "limit": limit,
                "page": page,
            }
            page_records, meta = self._results(
                self.http.get(path, response_params)
            )
            response_page = meta.get("page")
            if response_page is not None and response_page != page:
                raise InvalidProviderResponse(
                    "OpenAQ returned an unexpected page number"
                )

            records.extend(page_records)
            found = meta.get("found")
            if isinstance(found, int) and not isinstance(found, bool):
                if len(records) >= found:
                    break
                if not page_records:
                    raise InvalidProviderResponse("OpenAQ pagination ended before all results arrived")
            elif len(page_records) < limit:
                break
            page += 1

        return records

    def fetch_locations(
        self,
        bbox: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        if bbox is None:
            bbox = ",".join(
                f"{coordinate:.4f}"
                for coordinate in (
                    self.config.study_region_west,
                    self.config.study_region_south,
                    self.config.study_region_east,
                    self.config.study_region_north,
                )
            )
        return self._fetch_pages(
            "/v3/locations",
            {"bbox": bbox},
            max_pages=max_pages,
        )

    def fetch_location(self, location_id: int) -> dict[str, Any]:
        self._validate_id(location_id, "location_id")
        return self._single_result(
            self.http.get(f"/v3/locations/{location_id}")
        )

    def fetch_sensors(self, location_id: int) -> list[dict[str, Any]]:
        self._validate_id(location_id, "location_id")
        results, _ = self._results(
            self.http.get(f"/v3/locations/{location_id}/sensors")
        )
        return results

    def fetch_sensor(self, sensor_id: int) -> dict[str, Any]:
        self._validate_id(sensor_id, "sensor_id")
        return self._single_result(
            self.http.get(f"/v3/sensors/{sensor_id}")
        )

    def _measurement_params(
        self,
        datetime_from: datetime | None,
        datetime_to: datetime | None,
    ) -> dict[str, str]:
        params: dict[str, str] = {}
        start = self._timestamp(datetime_from, "datetime_from")
        end = self._timestamp(datetime_to, "datetime_to")
        if start is not None:
            params["datetime_from"] = start
        if end is not None:
            params["datetime_to"] = end
        if datetime_from is not None and datetime_to is not None:
            if datetime_to <= datetime_from:
                raise ValueError("datetime_to must be later than datetime_from")
        return params

    def fetch_measurements(
        self,
        sensor_id: int,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_id(sensor_id, "sensor_id")
        return self._fetch_pages(
            f"/v3/sensors/{sensor_id}/measurements",
            self._measurement_params(datetime_from, datetime_to),
            max_pages=max_pages,
        )

    def fetch_hourly_measurements(
        self,
        sensor_id: int,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_id(sensor_id, "sensor_id")
        return self._fetch_pages(
            f"/v3/sensors/{sensor_id}/hours",
            self._measurement_params(datetime_from, datetime_to),
            max_pages=max_pages,
        )

    def fetch_latest(
        self,
        location_id: int,
        datetime_min: datetime | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_id(location_id, "location_id")
        params: dict[str, str] = {}
        minimum = self._timestamp(datetime_min, "datetime_min")
        if minimum is not None:
            params["datetime_min"] = minimum
        return self._fetch_pages(
            f"/v3/locations/{location_id}/latest",
            params,
            max_pages=max_pages,
        )
