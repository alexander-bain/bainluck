"""#9645 / #9236 — unrelated sports dismissals stop suppressing a whole sport.

## The defect

Alex's journey: open and like every Red Sox game, swipe away the unrelated MLB
games around them. Every one of those swipes wrote a negative into the
`baseball` category rollup, into every feature token the card derived
(`category:baseball`, `type:event`, `format:matchup`, `archetype:*`, both teams'
`entity:*`, and — for any card naming Boston — `team:boston_red_sox` and
`region:boston`), and into a resemblance set carrying the same team/region
tokens. So the swipes that meant "not this game" were cancelling the opens that
meant "the Red Sox", and a two-team card was teaching a dislike of a team the
reader never named.

## The contract (week-one decision on #9236)

* A negative swipe on a sports card is EXACT: it hides that card (and its story,
  where the card has one). It teaches no category, format, archetype, region,
  team or entity dislike.
* Positive sports relevance is unchanged.
* Non-sports negatives are unchanged.
* No preference is learned without sign-in (Alex, 2026-09-29). A signed-out
  swipe is still recorded and still hides its card; it teaches nothing — not to
  the anonymous session, and not to the account that later signs in on it.

Every test here drives the REAL `_load_personalization_context` and the REAL
scorers, with the same eligible rows on both sides of each comparison.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.feed import (
    _build_discover_category_affinities,
    _build_discover_category_negative_counts,
    _build_discover_feature_affinities,
    _discover_feature_tokens,
    _discover_semantic_tokens,
    _is_sports_feedback,
    _load_personalization_context,
)
from app.utils.personalization import (
    compute_event_multiplier,
    compute_futures_multiplier,
)

_SESSION_ID = "sports-negative-9645"
_READER = SimpleNamespace(id=9645)
#: Offset from the clock, never fixed: the loader compares `last_seen` against a
#: cutoff computed at call time (gotcha #44).
_NOW = datetime.now(timezone.utc) - timedelta(minutes=5)

_RED_SOX_OPENS = [
    "Boston Red Sox vs New York Yankees",
    "Boston Red Sox vs Baltimore Orioles",
    "Toronto Blue Jays vs Boston Red Sox",
]
_UNRELATED_MLB_SWIPES = [
    "Seattle Mariners vs Houston Astros",
    "Chicago Cubs vs St. Louis Cardinals",
    "Los Angeles Dodgers vs San Diego Padres",
    "Atlanta Braves vs Philadelphia Phillies",
    "Detroit Tigers vs Cleveland Guardians",
    "Texas Rangers vs Kansas City Royals",
]
#: The card the reader should keep seeing: a Red Sox game they have not opened.
_NEXT_RED_SOX_GAME = "Tampa Bay Rays vs Boston Red Sox"
#: A control: an unrelated MLB game they have not swiped.
_UNSEEN_MLB_GAME = "Milwaukee Brewers vs Cincinnati Reds"


def _category_rows(opens, swipes):
    rows = []
    if opens:
        rows += [("baseball", "open", len(opens)), ("baseball", "like", len(opens))]
    if swipes:
        rows.append(("baseball", "unlike", len(swipes)))
    rows.append(("politics", "impression", 40))  # warm: clear the cold-start lane
    return rows


def _feature_rows(opens, swipes):
    return [("event", name, "baseball", "open", 1) for name in opens] + [
        ("event", name, "baseball", "like", 1) for name in opens
    ] + [("event", name, "baseball", "unlike", 1) for name in swipes]


def _recent_rows(swipes, first_id=70000):
    return [
        ("event", first_id + i, "unlike", _NOW, name, "baseball")
        for i, name in enumerate(swipes)
    ]


def _session(category_rows, feature_rows, recent_rows, statements=None):
    """Answer the three `discover_interactions` reads by projection (#5453's
    routing: `max(` is the recent-items read, `item_name` the feature rollup)."""

    def _result(rows):
        result = MagicMock()
        result.all.return_value = rows
        result.scalars.return_value.all.return_value = rows
        result.scalar_one_or_none.return_value = None
        return result

    async def mock_execute(stmt, *args, **kwargs):
        lowered = str(stmt).lower()
        if statements is not None:
            statements.append(lowered)
        if "discover_interactions" not in lowered:
            return _result([])
        if "max(" in lowered:
            return _result(list(recent_rows))
        if "item_name" in lowered:
            return _result(list(feature_rows))
        return _result(list(category_rows))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session


async def _ctx(opens, swipes, user=_READER, statements=None):
    return await _load_personalization_context(
        _session(
            _category_rows(opens, swipes),
            _feature_rows(opens, swipes),
            _recent_rows(swipes),
            statements,
        ),
        user,
        session_id=_SESSION_ID,
        config=None,
    )


def _mlb_card(ctx, name, event_id=None):
    """Score an MLB game the way `_score_events` does: feature tokens PLUS the
    semantic tokens derived from them, so the resemblance term sees what it
    sees in production."""
    features = _discover_feature_tokens(
        item_name=name, category="baseball", item_type="event"
    )
    return compute_event_multiplier(
        ctx,
        home_team_id=None,
        away_team_id=None,
        sport_key="baseball_mlb",
        event_id=event_id,
        feature_tokens=sorted(features)
        + sorted(
            _discover_semantic_tokens(
                item_name=name,
                category="baseball",
                item_type="event",
                feature_tokens=features,
            )
        ),
    )


# ---------------------------------------------------------------------------
# The ship: Red Sox relevance survives unrelated MLB negatives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_red_sox_relevance_survives_unrelated_mlb_swipes():
    """THE JOURNEY. Same Red Sox opens on both sides; one side also swiped six
    unrelated MLB games away. The next Red Sox game must score identically."""
    opens_only = await _ctx(_RED_SOX_OPENS, [])
    opens_and_swipes = await _ctx(_RED_SOX_OPENS, _UNRELATED_MLB_SWIPES)

    before = _mlb_card(opens_only, _NEXT_RED_SOX_GAME)
    after = _mlb_card(opens_and_swipes, _NEXT_RED_SOX_GAME)

    assert before.multiplier > 1.0, (
        f"premise: the Red Sox opens must lift the next Red Sox game "
        f"({before.reasons}) or the comparison below proves nothing"
    )
    assert after.multiplier == pytest.approx(before.multiplier), (
        f"unrelated MLB swipes moved the Red Sox card from {before.multiplier} "
        f"to {after.multiplier}: {after.reasons}"
    )
    assert not any(
        r.startswith(("discover_dismiss", "discover_feature_dislike", "semantic_dismiss"))
        for r in after.reasons
    ), after.reasons


@pytest.mark.asyncio
async def test_unrelated_swipes_teach_nothing_broader_than_the_card():
    """The mechanism, stated on the context: the swipes add no key to any
    learned dictionary. Stronger than a score comparison — a new penalty that
    happened to cancel against a bonus would still fail here."""
    opens_only = await _ctx(_RED_SOX_OPENS, [])
    opens_and_swipes = await _ctx(_RED_SOX_OPENS, _UNRELATED_MLB_SWIPES)

    assert opens_and_swipes.discover_category_affinities == (
        opens_only.discover_category_affinities
    )
    assert opens_and_swipes.discover_category_negative_counts == {}
    assert opens_and_swipes.discover_feature_affinities == (
        opens_only.discover_feature_affinities
    )


@pytest.mark.asyncio
async def test_an_unseen_mlb_game_is_not_downranked_by_other_mlb_swipes():
    """CONTROL: the swipes do not become "less baseball" either."""
    swipes_only = await _ctx([], _UNRELATED_MLB_SWIPES)

    result = _mlb_card(swipes_only, _UNSEEN_MLB_GAME)

    assert result.multiplier == 1.0, result.reasons
    assert result.admission_multiplier == 1.0


@pytest.mark.asyncio
async def test_a_swiped_red_sox_game_teaches_no_boston_or_red_sox_dislike():
    """The two-team rule. Swiping one Red Sox game away is "not this game": it
    must not softly penalise the next Red Sox game by team, region or
    resemblance, because a two-team card cannot say which side was disliked."""
    swiped = "Boston Red Sox vs New York Yankees"
    ctx = await _ctx([], [swiped])

    assert not any(
        t.startswith(("team:", "region:"))
        for token_set in ctx.recent_dismissed_feature_token_sets
        for t in token_set
    ), ctx.recent_dismissed_feature_token_sets
    result = _mlb_card(ctx, "Boston Red Sox vs Baltimore Orioles")
    assert result.multiplier == 1.0, result.reasons


# ---------------------------------------------------------------------------
# Exact dismissal is preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_swiped_game_is_still_dismissed_exactly():
    ctx = await _ctx(_RED_SOX_OPENS, _UNRELATED_MLB_SWIPES)

    assert ctx.recent_dismissed_event_ids == {
        70000 + i for i in range(len(_UNRELATED_MLB_SWIPES))
    }


# ---------------------------------------------------------------------------
# Paired controls — non-sports behaviour is unchanged
# ---------------------------------------------------------------------------


def test_a_politics_negative_still_teaches_its_category_and_features():
    rows = [("politics", "unlike", 8), ("politics", "impression", 40)]
    feature_rows = [
        ("futures", "Will Boston elect a new mayor?", "politics", "unlike", 8),
    ]

    assert _build_discover_category_negative_counts(rows) == {"politics": 8}
    assert _build_discover_category_affinities(rows)["politics"] < 0
    features = _build_discover_feature_affinities(feature_rows)
    assert features["category:politics"] < 0
    assert features["region:boston"] < 0


@pytest.mark.asyncio
async def test_a_politics_swipe_still_downranks_a_politics_card():
    ctx = await _load_personalization_context(
        _session(
            [("politics", "unlike", 8), ("politics", "impression", 40)],
            [("futures", "Will Brown win the Ohio Senate race?", "politics", "unlike", 8)],
            [],
        ),
        _READER,
        session_id=_SESSION_ID,
        config=None,
    )
    result = compute_futures_multiplier(
        ctx,
        sport_category="politics",
        outcome_team_ids=[],
        feature_tokens=sorted(
            _discover_feature_tokens(
                item_name="Will Tester win the Montana Senate race?",
                category="politics",
                item_type="futures",
            )
        ),
    )

    assert result.multiplier < 1.0, result.reasons
    assert result.admission_multiplier == pytest.approx(1.0)


def test_positive_sports_signals_still_learn():
    rows = [("baseball", "open", 3), ("baseball", "like", 3), ("politics", "impression", 40)]
    feature_rows = [("event", "Boston Red Sox vs New York Yankees", "baseball", "like", 3)]

    assert _build_discover_category_affinities(rows)["baseball"] > 0
    features = _build_discover_feature_affinities(feature_rows)
    assert features["team:boston_red_sox"] > 0
    assert features["region:boston"] > 0


@pytest.mark.parametrize(
    "category,item_type,expected",
    [
        ("baseball", None, True),
        ("americanfootball", None, True),  # event-card root → football
        ("icehockey", "futures", True),
        ("aussierules", None, True),  # a sport-key root the LLM set lacks
        ("  Soccer ", None, True),
        ("other", "event", True),  # an event row is always a game
        ("politics", "futures", False),
        ("economics", None, False),
        (None, None, False),
        ("", "futures", False),
    ],
)
def test_the_sports_predicate(category, item_type, expected):
    assert _is_sports_feedback(category, item_type) is expected


# ---------------------------------------------------------------------------
# No preference is learned without sign-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_signed_out_session_learns_nothing_but_keeps_exact_dismissal():
    statements: list[str] = []
    ctx = await _ctx(_RED_SOX_OPENS, _UNRELATED_MLB_SWIPES, user=None, statements=statements)

    assert ctx.discover_category_affinities == {}
    assert ctx.discover_category_negative_counts == {}
    assert ctx.discover_feature_affinities == {}
    assert ctx.recent_dismissed_feature_token_sets == []
    # Browsing hygiene is not a preference: the swiped cards stay hidden.
    assert len(ctx.recent_dismissed_event_ids) == len(_UNRELATED_MLB_SWIPES)
    # And the learning reads are not asked at all (LAT-P113: round trips).
    assert not any(
        "discover_interactions" in s and "max(" not in s for s in statements
    ), statements


@pytest.mark.asyncio
async def test_a_signed_out_politics_swipe_teaches_nothing_either():
    """The sign-in guard is not sports-scoped: it holds for every category."""
    ctx = await _load_personalization_context(
        _session([("politics", "unlike", 8), ("politics", "impression", 40)], [], []),
        None,
        session_id=_SESSION_ID,
        config=None,
    )

    assert ctx.discover_category_affinities == {}
    assert ctx.discover_category_negative_counts == {}


@pytest.mark.asyncio
async def test_signing_in_does_not_adopt_the_sessions_signed_out_swipes():
    """The learning reads key on `user_id` alone. The old identity clause was
    `user_id = u OR session_id = s`, which would have taught a freshly signed-in
    account everything the same device did while signed out."""
    statements: list[str] = []
    await _ctx(_RED_SOX_OPENS, [], statements=statements)

    learning = [
        s for s in statements if "discover_interactions" in s and "max(" not in s
    ]
    assert len(learning) == 2, statements
    for stmt in learning:
        where = re.split(r"\bwhere\b", stmt, maxsplit=1)[1]
        assert "user_id" in where and "session_id" not in where, stmt
    # The exact-dismissal read keeps the session arm (released signed-out swipes).
    recent = [s for s in statements if "discover_interactions" in s and "max(" in s]
    assert recent and "session_id" in re.split(r"\bwhere\b", recent[0], maxsplit=1)[1]
