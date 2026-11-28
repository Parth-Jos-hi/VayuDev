import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides):
    values = {
        "database_url": "postgresql://test:test@localhost/test",
        "supabase_url": "https://example.supabase.co",
        "supabase_jwt_issuer": "https://example.supabase.co/auth/v1",
        "supabase_jwks_url": (
            "https://example.supabase.co/auth/v1/.well-known/jwks.json"
        ),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_air_quality_defaults_load_successfully():
    settings = make_settings()

    assert settings.openaq_base_url == "https://api.openaq.org"
    assert settings.supported_pollutants == ["pm25", "pm10"]
    assert settings.openaq_max_request_budget == 1000
    assert settings.study_region_north > settings.study_region_south


def test_supported_pollutants_accepts_comma_separated_values():
    settings = make_settings(supported_pollutants="pm25, no2,co")

    assert settings.supported_pollutants == ["pm25", "no2", "co"]


def test_unsupported_pollutant_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(supported_pollutants=["pm25", "methane"])


def test_invalid_study_region_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(study_region_south=29.0, study_region_north=28.5)


def test_historical_end_cannot_precede_start():
    with pytest.raises(ValidationError):
        make_settings(
            air_quality_historical_start="2026-11-01",
            air_quality_historical_end="2026-10-01",
        )


def test_api_key_is_optional_for_configuration_loading():
    settings = make_settings(openaq_api_key=None)

    assert settings.openaq_api_key is None
