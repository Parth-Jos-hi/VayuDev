from math import isclose

from sqlalchemy import select, cast, func
from geoalchemy2 import Geometry

from app.db.session import SessionLocal
from app.db.models.venues import Venue
from app.jobs.discover_venues import DEFAULT_DATASET
from app.services.venue_ingestion_service import prepare_venue_ingestion
from app.services.venue_loader import (
    UPDATE_COLUMNS,
    PRESERVE_ON_NULL_COLUMNS,
)


def reconcile_venues(session):
    preparation = prepare_venue_ingestion(DEFAULT_DATASET)

    geometry = cast(Venue.location, Geometry("POINT", srid=4326))

    statement = select(
        Venue,
        func.ST_X(geometry),
        func.ST_Y(geometry),
    ).where(Venue.source == "osm")

    stored = {
        (venue.osm_type, venue.osm_id): (venue, longitude, latitude)
        for venue, longitude, latitude in session.execute(statement)
    }

    expected = {
        (record["osm_type"], record["osm_id"]): record
        for record in preparation.records
    }

    missing = expected.keys() - stored.keys()
    unexpected = stored.keys() - expected.keys()
    mismatches = []

    columns = [
        column for column in UPDATE_COLUMNS
        if column not in ("location", "last_synced_at")
    ]

    for identity in expected.keys() & stored.keys():
        record = expected[identity]
        venue, longitude, latitude = stored[identity]

        for column in columns:
            value = record[column]

            if value is None and column in PRESERVE_ON_NULL_COLUMNS:
                continue

            if getattr(venue, column) != value:
                mismatches.append((identity, column))

        coordinates = record["location"].data
        expected_lon, expected_lat = map(
            float, coordinates.split("(")[1].split(")")[0].split()
        )

        if (
            longitude is None
            or latitude is None
            or not isclose(longitude, expected_lon, rel_tol=0, abs_tol=1e-7)
            or not isclose(latitude, expected_lat, rel_tol=0, abs_tol=1e-7)
        ):
            mismatches.append((identity, "location"))

    print("\n--- SOURCE AND DATABASE RECONCILIATION ---")
    print(f"Expected records: {len(expected)}")
    print(f"Stored records: {len(stored)}")
    print(f"Rejected source records: {preparation.rejected_records}")
    print(f"Missing records: {len(missing)}")
    print(f"Unexpected records: {len(unexpected)}")
    print(f"Field mismatches: {len(mismatches)}")

    for identity, column in mismatches[:20]:
        print(f"Mismatch: {identity} | {column}")

    passed = not (
        missing
        or unexpected
        or mismatches
        or preparation.has_errors
    )

    print(f"\nReconciliation: {'PASS' if passed else 'FAIL'}")

    return passed


def main():
    with SessionLocal() as session:
        return 0 if reconcile_venues(session) else 1


if __name__ == "__main__":
    raise SystemExit(main())    