from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Pollutant = Literal["pm25", "pm10", "no2", "so2", "co", "o3", "nh3", "pb"]
DataSource = Literal["openaq", "cpcb"]
AggregationType = Literal["raw", "hourly", "daily"]
MeasurementQuality = Literal["valid", "suspect", "rejected"]


class SchemaBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class StationIngestion(SchemaBase):
    source: DataSource
    external_id: str = Field(min_length=1)
    name: str | None = None
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    locality: str | None = None
    provider_name: str | None = None
    is_mobile: bool = False

    @field_validator("name", "locality", "provider_name", mode="before")
    @classmethod
    def empty_text_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def reject_boolean_coordinates(cls, value):
        if isinstance(value, bool):
            raise ValueError("Coordinates cannot be boolean values")
        return value


class SensorIngestion(SchemaBase):
    source: DataSource
    external_id: str = Field(min_length=1)
    station_external_id: str = Field(min_length=1)
    pollutant: Pollutant
    original_unit: str = Field(min_length=1)
    is_active: bool = True

    @field_validator("pollutant", mode="before")
    @classmethod
    def normalize_pollutant(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


class MeasurementIngestion(SchemaBase):
    sensor_external_id: str = Field(min_length=1)
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1)
    original_value: float = Field(ge=0, allow_inf_nan=False)
    original_unit: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    aggregation_type: AggregationType = "raw"
    quality_status: MeasurementQuality = "valid"

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be later than period_start")
        return self

    @field_validator("period_start", "period_end")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Measurement timestamps must include timezone information")
        return value.astimezone(timezone.utc)


class StationResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    source: DataSource
    external_id: str
    name: str | None
    latitude: float
    longitude: float
    country_code: str | None
    locality: str | None
    provider_name: str | None
    is_mobile: bool
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SensorResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    station_id: UUID
    source: DataSource
    external_id: str
    pollutant: Pollutant
    original_unit: str
    is_active: bool
    last_measurement_at: datetime | None
    last_synced_at: datetime | None


class MeasurementResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    sensor_id: UUID
    value: float
    unit: str
    original_value: float
    original_unit: str
    period_start: datetime
    period_end: datetime
    aggregation_type: AggregationType
    quality_status: MeasurementQuality
    ingested_at: datetime


class LatestObservationResponse(SchemaBase):
    station_id: UUID
    station_name: str | None
    pollutant: Pollutant
    value: float
    unit: str
    period_start: datetime
    period_end: datetime
    quality_status: MeasurementQuality


class HistoricalMeasurementQuery(SchemaBase):
    from_at: datetime
    to_at: datetime
    pollutant: Pollutant | None = None
    aggregation_type: AggregationType | None = None
    limit: int = Field(default=1000, ge=1, le=10000)

    @field_validator("from_at", "to_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Query timestamps must include timezone information")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_range(self):
        if self.to_at <= self.from_at:
            raise ValueError("to_at must be later than from_at")
        return self


class FreshnessCoverageResponse(SchemaBase):
    station_id: UUID
    latest_measurement_at: datetime | None
    age_seconds: int | None = Field(default=None, ge=0)
    is_fresh: bool
    measurement_count: int = Field(ge=0)
