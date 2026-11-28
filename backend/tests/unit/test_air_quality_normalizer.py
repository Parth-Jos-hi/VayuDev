from datetime import datetime, timezone

import pytest

from app.ingestion.air_quality.normalizer import (
    MeasurementNormalizationError,
    MeasurementNormalizer,
)


def make_record(
    pollutant="pm25",
    value=40.5,
    unit="µg/m³",
    start="2026-10-01T04:30:00Z",
    end="2026-10-01T05:30:00Z",
):
    return {
        "value": value,
        "parameter": {
            "id": 2,
            "name": pollutant,
            "units": unit,
        },
        "period": {
            "label": "1hour",
            "interval": "01:00:00",
            "datetimeFrom": {"utc": start, "local": "2026-10-01T10:00:00+05:30"},
            "datetimeTo": {"utc": end, "local": "2026-10-01T11:00:00+05:30"},
        },
    }


def test_normalizes_open_aq_period_to_utc():
    record = make_record(
        start="2026-10-01T10:00:00+05:30",
        end="2026-10-01T11:00:00+05:30",
    )

    measurement = MeasurementNormalizer().normalize(record, "sensor-1")

    assert measurement.period_start == datetime(
        2026, 10, 1, 4, 30, tzinfo=timezone.utc
    )
    assert measurement.period_end == datetime(
        2026, 10, 1, 5, 30, tzinfo=timezone.utc
    )


def test_uses_local_timestamp_when_utc_is_not_available():
    record = make_record()
    record["period"]["datetimeFrom"] = {
        "local": "2026-10-01T10:00:00+05:30"
    }
    record["period"]["datetimeTo"] = {
        "local": "2026-10-01T11:00:00+05:30"
    }

    measurement = MeasurementNormalizer().normalize(record, "sensor-1")

    assert measurement.period_start == datetime(
        2026, 10, 1, 4, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pm25", "pm25"),
        ("PM2.5", "pm25"),
        ("pm2_5", "pm25"),
        ("pm10", "pm10"),
        ("nitrogen dioxide", "no2"),
        ("sulphur dioxide", "so2"),
        ("carbon monoxide", "co"),
        ("ozone", "o3"),
        ("ammonia", "nh3"),
        ("lead", "pb"),
    ],
)
def test_maps_supported_pollutant_names(name, expected):
    record = make_record(pollutant=name)

    measurement = MeasurementNormalizer().normalize(record, "sensor-1")

    assert measurement.unit == ("mg/m³" if expected == "co" else "µg/m³")


def test_maps_open_aq_parameter_id_when_name_is_missing():
    record = make_record()
    record["parameter"]["name"] = None
    record["parameter"]["id"] = 102
    record["parameter"]["units"] = "µg/m³"

    measurement = MeasurementNormalizer().normalize(record, "sensor-1")

    assert measurement.value == pytest.approx(0.0405)
    assert measurement.unit == "mg/m³"


@pytest.mark.parametrize(
    ("pollutant", "value", "unit", "expected_value", "expected_unit"),
    [
        ("co", 1200, "µg/m³", 1.2, "mg/m³"),
        ("pm25", 1.2, "mg/m³", 1200, "µg/m³"),
        ("so2", 0.001, "g/m³", 1000, "µg/m³"),
        ("co", 0.001, "g/m³", 1, "mg/m³"),
    ],
)
def test_converts_supported_mass_concentrations(
    pollutant,
    value,
    unit,
    expected_value,
    expected_unit,
):
    record = make_record(pollutant=pollutant, value=value, unit=unit)

    measurement = MeasurementNormalizer().normalize(record, "sensor-1")

    assert measurement.value == pytest.approx(expected_value)
    assert measurement.unit == expected_unit
    assert measurement.original_value == value
    assert measurement.original_unit == unit


def test_retains_aggregation_type():
    measurement = MeasurementNormalizer().normalize(
        make_record(),
        "sensor-1",
        aggregation_type="hourly",
    )

    assert measurement.aggregation_type == "hourly"


def test_rejects_measurement_for_a_different_sensor_pollutant():
    with pytest.raises(
        MeasurementNormalizationError,
        match="does not match its sensor",
    ):
        MeasurementNormalizer().normalize(
            make_record(pollutant="pm10"),
            "sensor-1",
            expected_pollutant="pm25",
        )


@pytest.mark.parametrize("unit", ["ppb", "ppm", "%", ""])
def test_rejects_units_without_safe_conversion(unit):
    with pytest.raises(MeasurementNormalizationError, match="unit"):
        MeasurementNormalizer().normalize(
            make_record(unit=unit),
            "sensor-1",
        )


def test_does_not_treat_aqi_as_a_pollutant_concentration():
    with pytest.raises(MeasurementNormalizationError, match="pollutant"):
        MeasurementNormalizer().normalize(
            make_record(pollutant="aqi"),
            "sensor-1",
        )


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"value": None},
        {"value": True},
        make_record(value=float("nan")),
        {**make_record(), "parameter": {"name": "pm25"}},
        {**make_record(), "period": {}},
        make_record(start="2026-10-01T10:00:00"),
        make_record(end="not-a-timestamp"),
        make_record(start="2026-10-01T05:30:00Z", end="2026-10-01T04:30:00Z"),
    ],
)
def test_rejects_malformed_measurements(record):
    with pytest.raises(MeasurementNormalizationError):
        MeasurementNormalizer().normalize(record, "sensor-1")
