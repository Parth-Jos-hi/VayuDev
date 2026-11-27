import csv
import logging
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from app.integrations.venue_dataset import (
    EXPECTED_COLUMNS,
    DatasetPathError,
)
from app.services import venue_ingestion_service as service
from app.services.venue_loader import (
    VenueLoadResult,
    load_venue_records,
)


@pytest.fixture
def dataset(tmp_path):
    path = tmp_path / "venues.csv"

    row = dict.fromkeys(EXPECTED_COLUMNS, "")
    row.update({
        "osm_type": "node",
        "osm_id": "100",
        "name": "Test Library",
        "category": "library",
        "latitude": "28.61",
        "longitude": "77.20",
        "access_classification": "unknown",
        "verification_priority": "medium",
        "verification_status": "pending",
        "public_access_verified": "unknown",
        "indoor_space_verified": "unknown",
        "air_conditioning_verified": "unknown",
        "emergency_access_verified": "unknown",
    })

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerow(row)
        writer.writerow(row)
        writer.writerow({**row, "latitude": "100"})

    return path


def test_named_logger():
    logger = get_logger("vayudev.test")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "vayudev.test"


def test_preparation_logs(dataset, caplog):
    with caplog.at_level(logging.INFO):
        result = service.prepare_venue_ingestion(dataset)

    assert result.total_records == 3
    assert result.transformed_records == 1
    assert result.invalid_records == 1
    assert result.duplicate_records == 1

    assert "event=preparation_started" in caplog.text
    assert "event=preparation_completed" in caplog.text
    assert "event=duplicate_record" in caplog.text
    assert "event=validation_failed" in caplog.text
    assert "duration_seconds=" in caplog.text


def test_dataset_failure(tmp_path, caplog):
    session = MagicMock()
    session.in_transaction.return_value = False

    with pytest.raises(DatasetPathError):
        service.ingest_venue_dataset(
            session, tmp_path / "missing.csv"
        )

    assert "event=dataset_failed" in caplog.text
    assert "event=ingestion_completed" not in caplog.text
    session.begin.assert_not_called()


def test_successful_ingestion(dataset, monkeypatch, caplog):
    session = MagicMock()
    session.in_transaction.return_value = False

    loader = MagicMock(
        return_value=VenueLoadResult(
            total_records=1,
            affected_records=1,
            batches_executed=1,
        )
    )

    monkeypatch.setattr(service, "load_venue_records", loader)

    with caplog.at_level(logging.INFO):
        result = service.ingest_venue_dataset(session, dataset)

    assert result.loading.affected_records == 1
    assert "event=ingestion_completed" in caplog.text
    session.begin.assert_called_once()


def test_database_failure(dataset, monkeypatch, caplog):
    session = MagicMock()
    session.in_transaction.return_value = False

    loader = MagicMock(
        side_effect=SQLAlchemyError("sensitive database details")
    )

    monkeypatch.setattr(service, "load_venue_records", loader)

    with pytest.raises(SQLAlchemyError):
        service.ingest_venue_dataset(session, dataset)

    assert "event=database_failed" in caplog.text
    assert "event=ingestion_completed" not in caplog.text
    assert "sensitive database details" not in caplog.text


def test_unexpected_failure(dataset, monkeypatch, caplog):
    session = MagicMock()
    session.in_transaction.return_value = False

    monkeypatch.setattr(
        service,
        "load_venue_records",
        MagicMock(side_effect=RuntimeError("Unexpected failure")),
    )

    with pytest.raises(RuntimeError):
        service.ingest_venue_dataset(session, dataset)

    assert "event=ingestion_failed" in caplog.text


def test_batch_logging(dataset, caplog):
    preparation = service.prepare_venue_ingestion(dataset)

    session = MagicMock()
    session.in_transaction.return_value = True
    session.execute.return_value.scalars.return_value.all.return_value = [
        "test-uuid"
    ]

    with caplog.at_level(logging.INFO):
        result = load_venue_records(session, preparation.records)

    assert result.batches_executed == 1
    assert "event=batch_executed" in caplog.text
    assert "batch=1" in caplog.text
    assert "affected=1" in caplog.text