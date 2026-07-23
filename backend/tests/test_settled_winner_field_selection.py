"""#1177 — settled-concept winner-field selection invariant.

A SETTLED concept must never serve an UNGRADED winner field when a GRADED market
(one carrying authoritative is_winner rows) exists among its candidates — the crown
cannot depend on which source market polled last. These tests pin the shared
selector and both adapters' selection functions (soccer World Cup, cycling GC).
"""

from datetime import datetime, timezone

from app.utils.winner_field_selection import (
    market_has_graded_winner,
    prefer_graded_winner_field,
)
from app.utils.event_soccer import _select_winner_field
from app.utils.event_cycling import _select_gc_field


class _Outcome:
    def __init__(self, name, prob, *, is_winner=False, last_updated=None):
        self.name = name
        self.current_probability = prob
        self.is_winner = is_winner
        self.last_updated = last_updated


class _Market:
    def __init__(self, mid, name, outcomes):
        self.id = mid
        self.name = name
        self.outcomes = outcomes


_OLD = datetime(2026, 6, 9, tzinfo=timezone.utc)
_NEW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _ungraded_fresh_wc(mid=10):
    # A live odds_api-shaped field that has FIZZLED post-settlement but is freshest.
    return _Market(
        mid,
        "FIFA World Cup Winner",
        [
            _Outcome("Spain", 0.55, last_updated=_NEW),
            _Outcome("France", 0.20, last_updated=_NEW),
            _Outcome("Brazil", 0.15, last_updated=_NEW),
        ],
    )


def _graded_stale_wc(mid=112892):
    # The authoritative graded market: Spain won, staler than the odds_api field.
    return _Market(
        mid,
        "World Cup Winner",
        [
            _Outcome("Spain", 1.0, is_winner=True, last_updated=_OLD),
            _Outcome("Argentina", 0.0, last_updated=_OLD),
            _Outcome("France", 0.0, last_updated=_OLD),
        ],
    )


# --- shared helper ---------------------------------------------------------


def test_market_has_graded_winner():
    assert market_has_graded_winner(_graded_stale_wc()) is True
    assert market_has_graded_winner(_ungraded_fresh_wc()) is False
    assert market_has_graded_winner(_Market(1, "x", [])) is False


def test_prefer_graded_overrides_fresher_ungraded():
    fresh = _ungraded_fresh_wc()
    graded = _graded_stale_wc()
    coherent = [
        (fresh, fresh.outcomes, _NEW),
        (graded, graded.outcomes, _OLD),
    ]
    market, real = prefer_graded_winner_field(fresh, fresh.outcomes, coherent)
    assert market is graded, "a graded market must override the fresher ungraded pick"
    assert real is graded.outcomes


def test_prefer_graded_noop_when_no_graded_candidate():
    fresh = _ungraded_fresh_wc()
    coherent = [(fresh, fresh.outcomes, _NEW)]
    market, real = prefer_graded_winner_field(fresh, fresh.outcomes, coherent)
    assert market is fresh, "with no graded candidate the freshest field is kept"


def test_prefer_graded_noop_when_best_already_graded():
    graded = _graded_stale_wc()
    coherent = [(graded, graded.outcomes, _OLD)]
    market, _ = prefer_graded_winner_field(graded, graded.outcomes, coherent)
    assert market is graded


# --- soccer adapter selection ---------------------------------------------


def test_soccer_prefers_graded_when_settled():
    """The exact #1177 shape: a fresh ungraded odds_api field beside a graded (Spain
    won) market — the selector must return the graded one."""
    market, real = _select_winner_field([_ungraded_fresh_wc(), _graded_stale_wc()])
    assert market is not None
    assert market_has_graded_winner(market), "settled WC must serve the graded field"
    spain = next(o for o in real if o.name == "Spain")
    assert spain.is_winner is True


def test_soccer_keeps_freshest_when_live_no_graded():
    """Live (no graded market): the pre-#1177 freshest-wins behavior is preserved."""
    stale = _ungraded_fresh_wc(mid=1)
    for o in stale.outcomes:
        o.last_updated = _OLD
    fresh = _ungraded_fresh_wc(mid=2)
    market, _ = _select_winner_field([stale, fresh])
    assert market is fresh


# --- cycling adapter selection --------------------------------------------


def _ungraded_fresh_gc(mid=100):
    return _Market(
        mid,
        "Tour de France 2026 Winner",
        [
            _Outcome("Tadej Pogacar", 0.60, last_updated=_NEW),
            _Outcome("Jonas Vingegaard", 0.25, last_updated=_NEW),
            _Outcome("Remco Evenepoel", 0.10, last_updated=_NEW),
        ],
    )


def _graded_stale_gc(mid=200):
    return _Market(
        mid,
        "Tour de France 2026 Winner",
        [
            _Outcome("Tadej Pogacar", 1.0, is_winner=True, last_updated=_OLD),
            _Outcome("Jonas Vingegaard", 0.0, last_updated=_OLD),
            _Outcome("Remco Evenepoel", 0.0, last_updated=_OLD),
        ],
    )


def test_cycling_prefers_graded_when_settled():
    market, real = _select_gc_field([_ungraded_fresh_gc(), _graded_stale_gc()])
    assert market is not None
    assert market_has_graded_winner(market), "settled GC must serve the graded field"
    champ = next(o for o in real if o.name == "Tadej Pogacar")
    assert champ.is_winner is True


def test_cycling_keeps_freshest_when_live_no_graded():
    stale = _ungraded_fresh_gc(mid=1)
    for o in stale.outcomes:
        o.last_updated = _OLD
    fresh = _ungraded_fresh_gc(mid=2)
    market, _ = _select_gc_field([stale, fresh])
    # No graded candidate → adapter's own (widest, freshest) selection stands; both
    # have equal width so the fresher one wins.
    assert market is fresh
