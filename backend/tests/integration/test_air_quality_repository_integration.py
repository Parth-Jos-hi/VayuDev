from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.air_quality import (
    AirQualityIngestionRun,
    AirQualityMeasurement,
    AirQualitySensor,
    AirQualityStation,
)
from app.db.repositories.air_quality import AirQualityRepository
from app.schemas.air_quality import (
    MeasurementIngestion,
    SensorIngestion,
    StationIngestion,
)


def make_station(**overrides) -> StationIngestion:
    values = {
        "source": "openaq",
        "external_id": "station-1",
        "name": "Delhi station",
        "latitude": 28.61,
        "longitude": 77.20,
        "country_code": "IN",
        "locality": "Delhi",
    }
    values.update(overrides)
    return StationIngestion.model_validate(values)


def make_sensor(**overrides) -> SensorIngestion:
    values = {
        "source": "openaq",
        "external_id": "sensor-1",
        "station_external_id": "station-1",
        "pollutant": "pm25",
        "original_unit": "µg/m³",
        "last_measurement_at": datetime(2026, 11, 28, 7, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SensorIngestion.model_validate(values)


def make_measurement(**overrides) -> MeasurementIngestion:
    period_start = datetime(2026, 11, 28, 6, tzinfo=timezone.utc)
    values = {
        "sensor_external_id": "sensor-1",
        "value": 40,
        "unit": "µg/m³",
        "original_value": 40,
        "original_unit": "µg/m³",
        "period_start": period_start,
        "period_end": period_start + timedelta(hours=1),
        "aggregation_type": "hourly",
        "quality_status": "valid",
    }
    values.update(overrides)
    return MeasurementIngestion.model_validate(values)


def test_station_and_sensor_upserts_keep_identity_and_metadata(
    db_session: Session,
):
    repository = AirQualityRepository(db_session)
    synced_at = datetime(2026, 11, 28, 8, tzinfo=timezone.utc)

    with db_session.begin():
        station_result = repository.upsert_stations(
            [make_station()],
            synced_at=synced_at,
        )
        station = db_session.execute(
            select(AirQualityStation).where(
                AirQualityStation.external_id == "station-1"
            )
        ).scalar_one()

        update_result = repository.upsert_stations(
            [make_station(name=None, latitude=28.62)],
            synced_at=synced_at + timedelta(minutes=1),
        )
        db_session.expire(station)
        saved_station = db_session.get(AirQualityStation, station.id)

        repository.upsert_sensors([make_sensor()])
        sensor_result = repository.upsert_sensors(
            [make_sensor(is_active=False, last_measurement_at=None)]
        )
        saved_sensor = db_session.execute(
            select(AirQualitySensor).where(
                AirQualitySensor.external_id == "sensor-1"
            )
        ).scalar_one()

        assert station_result.records_upserted == 1
        assert update_result.records_upserted == 1
        assert saved_station.id == station.id
        assert saved_station.name == "Delhi station"
        assert saved_station.latitude == 28.62
        assert sensor_result.records_upserted == 1
        assert saved_sensor.is_active is False
        assert saved_sensor.last_measurement_at is None
        assert saved_sensor.last_synced_at is None
        assert repository.get_sensor_pollutants("openaq") == {
            "sensor-1": "pm25"
        }


def test_measurement_upsert_is_idempotent_and_updates_quality(
    db_session: Session,
):
    repository = AirQualityRepository(db_session)
    first = make_measurement(value=40)
    corrected = make_measurement(value=55, quality_status="suspect")

    with db_session.begin():
        repository.upsert_stations([make_station()])
        repository.upsert_sensors([make_sensor()])
        result = repository.upsert_measurements(
            [first, corrected],
            source="openaq",
        )
        saved = db_session.execute(
            select(AirQualityMeasurement)
        ).scalar_one()

        assert result.records_received == 2
        assert result.records_upserted == 1
        assert result.batches_executed == 1
        assert saved.value == 55
        assert saved.quality_status == "suspect"


def test_sensor_upsert_rejects_an_unknown_station(db_session: Session):
    repository = AirQualityRepository(db_session)

    with db_session.begin():
        try:
            repository.upsert_sensors(
                [make_sensor(station_external_id="missing-station")]
            )
        except ValueError as error:
            assert "Station not found" in str(error)
        else:
            raise AssertionError("Expected missing station to be rejected")


def test_ingestion_run_records_final_status_and_counts(db_session: Session):
    repository = AirQualityRepository(db_session)
    started_at = datetime(2026, 11, 28, 7, tzinfo=timezone.utc)

    with db_session.begin():
        run = repository.start_ingestion_run(
            source="openaq",
            job_type="backfill",
            started_at=started_at,
        )
        saved_run = repository.finish_ingestion_run(
            run.id,
            status="success",
            completed_at=started_at + timedelta(minutes=5),
            counts={
                "records_fetched": 10,
                "records_upserted": 8,
                "records_inserted": 8,
                "records_skipped": 2,
            },
        )

        assert saved_run.status == "success"
        assert saved_run.records_fetched == 10
        assert saved_run.records_upserted == 8
        assert saved_run.records_inserted == 8
        assert saved_run.records_skipped == 2
        assert saved_run.completed_at == started_at + timedelta(minutes=5)

    assert db_session.get(AirQualityIngestionRun, run.id) is not None
