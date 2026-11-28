from unittest.mock import MagicMock

import pytest

from app.db.repositories.air_quality import AirQualityRepository


@pytest.mark.parametrize(
    "batch_size",
    [0, -1, True, 1.5, "10", 1001],
)
def test_invalid_batch_size_is_rejected(batch_size):
    with pytest.raises(ValueError, match="Batch size"):
        AirQualityRepository(MagicMock(), batch_size=batch_size)


def test_repository_writes_require_a_transaction():
    session = MagicMock()
    session.in_transaction.return_value = False

    with pytest.raises(RuntimeError, match="active transaction"):
        AirQualityRepository(session).upsert_stations([])

    session.execute.assert_not_called()


def test_sensor_lookup_rejects_an_unsupported_source():
    session = MagicMock()
    repository = AirQualityRepository(session)

    with pytest.raises(ValueError, match="Unsupported"):
        repository.get_sensor_pollutants("unknown")

    session.execute.assert_not_called()
