from sqlalchemy import select, func, cast, or_
from geoalchemy2 import Geometry

from app.db.session import SessionLocal
from app.db.models.venues import Venue
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

EXPECTED_COUNT = 2539

EXPECTED_CATEGORIES = {
    "school": 1112,
    "hospital": 659,
    "clinic": 518,
    "community_centre": 112,
    "library": 70,
    "university": 35,
    "public_building": 33,
}


def get_distribution(session, column):
    statement = (
        select(column, func.count())
        .where(Venue.source == "osm")
        .group_by(column)
    )
    return dict(session.execute(statement).all())


def verify_venues(session) -> bool:
    osm_filter = Venue.source == "osm"

    total = session.scalar(
        select(func.count())
        .select_from(Venue)
        .where(osm_filter)
    )

    duplicates = (
        select(Venue.osm_type, Venue.osm_id)
        .where(osm_filter)
        .group_by(Venue.osm_type, Venue.osm_id)
        .having(func.count() > 1)
        .subquery()
    )

    duplicate_count = session.scalar(
        select(func.count()).select_from(duplicates)
    )

    geometry = cast(
        Venue.location,
        Geometry("POINT", srid=4326),
    )

    invalid_locations = session.scalar(
        select(func.count())
        .select_from(Venue)
        .where(
            osm_filter,
            or_(
                Venue.location.is_(None),
                func.ST_IsEmpty(geometry),
                ~func.ST_X(geometry).between(-180, 180),
                ~func.ST_Y(geometry).between(-90, 90),
                func.ST_SRID(geometry) != 4326,
            ),
        )
    )

    missing_identities = session.scalar(
        select(func.count())
        .select_from(Venue)
        .where(
            osm_filter,
            or_(
                Venue.osm_id.is_(None),
                Venue.osm_type.is_(None),
            ),
        )
    )

    categories = get_distribution(session, Venue.category)
    access = get_distribution(session, Venue.access_type)
    verification = get_distribution(
        session, Venue.verification_status
    )

    checks = {
        "Record count": total == EXPECTED_COUNT,
        "Category distribution": categories == EXPECTED_CATEGORIES,
        "Duplicate identities": duplicate_count == 0,
        "Missing identities": missing_identities == 0,
        "Invalid locations": invalid_locations == 0,
    }

    print("\n--- DATABASE VERIFICATION ---")
    print(f"Total OSM venues: {total}")
    print(f"Duplicate identities: {duplicate_count}")
    print(f"Missing identities: {missing_identities}")
    print(f"Invalid locations: {invalid_locations}")

    for title, distribution in (
        ("CATEGORY", categories),
        ("ACCESS TYPE", access),
        ("VERIFICATION STATUS", verification),
    ):
        print(f"\n--- {title} DISTRIBUTION ---")

        for key, count in sorted(distribution.items()):
            print(f"{key:<25} {count}")

    print("\n--- VALIDATION RESULTS ---")

    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    return all(checks.values())


def main() -> int:
    configure_logging()

    try:
        with SessionLocal() as session:
            passed = verify_venues(session)

        return 0 if passed else 1

    except Exception as error:
        logger.error(
            "event=verification_failed error_type=%s",
            type(error).__name__,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())