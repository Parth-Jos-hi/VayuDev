from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.clients.base import BaseHTTPClient
from app.clients.openaq import OpenAQClient
from app.core.config import settings
from app.core.security.auth import get_current_user
from app.db.models.air_quality import AirQualitySensor, AirQualityStation
from app.db.repositories.air_quality import AirQualityRepository
from app.db.session import get_db
from app.jobs.air_quality_report import build_report
from app.main import app
from app.schemas.air_quality import AirQualityPage
from app.services.air_quality_service import AirQualityIngestionService


BASE = "/api/v1/air-quality"
START = datetime(2026, 10, 1, tzinfo=timezone.utc)
NOW = START + timedelta(hours=5)
UNIT = "µg/m³"


def test_openaq_to_database_and_api(db_session, monkeypatch):
    value = 42
    requests = []

    def openaq(request):
        requests.append(request.url.path)
        assert request.headers["X-API-Key"] == "test-key"
        if request.url.path == "/v3/locations":
            results = [{
                "id": 17, "name": "Delhi test", "isMobile": False, "isMonitor": True,
                "coordinates": {"latitude": 28.56, "longitude": 77.18},
            }]
        elif request.url.path == "/v3/locations/17/sensors":
            results = [{"id": 100, "parameter": {"name": "pm25", "units": UNIT}}]
        else:
            assert request.url.path == "/v3/sensors/100/hours"
            results = [{
                "value": value,
                "parameter": {"name": "pm25", "units": UNIT},
                "period": {
                    "datetimeFrom": {"utc": (NOW - timedelta(hours=1)).isoformat()},
                    "datetimeTo": {"utc": NOW.isoformat()},
                },
            }]
        return httpx.Response(200, json={"results": results, "meta": {"found": len(results)}})

    config = settings.model_copy(update={
        "air_quality_historical_start": START.date(),
        "air_quality_historical_end": START.date(),
        "incremental_overlap_seconds": 3600,
    })
    repository = AirQualityRepository(db_session)
    with BaseHTTPClient(
        base_url="https://api.openaq.org", api_key="test-key",
        transport=httpx.MockTransport(openaq),
    ) as http:
        service = AirQualityIngestionService(OpenAQClient(http, config), repository, config)
        assert service.sync("discovery", now=NOW).sensors_upserted == 1
        assert service.sync("incremental", now=NOW).measurements_upserted == 1
        repeated = service.sync("incremental", now=NOW + timedelta(minutes=10))
        assert (repeated.measurements_upserted, repeated.measurements_skipped) == (0, 1)
        value = 55
        assert service.sync("incremental", now=NOW + timedelta(minutes=20)).measurements_upserted == 1

        with monkeypatch.context() as patch:
            def fail_checkpoint(*args):
                raise SQLAlchemyError("test persistence failure")

            patch.setattr(repository, "complete_sensor_window", fail_checkpoint)
            value = 90
            failed = service.sync("incremental", now=NOW + timedelta(minutes=30))
            assert failed.windows_completed == failed.measurements_upserted == 0
            assert list(failed.failed_windows.values()) == ["SQLAlchemyError"]

    with db_session.begin():
        station_id = db_session.scalar(
            select(AirQualityStation.id).where(AirQualityStation.external_id == "17")
        )
        sensor = db_session.scalar(select(AirQualitySensor).where(AirQualitySensor.external_id == "100"))
        assert sensor.synced_through == NOW + timedelta(minutes=20)
        assert sensor.last_synced_at == sensor.synced_through
        assert sensor.last_measurement_at == NOW
        report = build_report(db_session, config, AirQualityPage())
        assert report["stations"] == 1
        assert report["measurements"] == 1

    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db_session)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: {"sub": str(uuid4())})
    with TestClient(app) as client:
        assert client.get(f"{BASE}/stations", params={"limit": 1}).json()[0]["id"] == str(station_id)
        assert client.get(f"{BASE}/stations/{station_id}").json()["name"] == "Delhi test"
        assert len(client.get(f"{BASE}/stations/{station_id}/sensors").json()) == 1
        latest = client.get(f"{BASE}/stations/{station_id}/latest")
        assert latest.status_code == 200
        assert latest.json()[0]["value"] == 55
        history = client.get(f"{BASE}/stations/{station_id}/measurements", params={
            "from_at": START.isoformat(), "to_at": NOW.isoformat(), "pollutant": "pm25",
        }).json()
        assert len(history) == 1
        assert (history[0]["value"], history[0]["original_unit"]) == (55, UNIT)
        assert client.get(f"{BASE}/status").json()[0]["measurement_count"] == 1
    assert len(requests) == 6
