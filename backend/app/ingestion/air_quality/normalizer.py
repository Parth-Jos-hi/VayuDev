from datetime import datetime, timezone
import math
from typing import Any

from app.schemas.air_quality import MeasurementIngestion, Pollutant


class MeasurementNormalizationError(ValueError):
    pass


POLLUTANT_NAMES = {
    "pm25": "pm25",
    "pm2.5": "pm25",
    "pm2_5": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "nitrogen dioxide": "no2",
    "so2": "so2",
    "sulfur dioxide": "so2",
    "sulphur dioxide": "so2",
    "co": "co",
    "carbon monoxide": "co",
    "o3": "o3",
    "ozone": "o3",
    "nh3": "nh3",
    "ammonia": "nh3",
    "pb": "pb",
    "lead": "pb",
}

# OpenAQ parameter IDs observed in the project research data.
POLLUTANT_IDS = {
    1: "pm10",
    2: "pm25",
    3: "o3",
    4: "co",
    5: "no2",
    6: "so2",
    15: "no2",
    101: "so2",
    102: "co",
}


class MeasurementNormalizer:
    def normalize(
        self,
        record: dict[str, Any],
        sensor_external_id: str,
        aggregation_type: str = "raw",
        expected_pollutant: Pollutant | None = None,
    ) -> MeasurementIngestion:
        if not isinstance(record, dict):
            raise MeasurementNormalizationError(
                "Measurement must be a JSON object"
            )
        if not sensor_external_id:
            raise MeasurementNormalizationError(
                "Sensor external ID is required"
            )

        parameter = record.get("parameter")
        if not isinstance(parameter, dict):
            raise MeasurementNormalizationError(
                "Measurement parameter object is required"
            )

        pollutant = self._pollutant(parameter)
        if expected_pollutant is not None and pollutant != expected_pollutant:
            raise MeasurementNormalizationError(
                "Measurement pollutant does not match its sensor"
            )
        value = record.get("value")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise MeasurementNormalizationError(
                "Measurement value must be a finite number"
            )

        original_unit = parameter.get("units")
        if not isinstance(original_unit, str) or not original_unit.strip():
            raise MeasurementNormalizationError(
                "Measurement unit is required"
            )
        normalized_value, unit = self._convert_unit(
            float(value),
            original_unit,
            pollutant,
        )

        period = record.get("period")
        if not isinstance(period, dict):
            raise MeasurementNormalizationError(
                "Measurement period is required"
            )
        start = self._period_datetime(period, "datetimeFrom")
        end = self._period_datetime(period, "datetimeTo")
        if end <= start:
            raise MeasurementNormalizationError(
                "Measurement end time must be later than start time"
            )

        try:
            return MeasurementIngestion.model_validate(
                {
                    "sensor_external_id": sensor_external_id,
                    "value": normalized_value,
                    "unit": unit,
                    "original_value": float(value),
                    "original_unit": original_unit,
                    "period_start": start,
                    "period_end": end,
                    "aggregation_type": aggregation_type,
                }
            )
        except ValueError as error:
            raise MeasurementNormalizationError(
                "Measurement does not match the internal data contract"
            ) from error

    @staticmethod
    def _pollutant(parameter: dict[str, Any]) -> str:
        name = parameter.get("name")
        if isinstance(name, str) and name.strip():
            pollutant = POLLUTANT_NAMES.get(name.strip().lower())
            if pollutant is None:
                raise MeasurementNormalizationError(
                    f"Unsupported pollutant name: {name}"
                )
            return pollutant

        parameter_id = parameter.get("id")
        if isinstance(parameter_id, int) and not isinstance(parameter_id, bool):
            pollutant = POLLUTANT_IDS.get(parameter_id)
            if pollutant is not None:
                return pollutant

        raise MeasurementNormalizationError(
            "Measurement has no recognized pollutant name or parameter ID"
        )

    @staticmethod
    def _convert_unit(
        value: float,
        original_unit: str,
        pollutant: str,
    ) -> tuple[float, str]:
        unit = (
            original_unit.strip()
            .lower()
            .replace("μ", "µ")
            .replace("³", "3")
            .replace("^", "")
            .replace(" ", "")
        )

        if unit in {"µg/m3", "ug/m3"}:
            if pollutant == "co":
                return value / 1000, "mg/m³"
            return value, "µg/m³"

        if unit in {"mg/m3"}:
            if pollutant == "co":
                return value, "mg/m³"
            return value * 1000, "µg/m³"

        if unit in {"g/m3"}:
            if pollutant == "co":
                return value * 1000, "mg/m³"
            return value * 1_000_000, "µg/m³"

        raise MeasurementNormalizationError(
            f"Unsupported concentration unit: {original_unit}"
        )

    @classmethod
    def _period_datetime(cls, period: dict[str, Any], field: str) -> datetime:
        value = period.get(field)
        if not isinstance(value, dict):
            raise MeasurementNormalizationError(
                f"Measurement period is missing {field}"
            )

        timestamp = value.get("utc") or value.get("local")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise MeasurementNormalizationError(
                f"Measurement period {field} has no timestamp"
            )

        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise MeasurementNormalizationError(
                f"Measurement period {field} has an invalid timestamp"
            ) from error

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise MeasurementNormalizationError(
                f"Measurement period {field} must include timezone information"
            )
        return parsed.astimezone(timezone.utc)
