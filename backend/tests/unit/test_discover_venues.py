from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.jobs import discover_venues as job


@pytest.fixture
def dependencies(monkeypatch):
    session_factory = MagicMock()
    ingestion = MagicMock()

    monkeypatch.setattr(job, "SessionLocal", session_factory)
    monkeypatch.setattr(job, "ingest_venue_dataset", ingestion)
    monkeypatch.setattr(job, "configure_logging", MagicMock())

    return session_factory, ingestion


def test_default_arguments():
    args = job.parse_args([])

    assert args.file == job.DEFAULT_DATASET
    assert args.batch_size == 500
    assert args.log_level == "INFO"


def test_custom_arguments():
    args = job.parse_args([
        "--file", "custom.csv",
        "--batch-size", "100",
        "--log-level", "DEBUG",
    ])

    assert args.file == Path("custom.csv")
    assert args.batch_size == 100
    assert args.log_level == "DEBUG"


@pytest.mark.parametrize("args", [
    ["--batch-size", "invalid"],
    ["--log-level", "INVALID"],
    ["--unknown"],
])
def test_invalid_arguments(args):
    with pytest.raises(SystemExit) as error:
        job.parse_args(args)

    assert error.value.code == 2


@pytest.mark.parametrize("rejected", [True, False])
def test_successful_job(dependencies, rejected):
    session_factory, ingestion = dependencies

    ingestion.return_value.preparation.has_errors = rejected

    assert job.main([]) == 0

    session_factory.assert_called_once()
    ingestion.assert_called_once_with(
        session=session_factory.return_value.__enter__.return_value,
        file_path=job.DEFAULT_DATASET,
        batch_size=500,
    )

    session_factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("error, expected", [
    (RuntimeError("Database failure"), 1),
    (KeyboardInterrupt(), 130),
])
def test_failed_job(dependencies, error, expected):
    session_factory, ingestion = dependencies
    ingestion.side_effect = error

    assert job.main([]) == expected

    session_factory.return_value.__exit__.assert_called_once()