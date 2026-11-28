from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.clients.base import BaseHTTPClient
from app.clients.openaq import OpenAQClient
from app.core.config import settings
from app.core.exceptions import AuthenticationError, InvalidProviderResponse


def make_provider(handler, page_limit=2):
    transport = httpx.MockTransport(handler)
    http = BaseHTTPClient(
        base_url="https://api.openaq.org",
        max_retries=0,
        backoff_seconds=0,
        transport=transport,
    )
    config = settings.model_copy(update={"openaq_page_limit": page_limit})
    return OpenAQClient(http_client=http, config=config)


@pytest.fixture
def provider_factory(request):
    providers = []

    def create_provider(handler, **overrides):
        provider = make_provider(handler, **overrides)
        providers.append(provider)
        return provider

    request.addfinalizer(lambda: [provider.http.close() for provider in providers])
    return create_provider


def response(results, page=1, limit=2, found=None):
    meta = {"page": page, "limit": limit}
    if found is not None:
        meta["found"] = found
    return {"meta": meta, "results": results}


def test_fetch_locations_uses_configured_delhi_bbox_and_pages(provider_factory):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json=response([{"id": 1}, {"id": 2}], found=3),
            )
        return httpx.Response(
            200,
            json=response([{"id": 3}], page=2, found=3),
        )

    provider = provider_factory(handler)

    assert [station["id"] for station in provider.fetch_locations()] == [1, 2, 3]
    assert requests[0].url.path == "/v3/locations"
    assert requests[0].url.params["bbox"] == "76.8000,28.4000,77.3500,28.9000"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("fetch_location", "/v3/locations/17"),
        ("fetch_sensors", "/v3/locations/17/sensors"),
        ("fetch_sensor", "/v3/sensors/100"),
        ("fetch_measurements", "/v3/sensors/100/measurements"),
        ("fetch_hourly_measurements", "/v3/sensors/100/hours"),
        ("fetch_latest", "/v3/locations/17/latest"),
    ],
)
def test_provider_methods_use_documented_paths(method, path, provider_factory):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response([{"id": 1}], limit=100))

    provider = provider_factory(handler, page_limit=100)

    if method in ("fetch_location", "fetch_sensors", "fetch_latest"):
        getattr(provider, method)(17)
    elif method == "fetch_sensor":
        getattr(provider, method)(100)
    else:
        getattr(provider, method)(100)

    assert requests[0].url.path == path


def test_fetch_measurements_sends_utc_datetime_bounds(provider_factory):
    requests = []
    start = datetime(2026, 10, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response([{"value": 20}], limit=100))

    provider = provider_factory(handler, page_limit=100)
    provider.fetch_measurements(100, start, end)

    assert requests[0].url.params["datetime_from"] == "2026-09-30T18:30:00Z"
    assert requests[0].url.params["datetime_to"] == "2026-10-02T00:00:00Z"


def test_fetch_latest_sends_datetime_min(provider_factory):
    requests = []
    minimum = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response([{"sensorsId": 10}], limit=100))

    provider = provider_factory(handler, page_limit=100)
    provider.fetch_latest(17, datetime_min=minimum)

    assert requests[0].url.params["datetime_min"] == "2026-11-01T00:00:00Z"


def test_malformed_provider_envelope_is_rejected(provider_factory):
    def handler(request):
        assert request.url.path == "/v3/locations"
        return httpx.Response(200, json={"results": "not a list", "meta": {}})

    provider = provider_factory(handler)

    with pytest.raises(InvalidProviderResponse):
        provider.fetch_locations(max_pages=1)


def test_detail_response_must_contain_one_result(provider_factory):
    def handler(request):
        assert request.url.path == "/v3/locations/17"
        return httpx.Response(200, json=response([], limit=1))

    provider = provider_factory(handler, page_limit=100)

    with pytest.raises(InvalidProviderResponse):
        provider.fetch_location(17)


def test_measurement_timestamps_must_be_timezone_aware(provider_factory):
    def handler(request):
        raise AssertionError(f"Unexpected API call: {request.url}")

    provider = provider_factory(handler)

    with pytest.raises(ValueError, match="timezone"):
        provider.fetch_measurements(
            100,
            datetime(2026, 10, 1),
        )


def test_measurement_time_range_must_be_increasing(provider_factory):
    def handler(request):
        raise AssertionError(f"Unexpected API call: {request.url}")

    provider = provider_factory(handler)
    start = datetime(2026, 10, 2, tzinfo=timezone.utc)
    end = start - timedelta(hours=1)

    with pytest.raises(ValueError, match="later"):
        provider.fetch_measurements(100, start, end)


@pytest.mark.parametrize("location_id", [0, -1, True, "17"])
def test_location_id_must_be_positive_integer(provider_factory, location_id):
    def handler(request):
        raise AssertionError(f"Unexpected API call: {request.url}")

    provider = provider_factory(handler)

    with pytest.raises(ValueError, match="positive integer"):
        provider.fetch_location(location_id)


def test_api_key_is_required_for_real_client():
    config = settings.model_copy(update={"openaq_api_key": None})

    with pytest.raises(AuthenticationError, match="API key is required"):
        OpenAQClient(config=config)

