from types import SimpleNamespace

import pytest

from app.routes import calibration


class _FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, one_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._one_value = one_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value

    def one(self):
        return self._one_value


class _FakeDB:
    def __init__(self):
        self.statements = []
        self._results = [
            _FakeResult(rows=[]),
            _FakeResult(rows=[]),
            _FakeResult(scalar_value=0),
            _FakeResult(
                one_value=SimpleNamespace(
                    has_closing=0,
                    needs_closing=0,
                    total_completed=0,
                )
            ),
        ]

    async def execute(self, statement):
        self.statements.append(statement)
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_public_calibration_requires_settled_current_probability():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "COUNT(*) FILTER (WHERE fo.current_probability >= 0.95) AS near_one" in futures_sql
    assert "COUNT(*) FILTER (WHERE fo.current_probability <= 0.05) AS near_zero" in futures_sql
    assert "AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)" in futures_sql
    assert "fo.is_winner IS NOT NULL" not in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_falls_back_to_settled_price_for_winner_status():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "(fo.is_winner = true OR fo.current_probability >= 0.95) AS is_winner" in futures_sql
