from datetime import date
import math
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


DEFAULT_AIR_QUALITY_HIGH_CONCENTRATION_LIMITS = {
    "pm25": 1000.0,
    "pm10": 1000.0,
    "no2": 2000.0,
    "so2": 2000.0,
    "co": 100.0,
    "o3": 2500.0,
    "nh3": 2000.0,
    "pb": 30.0,
}
MAX_INGESTION_BATCH_SIZE = 1000


class Settings(BaseSettings):
    name: str = "VayuDev"
    version: str = "0.1"
    debug: bool = Field(default=False)
    environment: str = Field(default="development")

    database_url: SecretStr
    supabase_url: str
    supabase_jwt_issuer: str
    supabase_jwks_url: str

    # OpenAQ credentials and HTTP behavior
    openaq_api_key: SecretStr | None = None
    openaq_base_url: str = "https://api.openaq.org"
    openaq_http_timeout_seconds: float = Field(default=30.0, gt=0)
    openaq_max_retries: int = Field(default=3, ge=0)
    openaq_retry_backoff_seconds: float = Field(default=1.0, ge=0)
    openaq_page_limit: int = Field(default=100, gt=0, le=1000)
    openaq_max_request_budget: int = Field(default=1000, gt=0)

    # The default region is Delhi, but every boundary can be changed by
    # environment variables without changing application code.
    study_region_south: float = Field(default=28.40, ge=-90, le=90)
    study_region_north: float = Field(default=28.90, ge=-90, le=90)
    study_region_west: float = Field(default=76.80, ge=-180, le=180)
    study_region_east: float = Field(default=77.35, ge=-180, le=180)

    supported_pollutants: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["pm25", "pm10"]
    )
    air_quality_historical_start: date = date(2026, 10, 1)
    air_quality_historical_end: date = date(2026, 11, 1)

    # Operational limits and freshness rules
    ingestion_batch_size: int = Field(
        default=500,
        gt=0,
        le=MAX_INGESTION_BATCH_SIZE,
    )
    air_quality_freshness_seconds: int = Field(default=3600, gt=0)
    incremental_overlap_seconds: int = Field(default=900, ge=0)
    air_quality_high_concentration_limits: dict[str, float] = Field(
        default_factory=lambda: DEFAULT_AIR_QUALITY_HIGH_CONCENTRATION_LIMITS.copy()
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("openaq_base_url")
    @classmethod
    def validate_openaq_base_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("OPENAQ_BASE_URL must start with http:// or https://")
        return value

    @field_validator("supported_pollutants", mode="before")
    @classmethod
    def parse_supported_pollutants(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return value

    @field_validator("supported_pollutants")
    @classmethod
    def validate_supported_pollutants(cls, value: list[str]) -> list[str]:
        allowed = {"pm25", "pm10", "no2", "so2", "co", "o3", "nh3", "pb"}
        invalid = sorted(set(value) - allowed)
        if invalid:
            raise ValueError(
                f"Unsupported air quality pollutants: {', '.join(invalid)}"
            )
        return list(dict.fromkeys(value))

    @field_validator(
        "air_quality_high_concentration_limits",
        mode="before",
    )
    @classmethod
    def reject_boolean_high_limits(cls, value: object) -> object:
        if isinstance(value, dict) and any(
            isinstance(limit, bool) for limit in value.values()
        ):
            raise ValueError("High concentration limits cannot be boolean")
        return value

    @field_validator("air_quality_high_concentration_limits")
    @classmethod
    def validate_high_concentration_limits(
        cls,
        value: dict[str, float],
    ) -> dict[str, float]:
        unknown = set(value) - set(DEFAULT_AIR_QUALITY_HIGH_CONCENTRATION_LIMITS)
        if unknown:
            raise ValueError(
                f"Unknown pollutants in high concentration limits: "
                f"{', '.join(sorted(unknown))}"
            )

        limits = DEFAULT_AIR_QUALITY_HIGH_CONCENTRATION_LIMITS | value
        if any(
            isinstance(limit, bool)
            or not math.isfinite(limit)
            or limit < 0
            for limit in limits.values()
        ):
            raise ValueError(
                "High concentration limits must be finite and nonnegative"
            )
        return limits

    @model_validator(mode="after")
    def validate_study_region_and_dates(self) -> "Settings":
        if self.study_region_north <= self.study_region_south:
            raise ValueError(
                "STUDY_REGION_NORTH must be greater than STUDY_REGION_SOUTH"
            )
        if self.study_region_east <= self.study_region_west:
            raise ValueError(
                "STUDY_REGION_EAST must be greater than STUDY_REGION_WEST"
            )
        if self.air_quality_historical_end < self.air_quality_historical_start:
            raise ValueError(
                "AIR_QUALITY_HISTORICAL_END must not precede "
                "AIR_QUALITY_HISTORICAL_START"
            )
        return self


settings = Settings()