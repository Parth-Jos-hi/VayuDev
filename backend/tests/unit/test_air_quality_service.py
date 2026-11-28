from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, RequestBudgetExceeded
from app.db.repositories.air_quality import IncrementalSensor, RepositoryWriteResult
from app.services.air_quality_service import AirQualityIngestionService


NOW = datetime(2026, 11, 28, 8, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self):
        self.active = False

    def in_transaction(self):
        return self.active

    @contextmanager
    def begin(self):
        self.active = True
        try:
            yield
        finally:
            self.active = False


class FakeRepository:
    def __init__(self):
        self.session = FakeSession()
        self.stations = []
        self.sensors = []
        self.measurements = []
        self.sync_times = []
        self.measurement_sources = []
        self.incremental = []
        self.checkpoints = []

    def upsert_stations(self, records, synced_at):
        self.stations.extend(records)
        self.sync_times.append(synced_at)
        return RepositoryWriteResult(
            records_received=len(records),
            records_upserted=len(records),
            batches_executed=int(bool(records)),
        )

    def upsert_sensors(self, records):
        self.sensors.extend(records)
        return RepositoryWriteResult(
            records_received=len(records),
            records_upserted=len(records),
            batches_executed=int(bool(records)),
        )

    def incremental_sensors(self, config):
        return self.incremental

    def complete_sensor_window(self, sensor_id, through, synced_at):
        assert self.session.in_transaction()
        self.checkpoints.append((sensor_id, through, synced_at))

    def upsert_measurements(self, records, source):
        self.measurements.extend(records)
        self.measurement_sources.append(source)
        return RepositoryWriteResult(
            records_received=len(records),
            records_upserted=len(records),
            batches_executed=int(bool(records)),
        )


class FakeProvider:
    def __init__(self, measurements=None, last_seen="2026-11-28T07:30:00Z"):
        self.measurements = measurements or []
        self.last_seen = last_seen
        self.measurement_requests = []
        self.location_requests = []
        self.sensor_requests = []

    def fetch_locations(self, bbox=None, max_pages=None):
        self.location_requests.append((bbox, max_pages))
        return [
            {
                "id": 17,
                "name": "Delhi station",
                "locality": "Delhi",
                "country": {"code": "IN"},
                "provider": {"name": "DPCC"},
                "isMobile": False,
                "isMonitor": True,
                "coordinates": {"latitude": 28.56, "longitude": 77.18},
            }
        ]

    def fetch_sensors(self, location_id):
        self.sensor_requests.append(location_id)
        sensor = {
            "id": 100,
            "parameter": {"name": "pm25", "units": "µg/m³"},
        }
        if self.last_seen is not None:
            sensor["datetimeLast"] = {"utc": self.last_seen}
        return [sensor]

    def fetch_hourly_measurements(
        self,
        sensor_id,
        datetime_from=None,
        datetime_to=None,
        max_pages=None,
    ):
        self.measurement_requests.append(
            (sensor_id, datetime_from, datetime_to, max_pages)
        )
        return self.measurements


def make_measurement(value, start, unit="µg/m³"):
    end = datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(hours=1)
    return {
        "value": value,
        "parameter": {"id": 2, "name": "pm25", "units": unit},
        "period": {
            "datetimeFrom": {"utc": start},
            "datetimeTo": {"utc": end.isoformat()},
        },
    }


def make_service(provider, **config_overrides):
    repository = FakeRepository()
    config = settings.model_copy(update=config_overrides)
    service = AirQualityIngestionService(provider, repository, config)
    return service, repository


def test_backfill_saves_valid_and_suspect_measurements():
    wrong_pollutant = make_measurement(20, "2026-10-01T03:00:00Z")
    wrong_pollutant["parameter"]["name"] = "pm10"
    provider = FakeProvider(
        [
            make_measurement(40, "2026-10-01T00:00:00Z"),
            make_measurement(1200, "2026-10-01T01:00:00Z"),
            make_measurement(10, "2026-10-01T02:00:00Z", unit="ppm"),
            wrong_pollutant,
        ]
    )
    service, repository = make_service(
        provider,
        air_quality_historical_start=date(2026, 10, 1),
        air_quality_historical_end=date(2026, 11, 1),
    )

    result = service.sync("backfill", now=NOW)

    assert len(repository.stations) == 1
    assert len(repository.sensors) == 1
    assert [item.quality_status for item in repository.measurements] == [
        "valid",
        "suspect",
    ]
    assert result.measurements_fetched == 4
    assert result.measurements_upserted == 2
    assert result.measurements_rejected == 2
    assert result.measurements_suspect == 1
    assert result.rejection_reasons["Unsupported concentration unit: ppm"] == 1
    assert (
        result.rejection_reasons[
            "Measurement pollutant does not match its sensor"
        ]
        == 1
    )
    assert repository.measurement_sources == ["openaq"]
    assert provider.measurement_requests == [
        (
            100,
            datetime(2026, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 11, 1, tzinfo=timezone.utc),
            None,
        )
    ]
    assert provider.location_requests == [
        ("76.8000,28.4000,77.3500,28.9000", None)
    ]


def test_discovery_only_does_not_fetch_measurements():
    provider = FakeProvider()
    service, repository = make_service(provider)

    result = service.sync("discovery", now=NOW)

    assert len(repository.stations) == 1
    assert len(repository.sensors) == 1
    assert repository.measurements == []
    assert result.measurements_fetched == 0
    assert provider.measurement_requests == []
    assert provider.sensor_requests == [17]


def test_incremental_sync_uses_database_checkpoint_and_replays_overlap():
    records = [
        make_measurement(20, "2026-11-28T06:30:00Z"),
        make_measurement(30, "2026-11-28T07:00:00Z"),
        make_measurement(40, "2026-11-28T07:30:00Z"),
    ]
    provider = FakeProvider(measurements=records)
    service, repository = make_service(provider, incremental_overlap_seconds=3600)
    sensor = IncrementalSensor(
        uuid4(), "100", "pm25", 28.56, 77.18, NOW - timedelta(minutes=30), None,
    )
    repository.incremental = [sensor]

    result = service.sync("incremental", now=NOW)

    assert provider.measurement_requests == [
        (100, NOW - timedelta(hours=2, minutes=30), NOW, None)
    ]
    assert provider.location_requests == []
    assert [item.value for item in repository.measurements] == [20, 30]
    assert repository.checkpoints == [(sensor.id, NOW, NOW)]
    assert result.measurements_skipped == 1
    assert result.sensors_missing == result.sensors_stale == 0


def test_incremental_empty_window_advances_checkpoint_but_keeps_stale_age():
    provider = FakeProvider()
    service, repository = make_service(
        provider, air_quality_historical_end=NOW.date(), incremental_overlap_seconds=0,
    )
    sensor = IncrementalSensor(
        uuid4(), "100", "pm25", 28.56, 77.18, None, NOW - timedelta(days=1),
    )
    repository.incremental = [sensor]

    result = service.sync("incremental", now=NOW)

    assert provider.measurement_requests[0][1] == NOW.replace(hour=0) - timedelta(hours=1)
    assert repository.checkpoints == [(sensor.id, NOW, NOW)]
    assert result.sensors_stale == 1


@pytest.mark.parametrize("error", [ExternalServiceError(), SQLAlchemyError(), RequestBudgetExceeded()])
def test_incremental_stops_at_failed_window(monkeypatch, error):
    provider = FakeProvider()
    service, repository = make_service(provider, incremental_overlap_seconds=0)
    first = IncrementalSensor(
        uuid4(), "100", "pm25", 28.56, 77.18, NOW - timedelta(days=20), None,
    )
    second = IncrementalSensor(
        uuid4(), "101", "pm25", 28.56, 77.18, NOW - timedelta(hours=1), None,
    )
    repository.incremental = [first, second]

    failed = False
    target, method = (
        (repository, "upsert_measurements") if isinstance(error, SQLAlchemyError)
        else (provider, "fetch_hourly_measurements")
    )
    original = getattr(target, method)

    def fail_on_second(*args, **kwargs):
        nonlocal failed
        if len(repository.checkpoints) == 1 and not failed:
            failed = True
            raise error
        return original(*args, **kwargs)

    monkeypatch.setattr(target, method, fail_on_second)
    result = service.sync("incremental", now=NOW)

    assert repository.checkpoints[0] == (first.id, NOW - timedelta(days=13), NOW)
    assert result.failed_windows == {
        f"100@{(NOW - timedelta(days=13)).isoformat()}": type(error).__name__
    }
    assert repository.checkpoints[1:] == (
        [] if isinstance(error, RequestBudgetExceeded) else [(second.id, NOW, NOW)]
    )


def test_sync_requires_a_fresh_session_transaction():
    provider = FakeProvider()
    service, repository = make_service(provider)
    repository.session.active = True

    with pytest.raises(RuntimeError, match="without an active transaction"):
        service.sync("discovery", now=NOW)

    assert provider.measurement_requests == []
