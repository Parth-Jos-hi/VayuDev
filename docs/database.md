## Air-quality persistence

Use `AirQualityRepository` with an active SQLAlchemy transaction. The caller
owns commit and rollback; repository methods do not commit.

Stations and sensors are upserted by `(source, external_id)`. Measurements are
upserted by sensor and observation interval, so re-ingesting a corrected
observation updates its value and quality status instead of creating a
duplicate. Repository writes use the configured batch size, capped at 1,000.
Ingestion runs are started and completed through the same repository.

`AirQualityIngestionService.sync()` refreshes station and sensor discovery
before processing measurements. `discovery` only refreshes those records;
`backfill` uses the configured historical dates; `incremental` uses each
sensor's latest provider timestamp and the configured overlap. The result
reports saved, suspect, and rejected measurements with rejection reasons.

Apply migrations from the `backend` directory using
`python -m alembic upgrade head`, then run a sync with
`python -m app.jobs.sync_air_quality --job-type backfill`. Choose `discovery`,
`backfill`, or `incremental`; the job records its final status and fetched,
upserted, and rejected measurement counts.
