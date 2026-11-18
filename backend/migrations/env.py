
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers

from app.db.base import Base
from app.db.session import engine

# Import models to register them with Base.metadata
from app.db.models.venues import Venue


# Alembic configuration
config = context.config

# Configure logging
if (
    config.config_file_name is not None
    and config.file_config.has_section("loggers")
):
    fileConfig(config.config_file_name)


# Metadata containing SQLAlchemy table definitions
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate migration SQL without a database connection."""

    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using the existing SQLAlchemy engine."""

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
