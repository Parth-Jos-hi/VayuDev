import csv
from uuid import uuid4

import pytest
from sqlalchemy import select, func, cast
from geoalchemy2 import Geometry

from app.db.models.venues import Venue
from app.integrations.venue_dataset import (
    EXPECTED_COLUMNS,
    DatasetRowError,
)
from app.services.venue_ingestion_service import ingest_venue_dataset


def make_row(**overrides):
    row = dict.fromkeys(EXPECTED_COLUMNS, "")
    row.update({
        "osm_type": "node",
        "osm_id": str(uuid4().int % 10**18 + 1),
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
    row.update(overrides)
    return row


def create_dataset(tmp_path, rows):
    path = tmp_path / "venues.csv"

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return path


def get_venue(session, osm_id):
    return session.scalar(
        select(Venue).where(
            Venue.osm_type == "node",
            Venue.osm_id == int(osm_id),
        )
    )


def test_complete_pipeline(db_session, tmp_path):
    row = make_row(
        name="Central Library",
        access="yes",
        access_classification="explicitly_permitted",
        opening_hours="09:00-18:00",
    )
    path = create_dataset(tmp_path, [row])

    result = ingest_venue_dataset(db_session, path)
    venue = get_venue(db_session, row["osm_id"])

    assert result.preparation.transformed_records == 1
    assert result.loading.affected_records == 1
    assert venue is not None
    assert venue.name == row["name"]
    assert venue.category == row["category"]
    assert venue.raw_access == row["access"]
    assert venue.access_type == row["access_classification"]
    assert venue.opening_hours == row["opening_hours"]
    assert venue.source == "osm"
    assert venue.verification_status == "pending"


def test_spatial_accuracy(db_session, tmp_path):
    row = make_row(latitude="28.5084497", longitude="77.166546")
    path = create_dataset(tmp_path, [row])

    ingest_venue_dataset(db_session, path)

    geometry = cast(Venue.location, Geometry("POINT", srid=4326))

    longitude, latitude, srid = db_session.execute(
        select(
            func.ST_X(geometry),
            func.ST_Y(geometry),
            func.ST_SRID(geometry),
        ).where(
            Venue.osm_type == "node",
            Venue.osm_id == int(row["osm_id"]),
        )
    ).one()

    assert latitude == pytest.approx(float(row["latitude"]))
    assert longitude == pytest.approx(float(row["longitude"]))
    assert srid == 4326


def test_mixed_dataset(db_session, tmp_path):
    first = make_row()
    second = make_row()
    invalid = make_row(latitude="100")

    path = create_dataset(tmp_path, [
        first,
        invalid,
        first.copy(),
        second,
    ])

    result = ingest_venue_dataset(
        db_session, path, batch_size=1
    )

    assert result.preparation.total_records == 4
    assert result.preparation.invalid_records == 1
    assert result.preparation.duplicate_records == 1
    assert result.preparation.transformed_records == 2
    assert result.loading.affected_records == 2
    assert result.loading.batches_executed == 2

    assert get_venue(db_session, first["osm_id"]) is not None
    assert get_venue(db_session, second["osm_id"]) is not None
    assert get_venue(db_session, invalid["osm_id"]) is None


def test_repeated_synchronization(db_session, tmp_path):
    row = make_row(name="Old Library")
    path = create_dataset(tmp_path, [row])

    ingest_venue_dataset(db_session, path)

    original_id = get_venue(db_session, row["osm_id"]).id
    db_session.commit()

    row["name"] = "Updated Library"
    path = create_dataset(tmp_path, [row])

    ingest_venue_dataset(db_session, path)

    venue = get_venue(db_session, row["osm_id"])

    assert venue.id == original_id
    assert venue.name == "Updated Library"

    count = db_session.scalar(
        select(func.count()).select_from(Venue).where(
            Venue.osm_type == "node",
            Venue.osm_id == int(row["osm_id"]),
        )
    )

    assert count == 1


def test_malformed_dataset_no_writes(db_session, tmp_path):
    row = make_row()
    path = create_dataset(tmp_path, [row])

    with path.open("a", encoding="utf-8") as file:
        file.write("node,123\n")

    with pytest.raises(DatasetRowError):
        ingest_venue_dataset(db_session, path)

    assert get_venue(db_session, row["osm_id"]) is None


def test_empty_dataset(db_session, tmp_path):
    path = create_dataset(tmp_path, [])

    result = ingest_venue_dataset(db_session, path)

    assert result.preparation.total_records == 0
    assert result.loading.affected_records == 0
    assert result.loading.batches_executed == 0