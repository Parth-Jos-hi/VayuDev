from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:

    connection = engine.connect()
    transaction = connection.begin()

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield db

    finally:
        try:
            db.close()

        finally:
            try:
                if transaction.is_active:
                    transaction.rollback()

            finally:
                connection.close()