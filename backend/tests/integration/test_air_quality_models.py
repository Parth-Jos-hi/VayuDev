from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.air_quality import (
    AirQualityIngestionRun,
    AirQualityMeasurement,
    AirQualitySensor,
    AirQualityStation,
)


def make_station(**overrides) -> AirQualityStation:
    values = {
        "source": "openaq",
        "external_id": str(uuid4()),
        "name": "Test Air Quality Station",
        "latitude": 28.61,
        "longitude": 77.20,
        "location": WKTElement("POINT(77.20 28.61)", srid=4326),
        "country_code": "IN",
        "locality": "Delhi",
    }
    values.update(overrides)
    return AirQualityStation(**values)


def make_sensor(station: AirQualityStation, **overrides) -> AirQualitySensor:
    values = {
        "station": station,
        "source": "openaq",
        "external_id": str(uuid4()),
        "pollutant": "pm25",
        "original_unit": "µg/m³",
    }
    values.update(overrides)
    return AirQualitySensor(**values)


def test_station_sensor_and_measurement_relationship(
    db_session: Session,
):
    station = make_station()
    sensor = make_sensor(station)
    now = datetime.now(timezone.utc)

    measurement = AirQualityMeasurement(
        sensor=sensor,
        value=40.5,
        unit="µg/m³",
        original_value=40.5,
        original_unit="µg/m³",
        period_start=now,
        period_end=now + timedelta(hours=1),
        aggregation_type="hourly",
        quality_status="valid",
    )

    db_session.add(station)
    db_session.flush()

    assert station.sensors == [sensor]
    assert sensor.station == station
    assert sensor.measurements == [measurement]
    assert measurement.sensor == sensor


def test_duplicate_station_identity_is_rejected(db_session: Session):
    external_id = str(uuid4())
    db_session.add(make_station(external_id=external_id))
    db_session.flush()

    db_session.add(make_station(external_id=external_id))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_measurement_is_rejected(db_session: Session):
    station = make_station()
    sensor = make_sensor(station)
    now = datetime.now(timezone.utc)

    for _ in range(2):
        db_session.add(
            AirQualityMeasurement(
                sensor=sensor,
                value=30,
                unit="µg/m³",
                original_value=30,
                original_unit="µg/m³",
                period_start=now,
                period_end=now + timedelta(hours=1),
                aggregation_type="hourly",
            )
        )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_station_coordinates_are_rejected(db_session: Session):
    db_session.add(make_station(latitude=91))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_ingestion_run_tracks_execution(db_session: Session):
    run = AirQualityIngestionRun(
        source="openaq",
        job_type="backfill",
        status="running",
    )
    db_session.add(run)
    db_session.flush()

    saved = db_session.execute(
        select(AirQualityIngestionRun).where(
            AirQualityIngestionRun.id == run.id
        )
    ).scalar_one()

    assert saved.records_fetched == 0
    assert saved.completed_at is None
