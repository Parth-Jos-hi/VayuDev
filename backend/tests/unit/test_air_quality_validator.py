from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.ingestion.air_quality.validator import (
    AirQualityMeasurementValidator,
)
from app.schemas.air_quality import MeasurementIngestion


NOW = datetime(2026, 11, 28, 8, 0, tzinfo=timezone.utc)


def make_measurement(
    value=50,
    unit="µg/m³",
    sensor_id="sensor-1",
    period_end=None,
):
    period_end = period_end or NOW - timedelta(minutes=5)
    return MeasurementIngestion(
        sensor_external_id=sensor_id,
        value=value,
        unit=unit,
        original_value=value,
        original_unit=unit,
        period_start=period_end - timedelta(hours=1),
        period_end=period_end,
    )


def make_validator(**config_overrides):
    config = settings.model_copy(update=config_overrides)
    return AirQualityMeasurementValidator(config)


def test_valid_zero_concentration_is_accepted():
    result = make_validator().validate(
        make_measurement(value=0),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.accepted is True
    assert result.quality_status == "valid"
    assert result.measurement.value == 0


@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (999, "valid"),
        (1000, "valid"),
        (1000.01, "suspect"),
        (5500, "suspect"),
    ],
)
def test_pm25_screening_limit_flags_but_keeps_high_values(
    value,
    expected_status,
):
    result = make_validator().validate(
        make_measurement(value=value),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.accepted is True
    assert result.quality_status == expected_status
    assert result.measurement.quality_status == expected_status
    if expected_status == "suspect":
        assert result.reasons == (
            "concentration_above_screening_limit:pm25",
        )
        assert result.measurement.value == value


@pytest.mark.parametrize(
    ("pollutant", "value", "unit"),
    [
        ("pm10", 1000.1, "µg/m³"),
        ("no2", 2000.1, "µg/m³"),
        ("so2", 2000.1, "µg/m³"),
        ("co", 100.1, "mg/m³"),
        ("o3", 2500.1, "µg/m³"),
        ("nh3", 2000.1, "µg/m³"),
        ("pb", 30.1, "µg/m³"),
    ],
)
def test_pollutant_screening_limits_are_applied(pollutant, value, unit):
    result = make_validator().validate(
        make_measurement(value=value, unit=unit),
        {"sensor-1": pollutant},
        now=NOW,
    )

    assert result.accepted is True
    assert result.quality_status == "suspect"


def test_high_reading_is_suspect_not_rejected():
    result = make_validator().validate(
        make_measurement(value=5500),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.accepted is True
    assert result.measurement.value == 5500


def test_configured_screening_limit_is_used():
    validator = make_validator(
        air_quality_high_concentration_limits={"pm25": 100}
    )
    at_limit = validator.validate(
        make_measurement(value=100),
        {"sensor-1": "pm25"},
        now=NOW,
    )
    above_limit = validator.validate(
        make_measurement(value=100.1),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert at_limit.quality_status == "valid"
    assert above_limit.quality_status == "suspect"


def test_stale_historical_measurement_is_stored_as_valid():
    old_period_end = NOW - timedelta(days=30)
    result = make_validator().validate(
        make_measurement(value=50, period_end=old_period_end),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.accepted is True
    assert result.quality_status == "valid"
    assert result.is_stale is True
    assert result.age_seconds > 3600


def test_freshness_boundary_is_not_marked_stale():
    period_end = NOW - timedelta(seconds=3600)
    result = make_validator().validate(
        make_measurement(period_end=period_end),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.is_stale is False


def test_measurement_over_freshness_boundary_is_stale():
    period_end = NOW - timedelta(seconds=3600, microseconds=1)
    result = make_validator().validate(
        make_measurement(period_end=period_end),
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.is_stale is True


def test_unknown_sensor_is_rejected_with_reason():
    result = make_validator().validate(
        make_measurement(),
        {},
        now=NOW,
    )

    assert result.accepted is False
    assert result.quality_status == "rejected"
    assert result.reasons == ("unknown_sensor",)


def test_unsupported_pollutant_is_rejected():
    result = make_validator().validate(
        make_measurement(),
        {"sensor-1": "aqi"},
        now=NOW,
    )

    assert result.accepted is False
    assert result.reasons == ("unsupported_pollutant",)


def test_unit_must_match_pollutant_standard_unit():
    result = make_validator().validate(
        make_measurement(unit="ppb"),
        {"sensor-1": "no2"},
        now=NOW,
    )

    assert result.accepted is False
    assert result.reasons == ("unsupported_unit_for_pollutant",)


@pytest.mark.parametrize(
    "coordinates",
    [
        {"latitude": 91, "longitude": 77},
        {"latitude": 28, "longitude": 181},
        {"latitude": True, "longitude": 77},
        {"latitude": 28, "longitude": float("inf")},
        {"latitude": 28},
    ],
)
def test_invalid_coordinates_are_rejected(coordinates):
    result = make_validator().validate(
        make_measurement(),
        {"sensor-1": "pm25"},
        coordinates=coordinates,
        now=NOW,
    )

    assert result.accepted is False
    assert result.reasons[0].startswith("invalid_")


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"value": None},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": -1},
        {
            "sensor_external_id": "sensor-1",
            "value": 20,
            "unit": "µg/m³",
            "original_value": 20,
            "original_unit": "µg/m³",
            "period_start": "2026-10-01T10:00:00",
            "period_end": "2026-10-01T11:00:00",
        },
        {
            "sensor_external_id": "sensor-1",
            "value": 20,
            "unit": "µg/m³",
            "original_value": 20,
            "original_unit": "µg/m³",
            "period_start": "2026-10-01T11:00:00Z",
            "period_end": "2026-10-01T10:00:00Z",
        },
    ],
)
def test_malformed_measurements_are_rejected_with_reasons(data):
    result = make_validator().validate(
        data,
        {"sensor-1": "pm25"},
        now=NOW,
    )

    assert result.accepted is False
    assert result.quality_status == "rejected"
    assert result.measurement is None
    assert result.reasons


def test_naive_validation_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        make_validator().validate(
            make_measurement(),
            {"sensor-1": "pm25"},
            now=datetime(2026, 11, 28, 8, 0),
        )
