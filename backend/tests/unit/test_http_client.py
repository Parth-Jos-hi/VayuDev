import httpx
import pytest

import app.clients.base as http_client
from app.clients.base import BaseHTTPClient
from app.core.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    InvalidProviderResponse,
    RateLimitError,
    RequestBudgetExceeded,
)


@pytest.fixture
def client_factory(request):
    clients = []

    def create_client(handler, **overrides):
        transport = httpx.MockTransport(handler)
        values = {
            "base_url": "https://example.test",
            "timeout_seconds": 1,
            "max_retries": 2,
            "backoff_seconds": 0,
            "max_request_budget": 100,
        }
        values.update(overrides)
        client = BaseHTTPClient(transport=transport, **values)
        clients.append(client)
        return client

    request.addfinalizer(lambda: [client.close() for client in clients])
    return create_client


def test_successful_get_and_api_key_header(client_factory):
    def handler(request):
        assert request.headers["X-API-Key"] == "test-key"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200, json={"results": []})

    client = client_factory(
        handler,
        api_key="test-key",
    )

    assert client.get("/v3/test", {"limit": 10}) == {"results": []}
    assert client.requests_used == 1


def test_request_timeout_is_retried(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("timeout")

    client = client_factory(handler)

    with pytest.raises(ExternalServiceError):
        client.get("/v3/test")

    assert calls == 3
    assert client.requests_used == 3


def test_rate_limit_respects_retry_after(client_factory, monkeypatch):
    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
            )
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(http_client.time, "sleep", delays.append)
    client = client_factory(handler)

    assert client.get("/v3/test") == {"results": []}
    assert calls == 2
    assert delays == [2]


def test_permanent_authentication_error_is_not_retried(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"detail": "invalid"})

    client = client_factory(handler)

    with pytest.raises(AuthenticationError):
        client.get("/v3/test")

    assert calls == 1


def test_malformed_json_is_rejected(client_factory):
    def handler(request):
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"Content-Type": "text/plain"},
        )

    client = client_factory(handler)

    with pytest.raises(InvalidProviderResponse):
        client.get("/v3/test")


def test_permanent_404_is_not_retried(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"detail": "not found"})

    client = client_factory(handler)

    with pytest.raises(ExternalServiceError):
        client.get("/v3/test")

    assert calls == 1


def test_rate_limit_retry_exhaustion(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "0"},
        )

    client = client_factory(handler)

    with pytest.raises(RateLimitError):
        client.get("/v3/test")

    assert calls == 3


def test_request_budget_is_enforced(client_factory):
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    client = client_factory(handler, max_request_budget=1)

    assert client.get("/v3/test") == {"ok": True}

    with pytest.raises(RequestBudgetExceeded):
        client.get("/v3/test")


def test_paginated_response_returns_all_results_and_uses_next_page(
    client_factory,
):
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json={
                    "results": [1, 2],
                    "meta": {
                        "next": "/v3/test?page=2",
                    },
                },
            )
        return httpx.Response(200, json={"results": [3], "meta": {}})

    client = client_factory(handler)

    assert client.get_paginated("/v3/test", {"page": 1}) == [1, 2, 3]
    assert len(requested_urls) == 2
    assert httpx.URL(requested_urls[1]).params["page"] == "2"


def test_server_error_is_retried(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = client_factory(handler)

    assert client.get("/v3/test") == {"ok": True}
    assert calls == 3


def test_connection_error_is_retried(client_factory):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return httpx.Response(200, json={"ok": True})

    client = client_factory(handler)

    assert client.get("/v3/test") == {"ok": True}
    assert calls == 2


def test_exponential_backoff(client_factory, monkeypatch):
    delays = []

    def handler(request):
        return httpx.Response(503)

    monkeypatch.setattr(http_client.time, "sleep", delays.append)
    client = client_factory(handler, backoff_seconds=0.25)

    with pytest.raises(ExternalServiceError):
        client.get("/v3/test")

    assert delays == [0.25, 0.5]


def test_api_key_is_not_in_error(client_factory):
    api_key = "private-test-key"

    def handler(request):
        return httpx.Response(401)

    client = client_factory(handler, api_key=api_key)

    with pytest.raises(AuthenticationError) as error:
        client.get("/v3/test")

    assert api_key not in str(error.value)


def test_absolute_request_to_another_origin_is_rejected(client_factory):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = client_factory(handler, api_key="private-test-key")

    with pytest.raises(InvalidProviderResponse, match="untrusted origin"):
        client.get("https://attacker.test/collect")

    assert requests == []
    assert client.requests_used == 0


def test_cross_origin_pagination_is_rejected(client_factory):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [1],
                "meta": {"next": "https://attacker.test/steal"},
            },
        )

    client = client_factory(handler, api_key="private-test-key")

    with pytest.raises(InvalidProviderResponse, match="untrusted origin"):
        client.get_paginated("/v3/test")

    assert client.requests_used == 1


def test_request_budget_counts_retry_attempts(client_factory):
    def handler(request):
        return httpx.Response(503)

    client = client_factory(handler, max_request_budget=2)

    with pytest.raises(RequestBudgetExceeded):
        client.get("/v3/test")

    assert client.requests_used == 2


def test_invalid_paginated_response_structure_is_rejected(client_factory):
    def handler(request):
        return httpx.Response(200, json={"results": "not-a-list"})

    client = client_factory(handler)

    with pytest.raises(InvalidProviderResponse):
        client.get_paginated("/v3/test")


def test_repeated_pagination_url_is_rejected(client_factory):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [1],
                "meta": {"next": str(request.url)},
            },
        )

    client = client_factory(handler)

    with pytest.raises(InvalidProviderResponse, match="repeated"):
        client.get_paginated("/v3/test")

    assert client.requests_used == 1


def test_empty_paginated_response_returns_empty_list(client_factory):
    def handler(request):
        return httpx.Response(200, json={"results": [], "meta": {}})

    client = client_factory(handler)

    assert client.get_paginated("/v3/test") == []


def test_max_pages_stops_pagination(client_factory):
    def handler(request):
        page = request.url.params.get("page", "1")
        return httpx.Response(
            200,
            json={
                "results": [page],
                "meta": {"next": f"/v3/test?page={int(page) + 1}"},
            },
        )

    client = client_factory(handler)

    assert client.get_paginated(
        "/v3/test",
        params={"page": 1},
        max_pages=2,
    ) == ["1", "2"]


def test_client_resource_cleanup(client_factory):
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    client = client_factory(handler)
    with client:
        assert client.get("/v3/test") == {"ok": True}
    assert client._client.is_closed
