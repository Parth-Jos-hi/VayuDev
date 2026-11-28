from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.jobs import sync_air_quality
from app.ingestion.air_quality.station_discovery import DiscoveryStats
from app.services.air_quality_service import AirQualityIngestionResult


def test_backfill_accepts_pilot_options():
    options = sync_air_quality.parse_args([
        "--job-type", "backfill", "--start", "2026-10-02", "--end", "2026-10-03",
        "--pollutants", "pm25", "--station-limit", "5", "--request-budget", "100",
    ])
    assert options.config.air_quality_historical_start.isoformat() == "2026-10-02"
    assert options.config.supported_pollutants == ["pm25"]
    assert options.config.openaq_max_request_budget == 100
    assert options.station_limit == 5


def test_invalid_budget_is_rejected_before_running():
    with pytest.raises(SystemExit) as error:
        sync_air_quality.parse_args(["--job-type", "incremental", "--request-budget", "0"])
    assert error.value.code == 2


@pytest.mark.parametrize(
    ("sync_error", "expected_status", "expected_exit_code"),
    [
        (None, "success", 0),
        (None, "partial", 0),
        (RuntimeError("provider unavailable"), "failed", 1),
    ],
)
def test_job_records_run_and_closes_provider(
    monkeypatch,
    sync_error,
    expected_status,
    expected_exit_code,
):
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    run = SimpleNamespace(id=uuid4())
    repository = MagicMock()
    repository.start_ingestion_run.return_value = run
    service = MagicMock()
    rejected = int(expected_status == "partial")
    service.sync.return_value = AirQualityIngestionResult(
        job_type="backfill",
        discovery_stats=DiscoveryStats(),
        measurements_fetched=5,
        measurements_upserted=4,
        measurements_rejected=rejected,
    )
    if sync_error is not None:
        service.sync.side_effect = sync_error
    provider = MagicMock()

    monkeypatch.setattr(sync_air_quality, "SessionLocal", lambda: session_context)
    monkeypatch.setattr(
        sync_air_quality,
        "AirQualityRepository",
        MagicMock(return_value=repository),
    )
    monkeypatch.setattr(
        sync_air_quality,
        "AirQualityIngestionService",
        MagicMock(return_value=service),
    )
    monkeypatch.setattr(sync_air_quality, "OpenAQClient", lambda **kwargs: provider)
    monkeypatch.setattr(
        sync_air_quality,
        "configure_logging",
        MagicMock(),
    )

    exit_code = sync_air_quality.main(["--job-type", "backfill"])

    assert exit_code == expected_exit_code
    repository.finish_ingestion_run.assert_called_once()
    assert (
        repository.finish_ingestion_run.call_args.kwargs["status"]
        == expected_status
    )
    provider.close.assert_called_once()

    if sync_error is None:
        counts = repository.finish_ingestion_run.call_args.kwargs["counts"]
        assert counts == {
            "records_fetched": 5,
            "records_upserted": 4,
            "records_skipped": 0,
            "records_rejected": rejected,
        }
