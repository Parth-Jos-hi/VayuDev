from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Text,
    UUID as SQLAlchemyUUID,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(
            Text,
            nullable=True,
        )    
    role:Mapped[str] = mapped_column(
        Text,
        nullable = False,
        server_default = text("'user'"),
    )
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        server_default = func.now(),
        nullable = False,
    )
    updated_at:Mapped[datetime] = mapped_column(
            DateTime(timezone = True),
            server_default = func.now(),
            onupdate = func.now(),
            nullable = False,
        )