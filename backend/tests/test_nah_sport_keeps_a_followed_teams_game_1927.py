"""#1927 — a game your team is playing survives a "Nah" on its sport.

Measured on production 2026-09-17 22:50Z, master `8264130bc`. The one account
with real phone history (`user_preferences.user_id` 364, 2,943 recorded swipes,
5 followed teams) stores `baseball_mlb: 0.0` from its 2026-06-21 onboarding. All
five MLB games in that minute's `GET /api/feed?limit=150` payload were deleted
for it, along with both soccer fixtures — **7 of 7 games, zero reaching the
phone** — which is the failure this issue was opened for.

The deletion is `routes/feed.py`'s "Nah" hard filter: it reads a REASON STRING
off the personalization result and `continue`s, so it never sees the number the
scorer computed. For a followed team in a Nah sport that number is:

    your_team:0.80  +  sport_nah:-0.60  ->  multiplier 1.20

a NET BOOST. The two signals had already been weighed against each other, the
follow had already won, and the gate was deleting the winner. CERT-2676 named
this exact shape one clause to the left — "the gate reads the admission score,
the rank reads the penalty" — and the same reasoning had not been carried across
to the hard filter beside it.

The controls carry as much of this file as the arm does. A Nah still deletes
(this is not a quiet repeal of the preference); a `rival` relation still deletes,
because a rival is INFERRED from a follow rather than performed by the reader;
and a game in a sport that is not Nah is served either way, so the arm cannot
pass for the trivial reason that the harness admits everything.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.personalization import (
    NAH_AFFINITY_THRESHOLD,
    STANDING_TEAM_RELATIONSHIPS,
    PersonalizationContext,
    compute_event_multiplier,
)

NOW = datetime(2026, 9, 17, 22, 50, 0, tzinfo=timezone.utc)

#: The stored key and value read off production for the account above. Written
#: as the real pair rather than a round number so a reader can check it against
#: the issue comment.
NAH_SPORT = "baseball_mlb"
NAH_VALUE = 0.0

HOME_TEAM_ID = 4101
AWAY_TEAM_ID = 4202


# --------------------------------------------------------------------------
# The scorer: the flag, and the multiplier that proves the gate was wrong
# --------------------------------------------------------------------------


def _ctx(relations=None, affinity=NAH_VALUE):
    return PersonalizationContext(
        is_authenticated=True,
        sport_affinities={NAH_SPORT: affinity},
        team_relations={HOME_TEAM_ID: set(relations)} if relations else {},
        team_weights={HOME_TEAM_ID: 1.0} if relations else {},
    )


def _score(relations=None, affinity=NAH_VALUE):
    return compute_event_multiplier(
        _ctx(relations, affinity),
        home_team_id=HOME_TEAM_ID,
        away_team_id=AWAY_TEAM_ID,
        sport_key=NAH_SPORT,
    )


@pytest.mark.parametrize("relation", sorted(STANDING_TEAM_RELATIONSHIPS))
def test_a_performed_relationship_sets_the_flag(relation):
    assert _score({relation}).has_standing_team_relationship is True


def test_a_rival_alone_does_not_set_the_flag():
    """A rival is derived from a follow, not declared. The distinction is the
    reason this is a field and not a substring test on the reason strings —
    `rival_playing` is a team relationship by any string measure."""
    r = _score({"rival"})
    assert any(x.startswith("rival_") for x in r.reasons), r.reasons
    assert r.has_standing_team_relationship is False


def test_no_relationship_leaves_the_flag_false():
    assert _score().has_standing_team_relationship is False


def test_the_futures_path_never_sets_it():
    """Futures have no home/away pair, so their gate is untouched by this ship."""
    from app.utils.personalization import compute_futures_multiplier

    r = compute_futures_multiplier(
        _ctx({"follow"}), NAH_SPORT.split("_")[0], [HOME_TEAM_ID], sport_key=NAH_SPORT
    )
    assert r.has_standing_team_relationship is False


def test_the_followed_game_in_a_nah_sport_is_a_net_boost():
    """The defect in one number: the gate was deleting a card the scorer rated
    ABOVE neutral for this reader. If this ever drops to <= 1.0 the rescue below
    stops being "read the score you already computed" and becomes a policy
    change, which is a different ship and a different ruling."""
    r = _score({"follow"})
    assert any(x.startswith("sport_nah") for x in r.reasons), r.reasons
    assert r.multiplier > 1.0, r.multiplier
    # and the unfollowed twin, for contrast
    assert _score().multiplier < 1.0


def test_the_affinity_under_test_really_is_a_nah():
    """Pins the arm to the threshold rather than to the literal 0.0, so a change
    to `NAH_AFFINITY_THRESHOLD` cannot leave this file testing nothing."""
    assert NAH_VALUE <= NAH_AFFINITY_THRESHOLD


# --------------------------------------------------------------------------
# The gate: driven through the real `_score_events`
# --------------------------------------------------------------------------


def _sport():
    s = MagicMock()
    s.key = NAH_SPORT
    s.name = "MLB"
    return s


def _game(event_id: int = 1):
    """A finished high-interest MLB game in production's measured shape — the
    same card type as the five that were deleted."""
    e = MagicMock()
    e.id = event_id
    e.status = "completed"
    e.commence_time = NOW - timedelta(hours=4)
    e.completed_at = NOW - timedelta(hours=1)
    e.statpal_end_time = None
    e.home_team_id = HOME_TEAM_ID
    e.away_team_id = AWAY_TEAM_ID
    e.home_team_name = "Red Sox"
    e.away_team_name = "Yankees"
    e.opening_home_probability = 0.20
    e.opening_away_probability = 0.80
    e.win_probability_sources = {"betting": {"home_probability": 0.95}}
    e.opening_home_spread = -3.5
    e.opening_over_under = 8.5
    e.opening_favorite = "Yankees"
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.period = None
    e.raw_ei = 0.95
    e.ei_metadata = None
    e.home_score = 7
    e.away_score = 2
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _served(ctx, *, my_teams_only=False):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db([_game()]), NOW, None, ctx, my_teams_only=my_teams_only
        )
    return items


@pytest.mark.asyncio
@pytest.mark.parametrize("relation", sorted(STANDING_TEAM_RELATIONSHIPS))
async def test_the_gate_keeps_a_game_the_reader_has_a_standing_relationship_with(
    relation,
):
    """THE ARM. Deleting the clause in `routes/feed.py` fails exactly this."""
    items = await _served(_ctx({relation}))
    assert len(items) == 1, f"{relation}: the followed game was deleted"


@pytest.mark.asyncio
async def test_the_gate_still_deletes_a_nah_sport_with_no_relationship():
    """THE CONTROL that keeps the preference real. A rescue written as an
    unconditional `True` passes every arm above and fails here."""
    assert await _served(_ctx()) == []


@pytest.mark.asyncio
async def test_a_rival_alone_is_still_deleted():
    assert await _served(_ctx({"rival"})) == []


@pytest.mark.asyncio
async def test_the_same_game_is_served_when_the_sport_is_not_a_nah():
    """THE CONTROL against a vacuous arm: if the harness were dropping this game
    for some reason of its own, this would be empty too."""
    assert len(await _served(_ctx(affinity=1.0))) == 1


@pytest.mark.asyncio
async def test_my_stuff_is_unchanged():
    """`my_teams_only` already exempted itself from the filter; this ship must
    not have made that exemption conditional on the new flag.

    A `rival` relation is the specimen that separates the two: My Stuff admits
    the game because `my_teams_only` is true, NOT because of the rescue — the
    same context is deleted on Discover two tests above. (My Stuff also needs a
    relation of some kind to select the event at all, `feed.py:8887`, which is
    why the plain no-relation context cannot be used here.)"""
    assert len(await _served(_ctx({"rival"}), my_teams_only=True)) == 1
