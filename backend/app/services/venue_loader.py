from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import batched
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert, Insert
from sqlalchemy.orm import Session

from app.db.models.venues import Venue


# ==========================================
# LOADER CONFIGURATION
# ==========================================

DEFAULT_BATCH_SIZE = 500

MAX_BATCH_SIZE = 1000

OSM_IDENTITY_CONSTRAINT = "uq_venues_osm_identity"


# ==========================================
# PERMITTED UPDATE COLUMNS
# ==========================================

UPDATE_COLUMNS: tuple[str, ...] = (
    "name",
    "category",
    "location",
    "raw_access",
    "access_type",
    "opening_hours",
    "fee",
    "operator",
    "website",
    "phone",
    "email",
    "wheelchair",
    "last_synced_at",
)


# ==========================================
# OPTIONAL METADATA PRESERVATION
# ==========================================

PRESERVE_ON_NULL_COLUMNS: tuple[str, ...] = (
    "name",
    "opening_hours",
    "fee",
    "operator",
    "website",
    "phone",
    "email",
    "wheelchair",
)


# ==========================================
# LOADING RESULT
# ==========================================

@dataclass
class VenueLoadResult:
    """Store database-loading statistics."""

    total_records: int = 0

    affected_records: int = 0

    batches_executed: int = 0


# ==========================================
# BATCH SIZE VALIDATION
# ==========================================

def validate_batch_size(
    batch_size: int,
) -> None:

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
    ):

        raise ValueError(
            "Batch size must be an integer"
        )

    if not 1 <= batch_size <= MAX_BATCH_SIZE:

        raise ValueError(
            f"Batch size must be between "
            f"1 and {MAX_BATCH_SIZE}"
        )


# ==========================================
# BATCH GENERATION
# ==========================================

def iter_venue_batches(
    records: Iterable[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Iterator[tuple[dict[str, Any], ...]]:

    validate_batch_size(batch_size)

    yield from batched(
        records,
        batch_size,
    )


# ==========================================
# POSTGRESQL UPSERT STATEMENT
# ==========================================

def build_venue_upsert(
    batch: tuple[dict[str, Any], ...],
) -> Insert:

    if not batch:

        raise ValueError(
            "Cannot build an upsert for an empty batch"
        )

    validate_batch_size(len(batch))

    table = Venue.__table__

    # Construct multi-row INSERT

    statement = insert(table).values(
        list(batch)
    )

    # Construct permitted update operations

    update_values = {}

    for column in UPDATE_COLUMNS:

        incoming_value = statement.excluded[column]

        if column in PRESERVE_ON_NULL_COLUMNS:

            update_values[column] = func.coalesce(
                incoming_value,
                table.c[column],
            )

        else:

            update_values[column] = incoming_value

    # Explicit modification timestamp

    update_values["updated_at"] = func.now()

    # Configure conflict resolution

    statement = statement.on_conflict_do_update(

        constraint=OSM_IDENTITY_CONSTRAINT,

        set_=update_values,

    )

    # Return affected venue identifiers

    statement = statement.returning(
        table.c.id
    )

    return statement


# ==========================================
# DATABASE LOADING
# ==========================================

def load_venue_records(
    session: Session,
    records: Iterable[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> VenueLoadResult:
    """Execute venue upserts inside an existing transaction."""

    validate_batch_size(batch_size)

    if not session.in_transaction():

        raise RuntimeError(
            "Venue loading requires an active transaction"
        )

    result = VenueLoadResult()

    for batch in iter_venue_batches(
        records,
        batch_size,
    ):

        statement = build_venue_upsert(batch)

        execution_result = session.execute(
            statement
        )

        affected_ids = (
            execution_result.scalars().all()
        )

        result.total_records += len(batch)

        result.affected_records += len(
            affected_ids
        )

        result.batches_executed += 1

    return result