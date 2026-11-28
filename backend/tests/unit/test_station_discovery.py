from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.ingestion.air_quality.station_discovery import StationDiscoveryService


NOW = datetime(2026, 11, 28, 8, 0, tzinfo=timezone.utc)


def make_location(**overrides):
    location = {
        "id": 17,
        "name": "R K Puram, Delhi - DPCC",
        "locality": "Delhi",
        "country": {"code": "IN"},
        "provider": {"id": 168, "name": "Delhi Pollution Control Committee"},
        "isMobile": False,
        "isMonitor": True,
        "coordinates": {"latitude": 28.56, "longitude": 77.18},
    }
    location.update(overrides)
    return location


def make_sensor(sensor_id, pollutant, unit="µg/m³", last_seen=None):
    sensor = {
        "id": sensor_id,
        "name": f"{pollutant} sensor",
        "parameter": {"name": pollutant, "units": unit},
    }
    if last_seen is not None:
        sensor["datetimeLast"] = {"utc": last_seen}
    return sensor


class FakeProvider:
    def __init__(self, locations, sensors_by_location):
        self.locations = locations
        self.sensors_by_location = sensors_by_location
        self.requested_locations = []

    def fetch_locations(self, bbox=None, max_pages=None):
        self.requested_locations.append((bbox, max_pages))
        return self.locations

    def fetch_sensors(self, location_id):
        return self.sensors_by_location.get(location_id, [])


def make_service(provider, **config_overrides):
    config = settings.model_copy(update=config_overrides)
    return StationDiscoveryService(provider, config)


def test_discovers_station_and_only_supported_sensors():
    provider = FakeProvider(
        [make_location()],
        {
            17: [
                make_sensor(100, "pm25", last_seen="2026-11-28T07:30:00Z"),
                make_sensor(101, "pm10", last_seen="2026-11-28T06:00:00Z"),
                make_sensor(102, "co", unit="mg/m³", last_seen="2026-11-28T07:45:00Z"),
            ],
        },
    )
    service = make_service(provider)

    result = service.discover(now=NOW)

    assert len(result.stations) == 1
    discovered = result.stations[0]
    assert discovered.station.external_id == "17"
    assert discovered.station.provider_name == "Delhi Pollution Control Committee"
    assert discovered.station.latitude == pytest.approx(28.56)
    assert discovered.station.longitude == pytest.approx(77.18)
    assert discovered.station.is_active is True
    assert [sensor.pollutant for sensor in discovered.sensors] == ["pm25", "pm10"]
    assert discovered.sensors[0].original_unit == "µg/m³"
    assert discovered.sensors[0].is_active is True
    assert discovered.sensors[1].is_active is False
    assert result.stats.sensors_skipped_unsupported == 1
    assert result.stats.sensors_inactive == 1


def test_uses_configured_region_and_pagination_limit():
    provider = FakeProvider([], {})
    service = make_service(provider)

    service.discover(now=NOW, max_pages=3)

    assert provider.requested_locations == [
        ("76.8000,28.4000,77.3500,28.9000", 3)
    ]


def test_skips_non_monitors_without_fetching_sensors():
    provider = FakeProvider(
        [make_location(id=18, isMonitor=False)],
        {},
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations == []
    assert result.stats.stations_skipped_non_monitor == 1


def test_outdated_station_is_kept_but_marked_inactive():
    provider = FakeProvider(
        [make_location()],
        {17: [make_sensor(100, "pm25", last_seen="2026-11-28T06:00:00Z")]},
    )

    result = make_service(provider).discover(now=NOW)

    assert len(result.stations) == 1
    assert result.stations[0].station.is_active is False
    assert result.stats.stations_inactive == 1
    assert result.stats.sensors_inactive == 1


def test_mobile_station_is_kept_inactive_even_with_recent_data():
    provider = FakeProvider(
        [make_location(isMobile=True)],
        {
            17: [
                make_sensor(100, "pm25", last_seen="2026-11-28T07:30:00Z")
            ],
        },
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations[0].station.is_mobile is True
    assert result.stations[0].station.is_active is False


def test_skips_stations_outside_region_or_with_invalid_coordinates():
    provider = FakeProvider(
        [
            make_location(id=17, coordinates={"latitude": 29.0, "longitude": 77.18}),
            make_location(id=18, coordinates={"latitude": 91, "longitude": 77.18}),
        ],
        {},
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations == []
    assert result.stats.stations_skipped_outside_region == 1
    assert result.stats.stations_skipped_invalid == 1


def test_skips_station_without_supported_sensors():
    provider = FakeProvider(
        [make_location()],
        {17: [make_sensor(100, "co", "mg/m³")]},
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations == []
    assert result.stats.stations_skipped_without_supported_sensors == 1
    assert result.stats.sensors_skipped_unsupported == 1


def test_invalid_sensor_data_is_counted_and_skipped():
    provider = FakeProvider(
        [make_location()],
        {
            17: [
                {
                    "id": 100,
                    "parameter": {"name": "pm25"},
                },
                make_sensor(101, "pm25", last_seen="not-a-timestamp"),
                make_sensor(0, "pm25"),
            ],
        },
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations == []
    assert result.stats.sensors_rejected_invalid == 3
    assert result.stats.stations_skipped_without_supported_sensors == 1


def test_duplicate_locations_are_only_discovered_once():
    location = make_location()
    provider = FakeProvider(
        [location, location],
        {
            17: [make_sensor(100, "pm25", last_seen="2026-11-28T07:30:00Z")]
        },
    )

    result = make_service(provider).discover(now=NOW)

    assert len(result.stations) == 1
    assert result.stats.duplicate_locations_skipped == 1


def test_future_measurement_is_not_considered_fresh():
    provider = FakeProvider(
        [make_location()],
        {
            17: [
                make_sensor(
                    100,
                    "pm25",
                    last_seen=(NOW + timedelta(minutes=5)).isoformat(),
                )
            ],
        },
    )

    result = make_service(provider).discover(now=NOW)

    assert result.stations[0].sensors[0].is_active is False
