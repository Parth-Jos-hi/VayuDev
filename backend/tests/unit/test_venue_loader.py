from datetime import UTC, datetime
from unittest.mock import MagicMock
import re

import pytest

from sqlalchemy.dialects import postgresql

from app.schemas.venues import VenueIngestionSchema

from app.services.venue_transformer import (
    transform_venue_record,
)

from app.services.venue_loader import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    OSM_IDENTITY_CONSTRAINT,
    UPDATE_COLUMNS,
    PRESERVE_ON_NULL_COLUMNS,
    validate_batch_size,
    iter_venue_batches,
    build_venue_upsert,
    load_venue_records,
)


# ==========================================
# TEST DATA FACTORY
# ==========================================

def make_record(osm_id=100):

    venue = VenueIngestionSchema.model_validate({
        "osm_type": "node",
        "osm_id": osm_id,
        "name": "Test Library",
        "category": "library",
        "latitude": 28.61,
        "longitude": 77.20,
    })

    return transform_venue_record(
        venue=venue,
        synced_at=datetime.now(UTC),
    )


def compile_statement(statement):

    return str(
        statement.compile(
            dialect=postgresql.dialect()
        )
    ).lower()


# ==========================================
# CONFIGURATION TESTS
# ==========================================

def test_default_batch_size():

    assert DEFAULT_BATCH_SIZE == 500


def test_conflict_constraint():

    assert OSM_IDENTITY_CONSTRAINT == (
        "uq_venues_osm_identity"
    )


# ==========================================
# BATCH SIZE VALIDATION
# ==========================================

@pytest.mark.parametrize(
    "size",
    [
        1,
        100,
        500,
        MAX_BATCH_SIZE,
    ],
)
def test_valid_batch_size(size):

    validate_batch_size(size)


@pytest.mark.parametrize(
    "size",
    [
        0,
        -1,
        True,
        False,
        1.5,
        "500",
        None,
        MAX_BATCH_SIZE + 1,
    ],
)
def test_invalid_batch_size(size):

    with pytest.raises(ValueError):

        validate_batch_size(size)


# ==========================================
# BATCH GENERATION
# ==========================================

@pytest.mark.parametrize(
    "count,size,expected",
    [
        (0, 500, []),
        (1, 500, [1]),
        (500, 500, [500]),
        (501, 500, [500, 1]),
        (1000, 500, [500, 500]),
        (2539, 500, [500, 500, 500, 500, 500, 39]),
    ],
)
def test_batch_sizes(count, size, expected):

    records = [
        {"osm_id": number}
        for number in range(count)
    ]

    batches = list(
        iter_venue_batches(records, size)
    )

    assert [
        len(batch)
        for batch in batches
    ] == expected


def test_batching_preserves_order():

    records = [
        {"osm_id": number}
        for number in range(10)
    ]

    batches = iter_venue_batches(
        records,
        3,
    )

    flattened = [
        record
        for batch in batches
        for record in batch
    ]

    assert flattened == records


def test_generator_input():

    records = (
        {"osm_id": number}
        for number in range(5)
    )

    batches = list(
        iter_venue_batches(records, 2)
    )

    assert [
        len(batch)
        for batch in batches
    ] == [2, 2, 1]


# ==========================================
# UPSERT STATEMENT CONSTRUCTION
# ==========================================

def test_empty_batch_rejected():

    with pytest.raises(ValueError):

        build_venue_upsert(())


def test_upsert_statement():

    statement = build_venue_upsert(
        (make_record(),)
    )

    sql = compile_statement(statement)

    assert "insert into" in sql

    assert "on conflict on constraint" in sql

    assert "uq_venues_osm_identity" in sql

    assert "do update set" in sql

    assert "excluded" in sql

    assert "returning" in sql


def test_multiple_record_statement():

    statement = build_venue_upsert(
        (
            make_record(100),
            make_record(200),
        )
    )

    sql = compile_statement(statement)

    assert "osm_id_m0" in sql

    assert "osm_id_m1" in sql


# ==========================================
# PROTECTED COLUMN VALIDATION
# ==========================================

@pytest.mark.parametrize(
    "column",
    [
        "id",
        "osm_type",
        "osm_id",
        "source",
        "address",
        "created_at",
        "verification_priority",
        "verification_status",
        "public_access_verified",
        "indoor_space_verified",
        "air_conditioning_verified",
        "emergency_access_verified",
        "last_verified",
        "verification_source",
        "verification_notes",
    ],
)
def test_protected_columns(column):

    assert column not in UPDATE_COLUMNS

    statement = build_venue_upsert(
        (make_record(),)
    )

    sql = compile_statement(statement)

    update_clause = (
        sql.split("do update set", 1)[1]
        .split("returning", 1)[0]
    )

    pattern = rf"\b{re.escape(column)}\s*="

    assert re.search(
        pattern,
        update_clause,
    ) is None


# ==========================================
# OPTIONAL METADATA PRESERVATION
# ==========================================

def test_nullable_metadata_preservation():

    statement = build_venue_upsert(
        (make_record(),)
    )

    sql = compile_statement(statement)

    for column in PRESERVE_ON_NULL_COLUMNS:

        assert (
            f"coalesce(excluded.{column}"
            in sql
        )


def test_updated_at_explicitly_assigned():

    statement = build_venue_upsert(
        (make_record(),)
    )

    sql = compile_statement(statement)

    assert "updated_at = now()" in sql


# ==========================================
# MOCK DATABASE LOADING
# ==========================================

def test_empty_record_loading():

    session = MagicMock()

    session.in_transaction.return_value = True

    result = load_venue_records(
        session,
        [],
    )

    assert result.total_records == 0

    assert result.affected_records == 0

    assert result.batches_executed == 0

    session.execute.assert_not_called()


def test_loading_requires_transaction():

    session = MagicMock()

    session.in_transaction.return_value = False

    with pytest.raises(
        RuntimeError,
        match="active transaction",
    ):

        load_venue_records(
            session,
            [],
        )


def test_batch_loading():

    session = MagicMock()

    session.in_transaction.return_value = True

    session.execute.return_value.scalars.return_value.all.side_effect = [
        ["uuid-1", "uuid-2"],
        ["uuid-3"],
    ]

    records = [
        make_record(100),
        make_record(200),
        make_record(300),
    ]

    result = load_venue_records(
        session=session,
        records=records,
        batch_size=2,
    )

    assert result.total_records == 3

    assert result.affected_records == 3

    assert result.batches_executed == 2

    assert session.execute.call_count == 2

    session.commit.assert_not_called()

    session.rollback.assert_not_called()


def test_loading_failure_propagates():

    session = MagicMock()

    session.in_transaction.return_value = True

    session.execute.side_effect = RuntimeError(
        "Database execution failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Database execution failed",
    ):

        load_venue_records(
            session=session,
            records=[make_record()],
        )

    session.commit.assert_not_called()

    session.rollback.assert_not_called()