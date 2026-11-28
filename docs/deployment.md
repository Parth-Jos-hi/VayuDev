# Manual air quality jobs

Run from the `backend` directory in PowerShell. Apply the sensor checkpoint migration before using these commands. Discovery, backfill and incremental sync use the OpenAQ key from `.env`. The report uses only the database.

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.jobs.sync_air_quality --job-type discovery
..\.venv\Scripts\python.exe -m app.jobs.sync_air_quality --job-type backfill --start 2026-10-01 --end 2026-11-01 --pollutants pm25,pm10 --station-limit 5 --request-budget 100
..\.venv\Scripts\python.exe -m app.jobs.sync_air_quality --job-type incremental --request-budget 100
..\.venv\Scripts\python.exe -m app.jobs.sync_air_quality --job-type report
```

Discovery registers sensors. Incremental sync reads registered fixed stations in the configured region, including sensors that have gone quiet. For a sensor's first run it starts from the configured historical end in UTC and applies the same overlap used on later runs. If that date is still ahead, the starting point is 24 hours before the run.

Each successful window commits its measurements and checkpoint together. The checkpoint says how far the provider was queried. The last measurement timestamp says when the latest stored reading ended. If a sensor's checkpoint is 08:00 UTC and the overlap is 15 minutes, its next window includes readings ending after 07:45 UTC. A delayed 07:50 reading can then be inserted, and a corrected 07:55 reading can replace the original. An identical reading counts as skipped. An empty response can move the checkpoint forward while the stored observation stays stale.

If a window fails, the next run retries it from the last committed checkpoint. OpenAQ authentication failures, exhausted request budgets and rate limits stop the run early. The report records the run status and recent counts. A partial run logged by the CLI can be retried with the same command. The historical gap estimate compares distinct hourly observations with the configured period for currently active sensors, including hours when a sensor may have been offline.

## Where to read the code

| File | Concept to follow |
| --- | --- |
| `incremental_loader.py` | UTC windows and overlapping reads. OpenAQ's latest resource can miss late arrivals. [OpenAQ hourly measurements](https://docs.openaq.org/api/operations/sensor_hourly_measurements_get_v3_sensors__sensors_id__hours_get) · [OpenAQ latest limitations](https://docs.openaq.org/resources/latest) |
| `openaq.py` | Incomplete pagination fails the window so the next run can retry it. [OpenAQ pagination](https://docs.openaq.org/using-the-api/pagination) |
| `air_quality.py` in `db/models` and the sensor checkpoint migration | The nullable checkpoint gives existing rows a safe initial state. The migration rebuilds the cached observation timestamp from stored rows. [Alembic operations](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.add_column) |
| `air_quality.py` in `db/repositories` and `air_quality_service.py` | Building on Stage 3 upserts, the observation identity stays the same while a changed value or quality flag updates the row. Each window is a transaction so a failed checkpoint rolls back its measurements. [SQLAlchemy PostgreSQL upserts](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert) · [Session transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#managing-transactions) |
| `sync_air_quality.py` and `air_quality_report.py` | CLI argument validation, run statuses and counts. For coverage, a missing hourly reading contributes zero rows. [Python argparse](https://docs.python.org/3/library/argparse.html#the-parse-args-method) · [PostgreSQL aggregate functions](https://www.postgresql.org/docs/current/functions-aggregate.html) |
| `air_quality_reads.py` in `db/repositories` and `services` | Temporal filters and deterministic ordering select the latest valid reading per pollutant. Freshness is derived at read time. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html#SQL-DISTINCT) |
| `air_quality.py` in `schemas` and `api`, and `main.py` | Query models validate filters before database reads. The router applies bearer authentication and response schemas. [FastAPI query parameter models](https://fastapi.tiangolo.com/tutorial/query-param-models/) · [Router dependencies](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies) |
| `test_air_quality_service.py`, `test_sync_air_quality_job.py`, `test_air_quality.py`, `test_air_quality_ingestion.py` | Fakes test failure branches, while the integration test uses a mocked HTTP transport and real PostgreSQL writes. [HTTPX mock transports](https://www.python-httpx.org/advanced/transports/#mock-transports) · [FastAPI testing dependencies](https://fastapi.tiangolo.com/advanced/testing-dependencies/) |

Run `..\.venv\Scripts\python.exe -m pytest -q` with `DATABASE_URL` pointing to a migrated, isolated PostgreSQL/PostGIS test database. The integration test checks duplicate handling, a corrected observation, rollback after a checkpoint failure and the serialized API responses.
