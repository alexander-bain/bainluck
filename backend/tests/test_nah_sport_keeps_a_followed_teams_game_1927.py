"""#1927 — a game your team is playing survives a "Nah" on its sport.

Measured on production 2026-09-17 22:50Z, master `8264130bc`. The one account
with real phone history (`user_preferences.user_id` 364, 2,943 recorded swipes,
5 followed teams) stores `baseball_mlb: 0.0` from its 2026-06-21 onboarding. All
five MLB games in that minute's `GET /api/feed?limit=150` payload were deleted
for it, along with both soccer fixtures — **7 of 7 games, zero reaching the
phone** — which is the failure this issue was opened for.

The deletion is `routes/feed.py`'s "Nah" hard filter: it reads a REASON STRING
off the personalization result and `continue`s, so it never sees the number the
scorer computed. CERT-2676 named this exact shape one clause to the left — "the
gate reads the admission score, the rank reads the penalty" — and the same
reasoning had not been carried across to the hard filter beside it.

WHICH NUMBER, EXACTLY — corrected 2026-09-18 (the first version of this file got
it wrong, and the same wrong number was written into the comment in `feed.py`).
The relation decides the sign, and only ONE of the three is a net boost:

    follow      your_team:0.80    + sport_nah:-0.60  ->  1.20   net BOOST
    local       local_team:0.30   + sport_nah:-0.60  ->  0.70   net PENALTY
    alma_mater  alma_mater:0.30   + sport_nah:-0.60  ->  0.70   net PENALTY

Account 364 — the only account with real phone history, and so the entire
production population of this defect — stores **`local` for all five** of its
favourites. Not one is a `follow`. So the reading this file shipped with ("the
follow outweighed the Nah; the gate was deleting the winner") described a case
that does not occur on production, and the case that DOES occur arrives on a
multiplier BELOW neutral.

The ship is still right, on the narrower ground that a 0.70 card is a downrank
and `#1091`'s rule is that game events are never capped into an empty tab —
keep-and-downrank beats delete. But "the follow won" is not the justification,
and `test_the_relation_decides_the_sign` below now pins all three signs so the
claim cannot silently regrow. What makes the ship land is the ADMISSION FLOOR,
not the sign: at 0.70 a real card still clears `min_score` 30, which is what
`test_the_penalised_relations_still_clear_the_admission_floor` measures.

The controls carry as much of this file as the arm does. When this file was
written a Nah still deleted and a `rival` relation still deleted; #1927's WIDE
half (Alex, 2026-09-17: "a ranking signal, not a death certificate") retired
the delete for everyone, so those two controls now pin the replacement contract
instead — the unrelated game is SERVED and RANKED BELOW the followed one, and a
rival's game is served on the same terms as any other (a rival is inferred, not
performed, so it earns no standing rescue — and needs none). A game in a sport
that is not Nah is served either way, so the arm cannot pass for the trivial
reason that the harness admits everything.
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


#: The sign of `relation + Nah`, per relation. `follow` is the only net boost;
#: production's account has none of them. See the module docstring.
_EXPECTED_SIGN = {"follow": "boost", "local": "penalty", "alma_mater": "penalty"}


def test_every_standing_relationship_has_a_declared_sign():
    """Keeps the table below honest when a fourth relation is added: a new member
    of `STANDING_TEAM_RELATIONSHIPS` with no declared sign fails HERE, rather
    than silently not being tested by the parametrize that reads this dict."""
    assert set(_EXPECTED_SIGN) == set(STANDING_TEAM_RELATIONSHIPS)


@pytest.mark.parametrize("relation", sorted(_EXPECTED_SIGN))
def test_the_relation_decides_the_sign(relation):
    """THE CORRECTION. This test used to run on `follow` alone and assert
    `multiplier > 1.0` for it, with a docstring saying that a drop to <= 1.0
    would make the rescue "a policy change ... a different ship". Production's
    only affected account holds `local` on all five favourites, so it was always
    <= 1.0 there — the guarantee was true of the one relation tested and false of
    the one that actually occurs.

    Pinning all three signs is what stops the 1.20 reading coming back."""
    r = _score({relation})
    assert any(x.startswith("sport_nah") for x in r.reasons), r.reasons
    if _EXPECTED_SIGN[relation] == "boost":
        assert r.multiplier > 1.0, (relation, r.multiplier)
    else:
        assert r.multiplier < 1.0, (relation, r.multiplier)
    # and the reader with no relationship at all, for contrast
    assert _score().multiplier < r.multiplier


@pytest.mark.parametrize(
    "relation", sorted(r for r, s in _EXPECTED_SIGN.items() if s == "penalty")
)
def test_the_penalised_relations_still_clear_the_admission_floor(relation):
    """WHAT MAKES THE SHIP LAND, and the thing no test measured: surviving the
    "Nah" filter is worth nothing if the card then fails the admission gate two
    clauses below it.

    The gate is `_discover_admission_score(base_score, p_result) < min_score`
    with `min_score` 30 on this path (not low-affinity, not my_teams_only, and
    the multiplier is under 1.0 so the 10-floor branch is not taken either), so a
    0.70 card needs `base_score >= 43`.

    The two base scores below were REPLAYED on 2026-09-18 from production's
    stored rows through the released scorers, and each is confirmed against the
    score `/api/feed` served for it that minute:

      * 100 — `15313872` Red Sox @ Rangers, finished, EI 0.87 (served at 80 on
        `?sport=baseball_mlb`, 100 decayed by ~2.9h of completed-game freshness;
        the decay runs AFTER this gate, so it moves rank and never admission)
      * 65 — `15314172` Red Sox @ Rays, scheduled (served at 65)

    When this file was written the non-follower control asserted the SAME
    upcoming fixture was below the floor at 0.40 — "the ship admits the reader's
    team and not the sport". #1927's WIDE half retired that: a Nah is a rank
    term and is held OUT of the admission multiplier entirely, so the
    no-relationship reader's card is admitted too and the relation separates the
    two by RANK instead. The controls below pin the replacement contract."""
    from app.routes.feed import _discover_admission_score

    min_score = 30
    r = _score({relation})
    for base_score in (100, 65):
        assert _discover_admission_score(base_score, r) >= min_score, (
            relation,
            base_score,
            r.multiplier,
        )

    # CONTROL 1 — the ship itself: the Nah is OUT of the admission multiplier,
    # so the same card for a reader with no relationship admits at its base
    # score. Putting the penalty back into `admission_multiplier` (the
    # deletion, re-created one clause down) fails HERE.
    assert _discover_admission_score(65, _score()) == 65

    # CONTROL 2 — the floor is still a floor, not an unconditional admit: a
    # genuinely low-scoring card is still refused. Without this the assertions
    # above pass for a function that returns `base_score` unconditionally.
    assert _discover_admission_score(20, _score()) < min_score

    # CONTROL 3 — the relation still decides, but now in RANK rather than
    # admission. If this ever fails, the Nah has stopped reading the relation.
    assert _score().multiplier < r.multiplier


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
async def test_a_nah_sport_with_no_relationship_is_served_and_ranked_below():
    """THE CONTROL that keeps the preference real — rewritten for #1927's wide
    half. It used to assert `== []`. The Nah is now a rank signal: the same
    game is served, and it ranks BELOW the copy the reader has a standing
    relationship with, so a rescue written as an unconditional `True` (or a
    Nah made inert) still fails here."""
    unrelated = await _served(_ctx())
    followed = await _served(_ctx({"follow"}))
    assert len(unrelated) == 1, "the Nah deleted the game — that is the retired filter"
    assert len(followed) == 1
    assert unrelated[0]["score"] < followed[0]["score"], (
        unrelated[0]["score"],
        followed[0]["score"],
    )
    assert any(r.startswith("sport_nah") for r in unrelated[0]["personalization_reasons"])


@pytest.mark.asyncio
async def test_a_rival_alone_is_served_without_a_standing_rescue():
    """A rival is inferred from a follow, not performed, so it sets no standing
    flag (asserted above). Under the wide half it needs none: the game is
    served like any other Nah-sport game, and the rival term ranks it as the
    scorer always did."""
    items = await _served(_ctx({"rival"}))
    assert len(items) == 1
    reasons = items[0]["personalization_reasons"]
    assert any(r.startswith("rival_") for r in reasons), reasons
    assert any(r.startswith("sport_nah") for r in reasons), reasons


@pytest.mark.asyncio
async def test_the_same_game_is_served_when_the_sport_is_not_a_nah():
    """THE CONTROL against a vacuous arm: if the harness were dropping this game
    for some reason of its own, this would be empty too."""
    assert len(await _served(_ctx(affinity=1.0))) == 1


@pytest.mark.asyncio
async def test_my_stuff_is_unchanged():
    """`my_teams_only` already exempted itself from the filter; this ship must
    not have made that exemption conditional on the new flag.

    A `rival` relation is the specimen: My Stuff admits the game because
    `my_teams_only` is true, NOT because of any rescue. (My Stuff also needs a
    relation of some kind to select the event at all, `feed.py:8887`, which is
    why the plain no-relation context cannot be used here.)"""
    assert len(await _served(_ctx({"rival"}), my_teams_only=True)) == 1
