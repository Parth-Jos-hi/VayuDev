import csv

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.db.models.venues import Venue

from app.integrations.venue_dataset import (
    EXPECTED_COLUMNS,
)

from app.schemas.venues import VenueIngestionSchema

from app.services.venue_transformer import (
    transform_venue_record,
)

from app.services.venue_loader import (
    load_venue_records,
)

from app.services.venue_ingestion_service import (
    ingest_venue_dataset,
)


# ==========================================
# TEST IDENTIFIER GENERATION
# ==========================================

def unique_osm_id():

    return (
        uuid4().int % 9_000_000_000_000_000_000
    ) + 1


# ==========================================
# TRANSFORMED RECORD FACTORY
# ==========================================

def make_record(osm_id, **overrides):

    data = {
        "osm_type": "node",
        "osm_id": osm_id,
        "name": "Test Library",
        "category": "library",
        "latitude": 28.61,
        "longitude": 77.20,
    }

    data.update(overrides)

    venue = VenueIngestionSchema.model_validate(
        data
    )

    return transform_venue_record(
        venue=venue,
        synced_at=datetime.now(UTC),
    )


# ==========================================
# TEMPORARY DATASET FACTORY
# ==========================================

def create_dataset(tmp_path, osm_ids):

    path = tmp_path / "venues.csv"

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=EXPECTED_COLUMNS,
        )

        writer.writeheader()

        for osm_id in osm_ids:

            row = {
                column: ""
                for column in EXPECTED_COLUMNS
            }

            row.update({
                "osm_type": "node",
                "osm_id": osm_id,
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

            writer.writerow(row)

    return path


# ==========================================
# SUCCESSFUL DATABASE INSERTION
# ==========================================

def test_successful_insertion(db_session):

    osm_id = unique_osm_id()

    record = make_record(osm_id)

    with db_session.begin():

        result = load_venue_records(
            db_session,
            [record],
        )

    assert result.total_records == 1

    assert result.affected_records == 1

    assert result.batches_executed == 1

    venue = db_session.scalar(
        select(Venue).where(
            Venue.osm_type == "node",
            Venue.osm_id == osm_id,
        )
    )

    assert venue is not None

    assert venue.name == "Test Library"

    assert venue.source == "osm"

    assert venue.id is not None

    assert venue.location is not None


# ==========================================
# IDEMPOTENT UPSERT
# ==========================================

def test_repeated_ingestion(db_session):

    osm_id = unique_osm_id()

    record = make_record(osm_id)

    with db_session.begin():

        load_venue_records(
            db_session,
            [record],
        )

        original_id = db_session.scalar(
            select(Venue.id).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        )

        load_venue_records(
            db_session,
            [record],
        )

        venues = db_session.scalars(
            select(Venue).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        ).all()

        assert len(venues) == 1

        assert venues[0].id == original_id


# ==========================================
# UPDATE EXISTING METADATA
# ==========================================

def test_metadata_updated(db_session):

    osm_id = unique_osm_id()

    original = make_record(
        osm_id,
        name="Old Library",
    )

    incoming = make_record(
        osm_id,
        name="New Library",
        opening_hours="09:00-19:00",
    )

    with db_session.begin():

        load_venue_records(
            db_session,
            [original],
        )

        load_venue_records(
            db_session,
            [incoming],
        )

        venue = db_session.scalar(
            select(Venue).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        )

        assert venue.name == "New Library"

        assert venue.opening_hours == (
            "09:00-19:00"
        )


# ==========================================
# OPTIONAL METADATA PRESERVATION
# ==========================================

def test_null_metadata_preserved(db_session):

    osm_id = unique_osm_id()

    original = make_record(
        osm_id,
        name="Existing Library",
        phone="+91 1234567890",
    )

    incoming = make_record(
        osm_id,
        name=None,
        phone=None,
    )

    with db_session.begin():

        load_venue_records(
            db_session,
            [original],
        )

        load_venue_records(
            db_session,
            [incoming],
        )

        venue = db_session.scalar(
            select(Venue).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        )

        assert venue.name == "Existing Library"

        assert venue.phone == "+91 1234567890"


# ==========================================
# VERIFICATION DATA PROTECTION
# ==========================================

def test_verification_data_preserved(db_session):

    osm_id = unique_osm_id()

    original = make_record(osm_id)

    verified_at = datetime.now(UTC)

    with db_session.begin():

        load_venue_records(
            db_session,
            [original],
        )

        db_session.execute(
            update(Venue)
            .where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
            .values(
                verification_status="verified",
                verification_priority="high",
                public_access_verified="yes",
                indoor_space_verified="yes",
                air_conditioning_verified="yes",
                emergency_access_verified="yes",
                verification_notes="Manual inspection",
                verification_source="manual",
                last_verified=verified_at,
                address="Verified address",
            )
        )

        incoming = make_record(
            osm_id,
            name="Updated Library",
        )

        load_venue_records(
            db_session,
            [incoming],
        )

        venue = db_session.scalar(
            select(Venue).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        )

        assert venue.name == "Updated Library"

        assert venue.verification_status == "verified"

        assert venue.verification_priority == "high"

        assert venue.public_access_verified == "yes"

        assert venue.indoor_space_verified == "yes"

        assert venue.air_conditioning_verified == "yes"

        assert venue.emergency_access_verified == "yes"

        assert venue.verification_notes == (
            "Manual inspection"
        )

        assert venue.verification_source == "manual"

        assert venue.last_verified == verified_at

        assert venue.address == "Verified address"


# ==========================================
# ACCESS CLASSIFICATION SYNCHRONIZATION
# ==========================================

def test_missing_access_information_updates(
    db_session,
):

    osm_id = unique_osm_id()

    original = make_record(
        osm_id,
        access="yes",
        access_classification="explicitly_permitted",
    )

    incoming = make_record(
        osm_id,
        access=None,
        access_classification="unknown",
    )

    with db_session.begin():

        load_venue_records(
            db_session,
            [original],
        )

        load_venue_records(
            db_session,
            [incoming],
        )

        venue = db_session.scalar(
            select(Venue).where(
                Venue.osm_type == "node",
                Venue.osm_id == osm_id,
            )
        )

        assert venue.raw_access is None

        assert venue.access_type == "unknown"


# ==========================================
# COMPOSITE OSM IDENTITY
# ==========================================

def test_composite_identity(db_session):

    osm_id = unique_osm_id()

    records = [
        make_record(
            osm_id,
            osm_type="node",
        ),
        make_record(
            osm_id,
            osm_type="way",
        ),
        make_record(
            osm_id,
            osm_type="relation",
        ),
    ]

    with db_session.begin():

        result = load_venue_records(
            db_session,
            records,
        )

        count = db_session.scalar(
            select(func.count())
            .select_from(Venue)
            .where(
                Venue.osm_id == osm_id
            )
        )

        assert count == 3

        assert result.affected_records == 3


# ==========================================
# MULTIPLE BATCH EXECUTION
# ==========================================

def test_multiple_batches(db_session):

    records = [
        make_record(unique_osm_id())
        for _ in range(5)
    ]

    with db_session.begin():

        result = load_venue_records(
            db_session,
            records,
            batch_size=2,
        )

    assert result.total_records == 5

    assert result.affected_records == 5

    assert result.batches_executed == 3


# ==========================================
# ATOMIC TRANSACTION ROLLBACK
# ==========================================

def test_failed_batch_rolls_back_all_batches(
    db_session,
):

    first_id = unique_osm_id()

    second_id = unique_osm_id()

    first = make_record(first_id)

    second = make_record(second_id)

    # Intentionally trigger a database
    # constraint violation.

    second["category"] = "invalid_category"

    with pytest.raises(IntegrityError):

        with db_session.begin():

            load_venue_records(
                db_session,
                [first, second],
                batch_size=1,
            )

    count = db_session.scalar(
        select(func.count())
        .select_from(Venue)
        .where(
            Venue.osm_type == "node",
            Venue.osm_id.in_([
                first_id,
                second_id,
            ]),
        )
    )

    assert count == 0


# ==========================================
# COMPLETE ETL WORKFLOW
# ==========================================

def test_complete_ingestion(
    db_session,
    tmp_path,
):

    osm_ids = [
        unique_osm_id()
        for _ in range(3)
    ]

    path = create_dataset(
        tmp_path,
        osm_ids,
    )

    result = ingest_venue_dataset(
        session=db_session,
        file_path=path,
        batch_size=2,
    )

    assert result.preparation.total_records == 3

    assert result.preparation.transformed_records == 3

    assert result.preparation.rejected_records == 0

    assert result.loading.total_records == 3

    assert result.loading.affected_records == 3

    assert result.loading.batches_executed == 2

    count = db_session.scalar(
        select(func.count())
        .select_from(Venue)
        .where(
            Venue.osm_type == "node",
            Venue.osm_id.in_(osm_ids),
        )
    )

    assert count == 3


# ==========================================
# TRANSACTION OWNERSHIP
# ==========================================

def test_existing_transaction_rejected(
    db_session,
    tmp_path,
):

    path = create_dataset(
        tmp_path,
        [unique_osm_id()],
    )

    with db_session.begin():

        with pytest.raises(
            RuntimeError,
            match="without an active transaction",
        ):

            ingest_venue_dataset(
                session=db_session,
                file_path=path,
            )