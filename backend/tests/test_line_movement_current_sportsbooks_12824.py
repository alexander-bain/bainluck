"""Opening prices are historical inputs, never a current disagreement."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import WinProbSnapshot
from app.routes.events import get_line_movement_analysis


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, *rows, venue_history=()):
        self.rows = iter(rows)
        self.venue_history = venue_history
        self.added = []
        self.committed = False

    async def execute(self, statement):
        if statement.column_descriptions[0]["entity"] is WinProbSnapshot:
            return _Result(self.venue_history)
        return _Result(next(self.rows))

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


def _event(now, *, opening=0.74, betting=None):
    sources = {"kalshi": {"value": 0.58, "updated_at": now.isoformat()}}
    if betting is not None:
        sources.update(
            betting={"value": betting, "updated_at": now.isoformat()}, betting_book_count=3
        )
    return SimpleNamespace(
        id=99123, status="live", home_team_name="Home", away_team_name="Away",
        sport=SimpleNamespace(key="icehockey_nhl"), opening_home_probability=opening,
        win_probability_sources=sources,
    )


def _venue_snapshot(event, captured_at, probability=0.58):
    return WinProbSnapshot(
        event_id=event.id, source="kalshi", captured_at=captured_at,
        home_win_probability=probability,
    )


async def test_opening_and_unadmitted_raw_book_rows_do_not_create_disagreement():
    now = datetime.now(timezone.utc)
    event = _event(now)
    raw = SimpleNamespace(captured_at=now, home_win_probability=0.72)
    for books in ([], [raw]):
        db = _Session([event], [], books, venue_history=[_venue_snapshot(event, now)])
        response = await get_line_movement_analysis(event.id, db)
        assert response["disagreement_data"] is None
        assert response["disagreement_explanation"] is None
        assert db.committed and db.added[0].disagreement_data is None


async def test_current_admitted_consensus_serves_without_an_opening_and_caches():
    now = datetime.now(timezone.utc)
    event = _event(now, opening=None, betting=0.69)
    raw = SimpleNamespace(captured_at=now, home_win_probability=0.83)
    older_venue = _venue_snapshot(event, now - timedelta(minutes=5), probability=0.52)
    db = _Session([event], [], [raw], venue_history=[older_venue])
    response = await get_line_movement_analysis(event.id, db)
    expected = {
        "sportsbook_home_prob": 0.69, "prediction_market_home_prob": 0.58,
        "source": "kalshi", "divergence": 0.11,
    }
    assert response["disagreement_data"] == expected
    cache = db.added[0]
    cache.created_at = now
    cache.explanation = "The score changed."
    cached_db = _Session([event], [cache])
    cached = await get_line_movement_analysis(event.id, cached_db)
    assert cached["cached"] is True
    assert cached["disagreement_data"] == expected
    assert cached["movements"] == response["movements"]
    assert cached["context"] == response["context"]
    assert not cached_db.committed

    venue_value_changed = _event(now, betting=0.69)
    venue_value_changed.win_probability_sources["kalshi"]["value"] = 0.54
    venue_source_changed = _event(now, betting=0.69)
    sources = venue_source_changed.win_probability_sources
    sources["polymarket"] = sources.pop("kalshi")
    withdrawn = _event(now, betting=0.69)
    withdrawn.win_probability_sources.pop("kalshi")
    for latest in (_event(now), _event(now, betting=0.73), venue_value_changed,
                   venue_source_changed, withdrawn):
        changed = await get_line_movement_analysis(event.id, _Session([latest], [cache]))
        assert changed["disagreement_data"] is None
        assert changed["movements"] == response["movements"]
        assert changed["context"] == response["context"]
        assert changed["explanation"] == cache.explanation


@pytest.mark.parametrize("venue_retained", [False, True], ids=["withdrawn", "floored"])
async def test_an_opening_only_venue_snapshot_cannot_create_a_current_comparison(venue_retained):
    now = datetime.now(timezone.utc)
    opening_at = now - timedelta(hours=2)
    event = _event(now, betting=0.69)
    if venue_retained:
        event.win_probability_sources["kalshi"]["updated_at"] = opening_at.isoformat()
    else:
        event.win_probability_sources.pop("kalshi")
    historical_venue = _venue_snapshot(event, opening_at)
    db = _Session([event], [], [], venue_history=[historical_venue])
    response = await get_line_movement_analysis(event.id, db)
    assert response["disagreement_data"] is None
    assert db.added[0].disagreement_data is None


@pytest.mark.parametrize(
    ("kalshi_seconds_ago", "polymarket_seconds_ago", "expected"),
    [(60, 0, "polymarket"), (None, 0, "polymarket"),
     (0, 0, "kalshi"), (None, None, "kalshi")],
)
async def test_latest_admitted_venue_has_stable_ties_and_undated_ordering(
    kalshi_seconds_ago, polymarket_seconds_ago, expected,
):
    now = datetime.now(timezone.utc)
    event = _event(now, betting=0.69)
    sources = event.win_probability_sources
    sources.pop("kalshi")
    for source, seconds_ago, probability in (
        ("polymarket", polymarket_seconds_ago, 0.53), ("kalshi", kalshi_seconds_ago, 0.58),
    ):
        sources[source] = (
            probability if seconds_ago is None else
            {"value": probability, "updated_at": (now - timedelta(seconds=seconds_ago)).isoformat()}
        )
    response = await get_line_movement_analysis(event.id, _Session([event], [], []))
    assert response["disagreement_data"]["source"] == expected


async def test_legacy_cache_preserves_history_without_its_unsupported_comparison():
    now = datetime.now(timezone.utc)
    movement = [{"timestamp_start": now.isoformat(), "home_prob_before": 0.5}]
    for stored in (
        movement,
        {"movements": movement, "context": {"injuries_count": 2}},
        {"movements": movement, "disagreement_basis": "admitted-sportsbook-v1"},
    ):
        event = _event(now, betting=0.74)
        data = {
            "sportsbook_home_prob": 0.74, "prediction_market_home_prob": 0.58,
            "source": "kalshi", "divergence": 0.16,
        }
        cache = SimpleNamespace(
            expires_at=now + timedelta(minutes=15), created_at=now,
            movement_data=stored, explanation="The score changed.",
            disagreement_explanation="The sportsbook figure is different.",
            disagreement_data=data,
        )
        db = _Session([event], [cache])
        response = await get_line_movement_analysis(event.id, db)
        assert response["cached"] is True
        assert response["movements"] == movement
        assert response["context"] == (stored.get("context") if isinstance(stored, dict) else None)
        assert response["explanation"] == cache.explanation
        assert response["disagreement_data"] is None
        assert response["disagreement_explanation"] is None
        assert cache.disagreement_data == data
        assert not db.committed
