from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.jobs import sync_air_quality
from app.ingestion.air_quality.station_discovery import DiscoveryStats
from app.services.air_quality_service import AirQualityIngestionResult


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
        job_type="discovery",
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
    monkeypatch.setattr(sync_air_quality, "OpenAQClient", lambda: provider)
    monkeypatch.setattr(
        sync_air_quality,
        "configure_logging",
        MagicMock(),
    )

    exit_code = sync_air_quality.main(["--job-type", "discovery"])

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
            "records_rejected": rejected,
        }
