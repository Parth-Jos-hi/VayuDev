from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import batched
from time import perf_counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.venues import Venue

logger = get_logger(__name__)

DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1000
OSM_IDENTITY_CONSTRAINT = "uq_venues_osm_identity"

UPDATE_COLUMNS = (
    "name", "category", "location", "raw_access",
    "access_type", "opening_hours", "fee", "operator",
    "website", "phone", "email", "wheelchair",
    "last_synced_at",
)

PRESERVE_ON_NULL_COLUMNS = (
    "name", "opening_hours", "fee", "operator",
    "website", "phone", "email", "wheelchair",
)


@dataclass
class VenueLoadResult:
    total_records: int = 0
    affected_records: int = 0
    batches_executed: int = 0


def validate_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("Batch size must be an integer")

    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"Batch size must be between 1 and {MAX_BATCH_SIZE}"
        )


def iter_venue_batches(
    records: Iterable[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Iterator[tuple[dict[str, Any], ...]]:
    validate_batch_size(batch_size)
    yield from batched(records, batch_size)


def build_venue_upsert(
    batch: tuple[dict[str, Any], ...],
) -> Insert:

    if not batch:
        raise ValueError("Cannot build an upsert for an empty batch")

    validate_batch_size(len(batch))

    table = Venue.__table__
    statement = insert(table).values(list(batch))
    update_values = {}

    for column in UPDATE_COLUMNS:
        incoming = statement.excluded[column]

        if column in PRESERVE_ON_NULL_COLUMNS:
            update_values[column] = func.coalesce(
                incoming, table.c[column]
            )
        else:
            update_values[column] = incoming

    update_values["updated_at"] = func.now()

    return statement.on_conflict_do_update(
        constraint=OSM_IDENTITY_CONSTRAINT,
        set_=update_values,
    ).returning(table.c.id)


def load_venue_records(
    session: Session,
    records: Iterable[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> VenueLoadResult:

    validate_batch_size(batch_size)

    if not session.in_transaction():
        raise RuntimeError(
            "Venue loading requires an active transaction"
        )

    result = VenueLoadResult()

    for number, batch in enumerate(
        iter_venue_batches(records, batch_size), start=1
    ):
        started_at = perf_counter()
        statement = build_venue_upsert(batch)

        affected = len(
            session.execute(statement).scalars().all()
        )

        result.total_records += len(batch)
        result.affected_records += affected
        result.batches_executed += 1

        logger.info(
            "event=batch_executed batch=%d records=%d "
            "affected=%d duration_seconds=%.3f",
            number,
            len(batch),
            affected,
            perf_counter() - started_at,
        )

    return result