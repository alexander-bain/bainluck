"""#11616 F3: a verified-title overlay never serves an integer older than its value.

``_format_market_detail`` stamps ``rendered_percent`` on the SOURCE values;
``_apply_verified_title_to_detail`` then rewrites ``probability``. Web detail
always asks for ``representation=verified_title`` and iOS defaults to it, and
both prefer the served integer — so lane1b's probe P3 printed 31% for an
overlaid 0.34, and an unsupported overlay row (``probability None``) kept 20,
breaking this PR's own "null probability, null integer" invariant.

The estimators stay distinct by design (#10224): only the integer is re-derived,
with the representation's own rule, from the value actually served.
"""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import futures
from app.utils.futures_verified_title import Composition, OutcomeOverlay, Refusal
from app.utils.graded_card import rendered_duel_percents, rendered_percent

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
SEEN = NOW - timedelta(hours=1)
SOURCES = ["kalshi", "polymarket"]


def _leg(i, name, p):
    return SimpleNamespace(
        id=i, name=name, external_id=f"F3-{i}", current_probability=p,
        current_yes_bid=max(0, p - 0.01), current_yes_ask=min(1, p + 0.01),
        current_american_odds=None, rank=i, rank_change_24h=None,
        probability_change_24h=None, opening_probability=None,
        opening_american_odds=None, is_winner=None, resolution_source=None,
        last_updated=SEEN, price_changed_at=None,
    )


def _detail(legs, *, exclusive):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    market = SimpleNamespace(
        id=990031, name="Pro Football Champion", description=None,
        category="championship", source="kalshi", external_id="F3-probe",
        status="open", sport=None, sport_id=None, event_id=None, market_type=None,
        market_tier=1, llm_sport_category="football", mutually_exclusive=exclusive,
        commence_time=None, resolution_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        created_at=None, updated_at=None, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[],
        market_metadata=None, outcomes=legs,
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(futures, "datetime", _Fixed))
        return futures._format_market_detail(market)


def _served(detail):
    return {row["id"]: (row["probability"], row["rendered_percent"]) for row in detail["outcomes"]}


def test_overlaid_rows_print_their_own_integers_and_an_unsupported_row_prints_none():
    # P3 verbatim: an independent board, two rows re-valued, one unsupported.
    detail = _detail(
        [_leg(1, "Kansas City Chiefs", 0.31), _leg(2, "Buffalo Bills", 0.25),
         _leg(3, "Philadelphia Eagles", 0.20)],
        exclusive=False,
    )
    assert _served(detail)[1] == (0.31, 31)  # the source stamp the overlay must replace
    futures._apply_verified_title_to_detail(detail, Composition(
        question_identity={"q": "nfl_title"},
        overlay={
            1: OutcomeOverlay(0.34, SOURCES, SEEN.isoformat(), "median", True),
            2: OutcomeOverlay(0.22, SOURCES, SEEN.isoformat(), "median", True),
            3: OutcomeOverlay(None, [], None, "unsupported", True),
        },
        contributing_sources=SOURCES,
    ))
    assert _served(detail) == {1: (0.34, 34), 2: (0.22, 22), 3: (None, None)}
    for probability, integer in _served(detail).values():
        assert integer == rendered_percent(probability)


def test_an_exclusive_pair_is_restamped_with_the_pair_rule_on_the_served_values():
    detail = _detail([_leg(1, "Alpha", 0.60), _leg(2, "Beta", 0.40)], exclusive=True)
    futures._apply_verified_title_to_detail(detail, Composition(
        question_identity={"q": "nfl_title"},
        overlay={
            1: OutcomeOverlay(0.565, SOURCES, SEEN.isoformat(), "median", True),
            2: OutcomeOverlay(0.445, SOURCES, SEEN.isoformat(), "median", True),
        },
        contributing_sources=SOURCES,
    ))
    rows = detail["outcomes"]
    assert [r["rendered_percent"] for r in rows] == rendered_duel_percents(
        rows[0]["probability"], rows[1]["probability"]
    )
    assert sum(r["rendered_percent"] for r in rows) == 100


def test_control_source_mode_keeps_the_representation_integers():
    detail = _detail(
        [_leg(1, "Kansas City Chiefs", 0.31), _leg(2, "Buffalo Bills", 0.25)],
        exclusive=False,
    )
    before = _served(detail)
    futures._apply_verified_title_to_detail(detail, Refusal("resolver_error"))
    assert _served(detail) == before
