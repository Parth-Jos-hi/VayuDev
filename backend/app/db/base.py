from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Table,Column,UUID
class Base(DeclarativeBase):
    pass
auth_users = Table(
    "users",
    Base.metadata,
    Column("id",UUID(as_uuid=True),primary_key=True),
    schema = "auth",
    info = {"external":True},       
)   