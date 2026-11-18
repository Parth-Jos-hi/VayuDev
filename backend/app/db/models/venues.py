from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, Text, UUID as SQLAlchemyUUID, func
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from app.db.base import Base
class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    category: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    location: Mapped[WKBElement] = mapped_column(
        Geography(
            geometry_type="POINT",
            srid=4326,
            spatial_index=True
        ),
        nullable=False
    )
    access_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown"
    )
    verification_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
