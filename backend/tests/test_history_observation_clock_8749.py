"""Actual detail/history routes keep a cached probability with its own clock."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.utils.aggregation import newest_source_reading_time
from tests.test_blend_fold_chart_pin_parity_3911 import (
    CANON_ID,
    _now,
    both_routes as _shared_both_routes,
)


@pytest.fixture
def both_routes(monkeypatch):
    return _shared_both_routes.__wrapped__(monkeypatch)


def _reading(value, at):
    return {"value": value, "updated_at": at.isoformat()} if at else value


def _session(
    routes, now, *, canon_value=0.6, twin_value=0.4, canon_at=None, twin_at=None
):
    session = routes.session(
        now,
        sources={"polymarket": _reading(canon_value, canon_at)},
        twin_sources={"kalshi": _reading(twin_value, twin_at)},
    )
    session.event.status = "live"
    session.event.commence_time = now - timedelta(hours=1)
    return session


@pytest.fixture(autouse=True)
def _clean_cache(both_routes):
    both_routes.cache.clear()
    yield
    both_routes.cache.clear()


def test_cached_pin_keeps_its_own_clock_when_live_row_moves(both_routes):
    now = _now()
    old, fresh = now - timedelta(seconds=25), now - timedelta(seconds=2)
    detail = both_routes.detail(_session(both_routes, now, canon_at=old, twin_at=old))
    assert detail["hero_probability"] == pytest.approx(0.5)
    assert detail["hero_probability_observed_at"] == old.isoformat()
    session = _session(
        both_routes, now, canon_value=0.2, twin_value=0.1, canon_at=fresh, twin_at=fresh
    )
    history = both_routes.history(session)
    assert history["blend_edge_pinned"] is True
    assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(0.5)
    assert history["blend_edge_observed_at"] == old.isoformat()
    assert (
        history["blend_edge_observed_at"] != history["aggregate_line"][-1]["timestamp"]
    )
    assert session.blend_fold_lookups == 0


def test_expired_cache_uses_fresh_folded_probability_and_clock(both_routes):
    now = _now()
    old, fresh = now - timedelta(seconds=25), now - timedelta(seconds=2)
    both_routes.detail(_session(both_routes, now, canon_at=old, twin_at=old))
    cached_at, status, payload = both_routes.cache[CANON_ID]
    both_routes.cache[CANON_ID] = (cached_at - 60, status, payload)
    session = _session(
        both_routes, now, canon_value=0.2, twin_value=0.1, canon_at=old, twin_at=fresh
    )
    history = both_routes.history(session)
    assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(0.15)
    assert history["blend_edge_observed_at"] == fresh.isoformat()
    assert session.blend_fold_lookups == 1


def test_detail_clock_includes_folded_source(both_routes):
    now = _now()
    old, fresh = now - timedelta(seconds=25), now - timedelta(seconds=2)
    detail = both_routes.detail(_session(both_routes, now, canon_at=old, twin_at=fresh))
    assert detail["hero_probability"] == pytest.approx(0.5)
    assert detail["hero_probability_observed_at"] == fresh.isoformat()


def test_legacy_cache_missing_clock_cannot_borrow_fresh_row_clock(both_routes):
    now = _now()
    old, fresh = now - timedelta(seconds=25), now - timedelta(seconds=2)
    detail = both_routes.detail(_session(both_routes, now, canon_at=old, twin_at=old))
    detail.pop("hero_probability_observed_at")
    history = both_routes.history(
        _session(both_routes, now, canon_at=fresh, twin_at=fresh)
    )
    assert history["blend_edge_pinned"] is True
    assert history["aggregate_line"][-1]["home_probability"] == pytest.approx(0.5)
    assert history["blend_edge_observed_at"] is None


@pytest.mark.parametrize("cached", [True, False], ids=["cached", "fresh-history"])
def test_unstamped_admitted_source_leaves_clock_unknown(both_routes, cached):
    now = _now()
    session = _session(both_routes, now, canon_at=now, twin_at=None)
    if cached:
        detail = both_routes.detail(session)
        assert detail["hero_probability_observed_at"] is None
    history = both_routes.history(session)
    assert history["blend_edge_pinned"] is True
    assert history["blend_edge_observed_at"] is None


def test_finished_no_pin_has_no_price_observation_clock(both_routes):
    now = _now()
    session = _session(both_routes, now, canon_at=now, twin_at=now)
    session.event.status = "completed"
    session.event.completed_at = now - timedelta(minutes=1)
    session.event.home_score, session.event.away_score = 2, 0
    detail = both_routes.detail(session)
    assert detail["hero_probability_source"] == "settled"
    assert detail["hero_probability_observed_at"] is None
    history = both_routes.history(session)
    assert history["blend_edge_pinned"] is False
    assert history["blend_edge_observed_at"] is None


def test_opening_and_unclocked_espn_fallback_have_no_clock(both_routes):
    now = _now()
    for espn in (None, 0.7):
        both_routes.cache.clear()
        session = both_routes.session(now, sources={}, twin_sources={})
        session.event.espn_win_prob_home = espn
        detail = both_routes.detail(session)
        assert detail["hero_probability_observed_at"] is None


def test_strict_clock_ignores_metadata_and_refused_sources():
    from app.utils.probability_eligibility import (
        ELIGIBILITY_KEY,
        INELIGIBLE,
        EligibilityRecord,
    )

    now = _now()
    event = SimpleNamespace(
        status="live",
        win_probability_sources={
            "kalshi": _reading(0.6, now),
            "betting_book_count": 12,
            "polymarket": {
                "value": 0.9,
                ELIGIBILITY_KEY: EligibilityRecord(status=INELIGIBLE).to_entry(),
            },
        },
    )
    assert newest_source_reading_time(event, require_complete=True) == now


def test_strict_clock_preserves_existing_permissive_pin_predicate():
    now = _now()
    event = SimpleNamespace(
        status="live",
        win_probability_sources={
            "kalshi": _reading(0.6, now),
            "polymarket": 0.4,
        },
    )
    assert newest_source_reading_time(event) == now
    assert newest_source_reading_time(event, require_complete=True) is None


@pytest.mark.parametrize("bad_stamp", [None, "not-a-date", ""])
def test_malformed_admitted_stamp_cannot_date_whole_blend(bad_stamp):
    now = _now()
    event = SimpleNamespace(
        status="live",
        win_probability_sources={
            "kalshi": _reading(0.6, now),
            "polymarket": {"value": 0.4, "updated_at": bad_stamp},
        },
    )
    assert newest_source_reading_time(event, require_complete=True) is None


def test_single_source_history_without_blend_line_has_no_edge_clock(both_routes):
    session = both_routes.session(_now())
    original_rows = session._rows
    session._rows = lambda: [
        row for row in original_rows() if row.source == "polymarket"
    ]
    history = both_routes.history(session)
    assert history["aggregate_line"] is None
    assert history["blend_edge_pinned"] is False
    assert history["blend_edge_observed_at"] is None
    assert session.blend_fold_lookups == 0
