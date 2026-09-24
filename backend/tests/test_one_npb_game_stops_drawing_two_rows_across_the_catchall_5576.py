"""Guard: an NPB game whose Polymarket row sits in the catch-all is ONE row. #5576.

THE SEARCH THIS EXISTS FOR. `/api/events/search?q=eagles`, 2026-09-24 05:3xZ
(latency/1074 at 390px; re-read by lane1/634 at 06:3xZ). Tomorrow's game, twice:

    15314060  Tohoku Rakuten Golden Eagles at Nippon Ham Fighters           baseball_other
    15317887  Tohoku Rakuten Golden Eagles at Hokkaido Nippon-Ham Fighters  baseball_npb

Same minute (2026-09-24 09:00Z). The first is the id-less Polymarket-born row;
the second is the Odds API row, `external_id` set, minted six days later and
unable to absorb the first (ruling 048 / gotcha #32). The Carp game the same
night was already ONE row, because both its rows are keyed `baseball_npb` and
#8100's name pass folds them. The Fighters claim is keyed `baseball_other`
because `teams` spells the club `Hokkaido Nippon-Ham Fighters` and #5576's
placer is exact, so it stays in the catch-all — and the only pass that compared
a catch-all with a league BY NAME was soccer-only.

THE MEASUREMENT (lane1/634, `artifacts-lane1-634/drive_5576.py`): the shipped
`fold_twin_events` driven over every production row in a minute where a
non-soccer `*_other` row and a same-sport league row agree exactly on one club,
2026-08-20 .. 2026-10-05, 40 rows, with the new branch OFF then ON:

    folded OFF 0 | ON 1 | NEW 1 | LOST 0
      NEW: 15314060 baseball_other -> kept 15317887 baseball_npb

Every other candidate in the export was refused, and the arms below pin the
reasons: past NPB pairs are `suspended` on both rows (not foldable — #5711 owns
why), `BC Dubai` is not a token subset of `Dubai Basketball`, and the tennis
pairs are id-less on both sides.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import event_twin_fold as tf
from app.utils.event_twin_fold import fold_twin_events

FIRST_PITCH = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)

CATCHALL = "baseball_other"
NPB = "baseball_npb"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Not a MagicMock, for the reason every #8100 suite gives: an auto-attribute
    mock makes every `external_id` truthy, and `external_id` truthiness is this
    licence's input.
    """

    def __init__(
        self,
        id,
        *,
        sport_key=NPB,
        home="Hokkaido Nippon-Ham Fighters",
        away="Tohoku Rakuten Golden Eagles",
        commence_time=FIRST_PITCH,
        external_id=None,
        espn_id=None,
        sources=None,
        status="scheduled",
        home_score=None,
        away_score=None,
    ):
        self.id = id
        self.sport_id = abs(hash(sport_key)) % 10**6
        self.sport = _Sport(self.sport_id, sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.external_id = external_id
        self.espn_id = espn_id
        self.win_probability_sources = sources
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.opening_home_probability = None
        self.opening_away_probability = None


def _fighters_pair(**claim_overrides):
    """The two production rows, as read 2026-09-24 06:3xZ."""
    claim = _Row(
        15314060,
        sport_key=CATCHALL,
        home="Nippon Ham Fighters",
        sources={"polymarket": 0.5},
    )
    for name, value in claim_overrides.items():
        setattr(claim, name, value)
    anchored = _Row(
        15317887,
        external_id="a20371b286aead",
        sources={"betting": 0.52},
    )
    return claim, anchored


# ── the ship ──────────────────────────────────────────────────────────────────


def test_search_stops_drawing_the_fighters_game_as_two_rows():
    claim, anchored = _fighters_pair()

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1, "one game must be one row"
    assert result.dropped_ids == [
        15314060
    ], "the id-less catch-all row is the one folded"


def test_the_one_row_still_carries_the_polymarket_price():
    """The survivor is the anchored row, so the claim's price must be unioned
    onto it — two rows traded for one that quietly lost a venue is not the ship."""
    claim, anchored = _fighters_pair()

    result = fold_twin_events([claim, anchored])

    assert result.events[0].id == 15317887
    assert result.merged_sources[15317887] == {"betting": 0.52, "polymarket": 0.5}


def test_the_fold_is_this_branch_and_nothing_else(monkeypatch):
    """Attribution: with the new predicate forced False the pair is two rows, as
    it was on master. If this goes green-on-both, some other pass is doing the
    work and the arms below are not testing what they claim."""
    monkeypatch.setattr(tf, "_catchall_claim_names_league_row", lambda *a, **k: False)
    claim, anchored = _fighters_pair()

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_the_longer_name_on_the_catchall_side_also_folds():
    """`_one_club_named_twice` is a containment in EITHER direction."""
    claim, anchored = _fighters_pair(
        home_team_name="Hokkaido Nippon-Ham Fighters Baseball"
    )

    assert len(fold_twin_events([claim, anchored]).events) == 1


def test_the_dispute_may_sit_on_the_away_side():
    claim, anchored = _fighters_pair(
        home_team_name="Hokkaido Nippon-Ham Fighters",
        away_team_name="Rakuten Golden Eagles",
    )

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


# ── the licence, refused arm by arm ───────────────────────────────────────────


def test_both_sides_differing_is_refused_across_the_catchall_too():
    """🔴 `Georgia v Florida` beside `West Georgia v North Florida` — the one
    measured false fold #8100 found. A catch-all makes no claim about the
    competition, which makes it WEAKER evidence, never a reason to relax the
    one-side-exact rule."""
    kickoff = datetime(2026, 5, 14, 22, 5, tzinfo=timezone.utc)
    georgia = _Row(
        14706238,
        sport_key=CATCHALL,
        away="Georgia",
        home="Florida",
        commence_time=kickoff,
    )
    west = _Row(
        14707767,
        sport_key="baseball_ncaa",
        away="West Georgia",
        home="North Florida",
        commence_time=kickoff,
        external_id="ncaa-wg",
    )

    assert len(fold_twin_events([georgia, west]).events) == 2


def test_a_catchall_row_carrying_a_provider_id_is_refused():
    """An anchored catch-all row is somebody's scheduled fixture; two anchored
    rows are a question for #1946, not for a spelling."""
    claim, anchored = _fighters_pair(external_id="pm-fixture-1")

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_an_espn_id_alone_anchors_the_catchall_row():
    claim, anchored = _fighters_pair(espn_id="401000001")

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_an_id_less_league_row_is_refused():
    claim, anchored = _fighters_pair()
    anchored.external_id = None

    assert len(fold_twin_events([claim, anchored]).events) == 2


@pytest.mark.parametrize("status", ["live", "suspended", "voided", ""])
def test_a_row_outside_the_foldable_statuses_refuses_the_pair(status):
    """Live: which row's score is current outranks any name question.
    Suspended: every finished NPB pair in the production export reads
    `suspended` on BOTH rows, and this pass does not fold them — that state is
    #5711's to explain, not this pass's to paper over. Pinned so a widening of
    the status set is a decision someone makes, not a side effect."""
    claim, anchored = _fighters_pair(status=status)

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_a_name_that_is_not_a_token_subset_is_refused():
    """Production specimen from the same export: `BC Dubai` x `Dubai
    Basketball` (15314581 / 15292394). One game, but neither name contains the
    other, and this pass does not guess."""
    kickoff = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
    claim = _Row(
        15314581,
        sport_key="basketball_other",
        away="Real Madrid",
        home="BC Dubai",
        commence_time=kickoff,
    )
    anchored = _Row(
        15292394,
        sport_key="basketball_euroleague",
        away="Real Madrid",
        home="Dubai Basketball",
        commence_time=kickoff,
        external_id="el-1",
    )

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_a_different_sport_is_never_reached():
    """The prefix test: a `basketball_other` claim never folds onto baseball."""
    claim, anchored = _fighters_pair()
    claim.sport_id = abs(hash("basketball_other")) % 10**6
    claim.sport = _Sport(claim.sport_id, "basketball_other")

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_a_bare_other_key_names_no_sport_and_is_refused():
    """`_catchall_sport_prefix("_other")` is `""`, and `startswith("")` is True
    for every league in the table."""
    claim, anchored = _fighters_pair()
    claim.sport_id = abs(hash("_other")) % 10**6
    claim.sport = _Sport(claim.sport_id, "_other")

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_one_minute_apart_is_not_reached():
    claim, anchored = _fighters_pair(commence_time=FIRST_PITCH + timedelta(minutes=1))

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_a_different_opponent_never_folds():
    claim, anchored = _fighters_pair()
    anchored.away_team_name = "Orix Buffaloes"

    assert len(fold_twin_events([claim, anchored]).events) == 2


def test_a_catchall_claim_naming_two_league_rows_is_refused_whole():
    """Two anchored league rows in two different keys of the family, both
    naming the claim: the catch-all cannot say which it is, so nothing folds."""
    claim, anchored = _fighters_pair()
    second = _Row(
        15399999, sport_key="baseball_npb_postseason", external_id="other-feed-1"
    )

    result = fold_twin_events([claim, anchored, second])

    assert 15314060 not in result.dropped_ids


def test_the_exact_identity_catchall_fold_is_untouched():
    """Rung two — byte-identical names across the catch-all — still folds, and
    does so without this branch."""
    claim, anchored = _fighters_pair(home_team_name="Hokkaido Nippon-Ham Fighters")

    assert len(fold_twin_events([claim, anchored]).events) == 1
