from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.integrations.venue_dataset import (
    VenueDatasetError,
    read_venue_dataset,
)
from app.schemas.venues import VenueIngestionSchema
from app.services.venue_transformer import transform_venue_record
from app.services.venue_loader import (
    DEFAULT_BATCH_SIZE,
    VenueLoadResult,
    load_venue_records,
    validate_batch_size,
)

logger = get_logger(__name__)

OSMIdentity = tuple[str, int]
IngestionStage = Literal["validation", "duplicate"]


@dataclass(frozen=True)
class IngestionIssue:
    record_number: int
    stage: IngestionStage
    message: str


@dataclass
class IngestionResult:
    synced_at: datetime
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[IngestionIssue] = field(default_factory=list)

    @property
    def transformed_records(self) -> int:
        return len(self.records)

    @property
    def rejected_records(self) -> int:
        return self.invalid_records + self.duplicate_records

    @property
    def has_errors(self) -> bool:
        return self.rejected_records > 0


@dataclass
class VenueIngestionRunResult:
    preparation: IngestionResult
    loading: VenueLoadResult


def format_validation_error(error: ValidationError) -> str:
    messages = []

    for detail in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(map(str, detail["loc"])) or "record"
        messages.append(f"{location}: {detail['msg']}")

    return "; ".join(messages)


def prepare_venue_ingestion(
    file_path: str | Path,
    synced_at: datetime | None = None,
) -> IngestionResult:

    started_at = perf_counter()

    if synced_at is None:
        synced_at = datetime.now(UTC)

    if synced_at.tzinfo is None or synced_at.utcoffset() is None:
        raise ValueError(
            "Synchronization timestamp must be timezone-aware"
        )

    result = IngestionResult(synced_at=synced_at.astimezone(UTC))
    seen_identities: set[OSMIdentity] = set()

    logger.info("event=preparation_started")

    with closing(read_venue_dataset(file_path)) as dataset:
        for record_number, row in dataset:
            result.total_records += 1

            try:
                venue = VenueIngestionSchema.model_validate(row)

            except ValidationError as error:
                result.invalid_records += 1

                result.issues.append(
                    IngestionIssue(
                        record_number,
                        "validation",
                        format_validation_error(error),
                    )
                )

                logger.warning(
                    "event=validation_failed record=%d",
                    record_number,
                )
                continue

            result.valid_records += 1
            identity = (venue.osm_type, venue.osm_id)

            if identity in seen_identities:
                result.duplicate_records += 1

                result.issues.append(
                    IngestionIssue(
                        record_number,
                        "duplicate",
                        f"Duplicate OSM identity: "
                        f"{venue.osm_type}/{venue.osm_id}",
                    )
                )

                logger.warning(
                    "event=duplicate_record record=%d osm_type=%s osm_id=%d",
                    record_number,
                    venue.osm_type,
                    venue.osm_id,
                )
                continue

            result.records.append(
                transform_venue_record(venue, result.synced_at)
            )
            seen_identities.add(identity)

    logger.info(
        "event=preparation_completed total=%d transformed=%d "
        "invalid=%d duplicates=%d duration_seconds=%.3f",
        result.total_records,
        result.transformed_records,
        result.invalid_records,
        result.duplicate_records,
        perf_counter() - started_at,
    )

    return result


def ingest_venue_dataset(
    session: Session,
    file_path: str | Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    synced_at: datetime | None = None,
) -> VenueIngestionRunResult:

    validate_batch_size(batch_size)

    if session.in_transaction():
        raise RuntimeError(
            "Venue ingestion requires a session "
            "without an active transaction"
        )

    started_at = perf_counter()

    logger.info(
        "event=ingestion_started batch_size=%d",
        batch_size,
    )

    try:
        preparation = prepare_venue_ingestion(file_path, synced_at)

        with session.begin():
            loading = load_venue_records(
                session=session,
                records=preparation.records,
                batch_size=batch_size,
            )

    except VenueDatasetError as error:
        logger.error(
            "event=dataset_failed error_type=%s",
            type(error).__name__,
        )
        raise

    except SQLAlchemyError as error:
        logger.error(
            "event=database_failed error_type=%s",
            type(error).__name__,
        )
        raise

    except Exception as error:
        logger.error(
            "event=ingestion_failed error_type=%s",
            type(error).__name__,
        )
        raise

    logger.info(
        "event=ingestion_completed affected=%d batches=%d "
        "rejected=%d duration_seconds=%.3f",
        loading.affected_records,
        loading.batches_executed,
        preparation.rejected_records,
        perf_counter() - started_at,
    )

    return VenueIngestionRunResult(preparation, loading)