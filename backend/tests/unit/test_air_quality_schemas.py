from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.air_quality import (
    HistoricalMeasurementQuery,
    MeasurementIngestion,
    SensorIngestion,
    StationIngestion,
)
from app.schemas.air_quality_ingestion import IngestionExecutionResult


def test_valid_station_contract():
    station = StationIngestion.model_validate({
        "source": "openaq",
        "external_id": "123",
        "name": "Test station",
        "latitude": "28.61",
        "longitude": "77.20",
    })

    assert station.latitude == pytest.approx(28.61)
    assert station.longitude == pytest.approx(77.20)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 91),
        ("latitude", -91),
        ("longitude", 181),
        ("latitude", True),
    ],
)
def test_invalid_station_coordinates(field, value):
    data = {
        "source": "openaq",
        "external_id": "123",
        "latitude": 28.61,
        "longitude": 77.20,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        StationIngestion.model_validate(data)


def test_valid_sensor_contract():
    sensor = SensorIngestion.model_validate({
        "source": "openaq",
        "external_id": "456",
        "station_external_id": "123",
        "pollutant": "PM25",
        "original_unit": "µg/m³",
    })

    assert sensor.pollutant == "pm25"


def test_sensor_rejects_unknown_pollutant():
    with pytest.raises(ValidationError):
        SensorIngestion.model_validate({
            "source": "openaq",
            "external_id": "456",
            "station_external_id": "123",
            "pollutant": "methane",
            "original_unit": "ppm",
        })


def test_valid_measurement_contract():
    now = datetime.now(timezone.utc)
    measurement = MeasurementIngestion.model_validate({
        "sensor_external_id": "456",
        "value": 40.5,
        "unit": "µg/m³",
        "original_value": 40.5,
        "original_unit": "µg/m³",
        "period_start": now.isoformat(),
        "period_end": (now + timedelta(hours=1)).isoformat(),
        "aggregation_type": "hourly",
    })

    assert measurement.value == 40.5
    assert measurement.quality_status == "valid"


def test_measurement_rejects_invalid_period():
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        MeasurementIngestion.model_validate({
            "sensor_external_id": "456",
            "value": 40,
            "unit": "µg/m³",
            "original_value": 40,
            "original_unit": "µg/m³",
            "period_start": now.isoformat(),
            "period_end": now.isoformat(),
        })


def test_measurement_rejects_naive_timestamp():
    now = datetime.now()

    with pytest.raises(ValidationError):
        MeasurementIngestion.model_validate({
            "sensor_external_id": "456",
            "value": 40,
            "unit": "µg/m³",
            "original_value": 40,
            "original_unit": "µg/m³",
            "period_start": now.isoformat(),
            "period_end": (now + timedelta(hours=1)).isoformat(),
        })


def test_historical_query_validates_range_and_limit():
    now = datetime.now(timezone.utc)
    query = HistoricalMeasurementQuery.model_validate({
        "from_at": now.isoformat(),
        "to_at": (now + timedelta(days=1)).isoformat(),
        "pollutant": "pm25",
        "limit": 500,
    })

    assert query.limit == 500

    with pytest.raises(ValidationError):
        HistoricalMeasurementQuery.model_validate({
            "from_at": now.isoformat(),
            "to_at": now.isoformat(),
        })


def test_ingestion_result_contract():
    now = datetime.now(timezone.utc)
    run = IngestionExecutionResult.model_validate({
        "id": str(uuid4()),
        "source": "openaq",
        "job_type": "incremental",
        "status": "success",
        "started_at": now.isoformat(),
        "completed_at": (now + timedelta(minutes=2)).isoformat(),
        "records_inserted": 10,
    })

    assert run.status == "success"
    assert run.records_inserted == 10
