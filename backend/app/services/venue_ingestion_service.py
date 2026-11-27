from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.integrations.venue_dataset import read_venue_dataset

from app.schemas.venues import VenueIngestionSchema

from app.services.venue_transformer import transform_venue_record

from app.services.venue_loader import (
    DEFAULT_BATCH_SIZE,
    VenueLoadResult,
    load_venue_records,
    validate_batch_size,
)


# ==========================================
# INGESTION TYPE ALIASES
# ==========================================

OSMIdentity = tuple[str, int]

IngestionStage = Literal[
    "validation",
    "duplicate",
]


# ==========================================
# INGESTION ISSUE
# ==========================================

@dataclass(frozen=True)
class IngestionIssue:
    """Represent an individual rejected dataset record."""

    record_number: int

    stage: IngestionStage

    message: str


# ==========================================
# INGESTION PREPARATION RESULT
# ==========================================

@dataclass
class IngestionResult:
    """Store the results of venue ingestion preparation."""

    synced_at: datetime

    total_records: int = 0

    valid_records: int = 0

    invalid_records: int = 0

    duplicate_records: int = 0

    records: list[dict[str, Any]] = field(
        default_factory=list
    )

    issues: list[IngestionIssue] = field(
        default_factory=list
    )

    @property
    def transformed_records(self) -> int:

        return len(self.records)

    @property
    def rejected_records(self) -> int:

        return (
            self.invalid_records
            + self.duplicate_records
        )

    @property
    def has_errors(self) -> bool:

        return self.rejected_records > 0


# ==========================================
# COMPLETE INGESTION RESULT
# ==========================================

@dataclass
class VenueIngestionRunResult:
    """Represent a completed venue ingestion operation."""

    preparation: IngestionResult

    loading: VenueLoadResult


# ==========================================
# VALIDATION ERROR FORMATTING
# ==========================================

def format_validation_error(
    error: ValidationError,
) -> str:
    """Convert Pydantic errors into readable messages."""

    messages: list[str] = []

    for detail in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):

        location = ".".join(
            str(part)
            for part in detail["loc"]
        )

        location = location or "record"

        message = detail["msg"]

        messages.append(
            f"{location}: {message}"
        )

    return "; ".join(messages)


# ==========================================
# VENUE INGESTION PREPARATION SERVICE
# ==========================================

def prepare_venue_ingestion(
    file_path: str | Path,
    synced_at: datetime | None = None,
) -> IngestionResult:
    """Read, validate and transform a venue dataset."""

    # ======================================
    # INITIALIZE SYNCHRONIZATION TIMESTAMP
    # ======================================

    if synced_at is None:

        synced_at = datetime.now(UTC)

    if (
        synced_at.tzinfo is None
        or synced_at.utcoffset() is None
    ):

        raise ValueError(
            "Synchronization timestamp must be timezone-aware"
        )

    synced_at = synced_at.astimezone(UTC)

    # ======================================
    # INITIALIZE PROCESSING STATE
    # ======================================

    result = IngestionResult(
        synced_at=synced_at
    )

    seen_identities: set[OSMIdentity] = set()

    # ======================================
    # READ DATASET RECORDS
    # ======================================

    with closing(
        read_venue_dataset(file_path)
    ) as dataset:

        for record_number, row in dataset:

            result.total_records += 1

            # ==============================
            # VALIDATE INDIVIDUAL RECORD
            # ==============================

            try:

                venue = (
                    VenueIngestionSchema.model_validate(
                        row
                    )
                )

            except ValidationError as error:

                result.invalid_records += 1

                result.issues.append(
                    IngestionIssue(
                        record_number=record_number,
                        stage="validation",
                        message=format_validation_error(
                            error
                        ),
                    )
                )

                continue

            result.valid_records += 1

            # ==============================
            # DETECT DUPLICATE OSM IDENTITIES
            # ==============================

            identity: OSMIdentity = (
                venue.osm_type,
                venue.osm_id,
            )

            if identity in seen_identities:

                result.duplicate_records += 1

                result.issues.append(
                    IngestionIssue(
                        record_number=record_number,
                        stage="duplicate",
                        message=(
                            "Duplicate OSM identity: "
                            f"{venue.osm_type}/"
                            f"{venue.osm_id}"
                        ),
                    )
                )

                continue

            # ==============================
            # TRANSFORM VALID VENUE
            # ==============================

            transformed = transform_venue_record(
                venue=venue,
                synced_at=synced_at,
            )

            # ==============================
            # STORE PROCESSING RESULT
            # ==============================

            result.records.append(
                transformed
            )

            seen_identities.add(
                identity
            )

    # ======================================
    # RETURN FINAL PREPARATION RESULT
    # ======================================

    return result


# ==========================================
# COMPLETE VENUE INGESTION SERVICE
# ==========================================

def ingest_venue_dataset(
    session: Session,
    file_path: str | Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    synced_at: datetime | None = None,
) -> VenueIngestionRunResult:
    """Prepare and atomically load a venue dataset."""

    # ======================================
    # VALIDATE LOADER CONFIGURATION
    # ======================================

    validate_batch_size(batch_size)

    # ======================================
    # ENSURE TRANSACTION OWNERSHIP
    # ======================================

    if session.in_transaction():

        raise RuntimeError(
            "Venue ingestion requires a session "
            "without an active transaction"
        )

    # ======================================
    # PREPARE DATASET
    # ======================================

    preparation = prepare_venue_ingestion(
        file_path=file_path,
        synced_at=synced_at,
    )

    # ======================================
    # ATOMIC DATABASE LOADING
    # ======================================

    with session.begin():

        loading = load_venue_records(
            session=session,
            records=preparation.records,
            batch_size=batch_size,
        )

    # ======================================
    # RETURN COMPLETE INGESTION RESULT
    # ======================================

    return VenueIngestionRunResult(
        preparation=preparation,
        loading=loading,
    )