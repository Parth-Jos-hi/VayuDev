from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Literal

from pydantic import ValidationError

from app.core.config import Settings, settings
from app.schemas.air_quality import MeasurementIngestion


QualityStatus = Literal["valid", "suspect", "rejected"]

STANDARD_UNITS = {
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "no2": "µg/m³",
    "so2": "µg/m³",
    "co": "mg/m³",
    "o3": "µg/m³",
    "nh3": "µg/m³",
    "pb": "µg/m³",
}


@dataclass(frozen=True)
class MeasurementValidationResult:
    accepted: bool
    measurement: MeasurementIngestion | None
    quality_status: QualityStatus
    reasons: tuple[str, ...]
    is_stale: bool
    age_seconds: float | None


class AirQualityMeasurementValidator:
    def __init__(self, config: Settings = settings):
        self.config = config
        self.high_limits = config.air_quality_high_concentration_limits

    def validate(
        self,
        measurement: MeasurementIngestion | dict[str, Any],
        sensor_pollutants: Mapping[str, str],
        coordinates: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> MeasurementValidationResult:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include timezone information")
        now = now.astimezone(timezone.utc)

        try:
            if isinstance(measurement, MeasurementIngestion):
                measurement = MeasurementIngestion.model_validate(
                    measurement.model_dump()
                )
            else:
                measurement = MeasurementIngestion.model_validate(measurement)
        except ValidationError as error:
            reasons = tuple(
                self._validation_reason(item)
                for item in error.errors(include_input=False)
            )
            return self._rejected(reasons)

        sensor_external_id = measurement.sensor_external_id
        pollutant = sensor_pollutants.get(sensor_external_id)
        if pollutant is None:
            return self._rejected(("unknown_sensor",))
        if not isinstance(pollutant, str):
            return self._rejected(("unsupported_pollutant",))

        pollutant = pollutant.strip().lower()
        if pollutant not in STANDARD_UNITS:
            return self._rejected(("unsupported_pollutant",))

        if measurement.unit != STANDARD_UNITS[pollutant]:
            return self._rejected(
                ("unsupported_unit_for_pollutant",)
            )

        coordinate_error = self._coordinate_error(coordinates)
        if coordinate_error is not None:
            return self._rejected((coordinate_error,))

        reasons: list[str] = []
        quality_status: QualityStatus = "valid"
        high_limit = self.high_limits[pollutant]
        if measurement.value > high_limit:
            quality_status = "suspect"
            reasons.append(
                f"concentration_above_screening_limit:{pollutant}"
            )

        age_seconds = max(
            0.0,
            (now - measurement.period_end).total_seconds(),
        )
        return MeasurementValidationResult(
            accepted=True,
            measurement=measurement.model_copy(
                update={"quality_status": quality_status}
            ),
            quality_status=quality_status,
            reasons=tuple(reasons),
            is_stale=(
                age_seconds > self.config.air_quality_freshness_seconds
            ),
            age_seconds=age_seconds,
        )

    @staticmethod
    def _validation_reason(error: dict[str, Any]) -> str:
        field = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        return f"invalid_measurement:{field}:{message}"

    @staticmethod
    def _coordinate_error(
        coordinates: Mapping[str, Any] | None,
    ) -> str | None:
        if coordinates is None:
            return None
        if not isinstance(coordinates, Mapping):
            return "invalid_coordinates"

        latitude = coordinates.get("latitude")
        longitude = coordinates.get("longitude")
        if not AirQualityMeasurementValidator._valid_coordinate(
            latitude,
            -90,
            90,
        ):
            return "invalid_latitude"
        if not AirQualityMeasurementValidator._valid_coordinate(
            longitude,
            -180,
            180,
        ):
            return "invalid_longitude"
        return None

    @staticmethod
    def _valid_coordinate(
        value: Any,
        minimum: float,
        maximum: float,
    ) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and minimum <= value <= maximum
        )

    @staticmethod
    def _rejected(
        reasons: tuple[str, ...],
    ) -> MeasurementValidationResult:
        return MeasurementValidationResult(
            accepted=False,
            measurement=None,
            quality_status="rejected",
            reasons=reasons,
            is_stale=False,
            age_seconds=None,
        )
