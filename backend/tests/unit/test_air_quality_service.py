from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.repositories.air_quality import RepositoryWriteResult
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

    def upsert_stations(self, records, synced_at):
        self.stations.extend(records)
        self.sync_times.append(synced_at)
        return RepositoryWriteResult(
            records_received=len(records),
            records_upserted=len(records),
            batches_executed=int(bool(records)),
        )

    def upsert_sensors(self, records, synced_at):
        self.sensors.extend(records)
        self.sync_times.append(synced_at)
        return RepositoryWriteResult(
            records_received=len(records),
            records_upserted=len(records),
            batches_executed=int(bool(records)),
        )

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


def test_incremental_sync_reuses_last_sensor_timestamp_with_overlap():
    provider = FakeProvider(measurements=[])
    service, _ = make_service(provider)

    service.sync("incremental", now=NOW)

    assert provider.measurement_requests == [
        (
            100,
            datetime(2026, 11, 28, 7, 15, tzinfo=timezone.utc),
            NOW,
            None,
        )
    ]


def test_incremental_sync_skips_sensors_without_a_checkpoint():
    provider = FakeProvider(last_seen=None)
    service, _ = make_service(provider)

    result = service.sync("incremental", now=NOW)

    assert result.sensors_skipped == 1
    assert provider.measurement_requests == []


def test_sync_requires_a_fresh_session_transaction():
    provider = FakeProvider()
    service, repository = make_service(provider)
    repository.session.active = True

    with pytest.raises(RuntimeError, match="without an active transaction"):
        service.sync("discovery", now=NOW)

    assert provider.measurement_requests == []
