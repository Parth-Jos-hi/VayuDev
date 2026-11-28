from collections.abc import Iterator
from datetime import datetime, time, timedelta, timezone

from app.core.config import Settings


def incremental_windows(
    synced_through: datetime | None,
    now: datetime,
    config: Settings,
) -> Iterator[tuple[datetime, datetime]]:
    end = now.astimezone(timezone.utc)
    if synced_through is not None:
        if synced_through > end:
            return
        start = synced_through
    else:
        start = datetime.combine(config.air_quality_historical_end, time.min, timezone.utc)
        if start >= end:
            start = end - timedelta(days=1)

    start -= timedelta(seconds=config.incremental_overlap_seconds)
    while start < end:
        stop = min(start + timedelta(days=7), end)
        yield start, stop
        start = stop
