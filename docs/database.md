## Air-quality persistence

Use `AirQualityRepository` with an active SQLAlchemy transaction. The caller
owns commit and rollback; repository methods do not commit.

Stations and sensors are upserted by `(source, external_id)`. Measurements are
upserted by sensor and observation interval, so re-ingesting a corrected
observation updates its value and quality status instead of creating a
duplicate. Repository writes use the configured batch size, capped at 1,000.
Ingestion runs are started and completed through the same repository.