# Air quality

Requests use the existing Supabase bearer token. The endpoints read stored observations from PostgreSQL.

| GET path under `/api/v1/air-quality` | Query parameters | Response |
| --- | --- | --- |
| `/stations` | `limit`, `offset` | Stored stations |
| `/stations/{id}` | | One station by UUID |
| `/stations/{id}/sensors` | `pollutant`, `limit`, `offset` | Sensors at the station |
| `/stations/{id}/latest` | `pollutant` | One latest valid observation per pollutant |
| `/stations/{id}/measurements` | `from_at`, `to_at`, `pollutant`, `aggregation_type`, `limit`, `offset` | Historical observations and their quality flags |
| `/status` | `limit`, `offset` | Observation counts, earliest stored period, age of the latest valid observation and freshness by station |

Supply historical bounds as ISO 8601 timestamps with offsets. The filter uses the observation's period start, includes `from_at`, and excludes `to_at`. Each range can cover up to 31 days. History defaults to 1,000 rows per page and accepts at most 10,000. Other paginated endpoints default to 100 rows and accept at most 1,000.
