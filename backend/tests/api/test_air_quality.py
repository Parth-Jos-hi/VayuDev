from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.air_quality import get_repository
from app.core.security.auth import get_current_user
from app.main import app


BASE = "/api/v1/air-quality"


@pytest.fixture
def api():
    repository = Mock()
    with TestClient(app) as client:
        app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid4())}
        app.dependency_overrides[get_repository] = lambda: repository
        try:
            yield client, repository
        finally:
            app.dependency_overrides.pop(get_current_user)
            app.dependency_overrides.pop(get_repository)


def test_air_quality_requires_a_bearer_token():
    response = TestClient(app).get(f"{BASE}/stations")
    assert response.status_code == 401


@pytest.mark.parametrize("query", [
    {"from_at": "2026-10-01", "to_at": "2026-10-02"},
    {"from_at": "2026-10-02T00:00:00Z", "to_at": "2026-10-01T00:00:00Z"},
    {"from_at": "2026-10-01T00:00:00Z", "to_at": "2026-11-02T00:00:00Z"},
    {"from_at": "2026-10-01T00:00:00Z", "to_at": "2026-10-02T00:00:00Z", "limit": 10001},
])
def test_history_validates_range_and_page(api, query):
    client, repository = api
    response = client.get(f"{BASE}/stations/{uuid4()}/measurements", params=query)
    assert response.status_code == 422
    repository.measurements.assert_not_called()


def test_unknown_station_returns_404(api):
    client, repository = api
    repository.station.return_value = None
    response = client.get(f"{BASE}/stations/{uuid4()}/latest")
    assert response.status_code == 404
    repository.latest.assert_not_called()


def test_sensor_pagination_and_pollutant_filter(api):
    client, repository = api
    station_id = uuid4()
    repository.station.return_value.id = station_id
    repository.sensors.return_value = []
    response = client.get(
        f"{BASE}/stations/{station_id}/sensors",
        params={"pollutant": "pm25", "limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    assert response.json() == []
    _, pollutant, page = repository.sensors.call_args.args
    assert (pollutant, page.limit, page.offset) == ("pm25", 2, 1)
