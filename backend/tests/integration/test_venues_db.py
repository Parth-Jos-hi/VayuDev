from uuid import uuid4
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import engine
from app.db.models.venues import Venue
def test_venue_database_crud():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection)
    try:
        venue = Venue(
            name=f"VayuDev Test Venue {uuid4()}",
            category="library",
            address="Demo address",
            location=WKTElement("POINT(77.20 28.61)", srid=4326),
            access_type="unknown",
            verification_status="pending",
        )
        db.add(venue)
        db.flush()
        venue_id = venue.id
        result = db.get(Venue, venue_id)
        assert result is not None
        assert result.name == venue.name
        result.name = "Updated VayuDev Test Venue"
        db.flush()
        db.expire_all()
        updated = db.get(Venue, venue_id)
        assert updated is not None
        assert updated.name == "Updated VayuDev Test Venue"
        db.delete(updated)
        db.flush()
        db.expire_all()
        deleted = db.execute(
            select(Venue).where(Venue.id == venue_id)
        ).scalar_one_or_none()
        assert deleted is None
    finally:
        # Always clean up, even if an assertion fails
        db.close()
        transaction.rollback()
        connection.close()
