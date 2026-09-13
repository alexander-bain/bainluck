"""Guard: the Europa League tie gets one card, not two three hours apart (#5905).

THE PAGE THIS EXISTS FOR. `/sports/soccer_uefa_europa_league`, 2026-09-13: 6 of
24 "Upcoming" cards were ghosts — a second card for a tie already on the page,
exactly three hours later, with no crest and no number. On La Liga the same rows
had no twin to give them away, so **Sevilla v Barcelona was simply advertised at
the wrong hour** (22:00Z for a 19:00Z kick-off) and the Madrid derby likewise.

WHAT THESE TESTS ARE ACTUALLY DEFENDING. Not "a function subtracts three hours".
The ways this recovery can go wrong and reach Alex:

* it does not fire, and the tie is served twice (`test_the_europa_ghost_folds…`);
* it fires on a row a schedule provider anchored, moving a REPORTED start
  (`test_an_anchored_row_is_never_moved`);
* it fires outside soccer, where the pad is a spread and not a constant
  (`test_mma_is_never_moved`, `test_the_pad_is_not_inherited_by_other_sports`);
* it fires on `kalshi_ticker`, whose midnight is a stand-in and not this instant
  (`test_a_ticker_midnight_is_never_moved`);
* it breaks a fold that works today (`test_it_cannot_unfold_a_pair_that_agrees`);
* it silently disables the whole fold by touching an unloaded relationship
  (`test_an_unloaded_sport_relationship_does_not_raise_or_fold`).
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events, twin_fold_key
from app.utils.kalshi_occurrence_start import (
    KALSHI_EXPECTED_EXPIRATION_PAD,
    KALSHI_RECOVERY_STAMP,
    kalshi_occurrence_scheduled_start,
    recover_kalshi_occurrence_starts,
)

#: Olympiakos v Jagiellonia, Europa League, as measured on production
#: 2026-09-13: the anchored row at 19:00Z and the Kalshi-timed ghost at 22:00Z.
KICKOFF = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)
EXPECTED_EXPIRATION = datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold and the recovery read.

    Deliberately not a MagicMock: an auto-attribute mock makes every
    `external_id` truthy and every `commence_time_source` a live object, which
    would make the two refusal tests below pass without any refusal existing.
    """

    def __init__(
        self,
        id,
        *,
        sport_id=7,
        sport_key="soccer_uefa_europa_league",
        home="Olympiakos",
        away="Jagiellonia",
        commence_time=KICKOFF,
        commence_time_source="odds_api",
        external_id=None,
        espn_id=None,
        home_score=None,
        away_score=None,
        sources=None,
    ):
        self.id = id
        self.sport_id = sport_id
        self.sport = _Sport(sport_key) if sport_key else None
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.commence_time_source = commence_time_source
        self.external_id = external_id
        self.espn_id = espn_id
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = sources


def _europa_pair():
    """The two production rows behind Alex's 12:19Z LOOK."""
    real = _Row(
        15298547,
        commence_time=KICKOFF,
        commence_time_source="odds_api",
        external_id="a1b2c3…",
        sources={"betting": 0.81},
    )
    ghost = _Row(
        15307677,
        commence_time=EXPECTED_EXPIRATION,
        commence_time_source="kalshi",
        external_id=None,
        sources={"kalshi": 0.86},
    )
    return real, ghost


# ── the ship ──────────────────────────────────────────────────────────────────


def test_the_marquee_orphan_is_served_at_its_kickoff_not_three_hours_late():
    """The worst of #5905, and the half no fold can reach.

    Sevilla v Barcelona has no Odds API row — Kalshi lists before Odds API does,
    so ours is the only row there is. It is not duplicated; it is simply
    advertised at 22:00Z for a 19:00Z kick-off. A reader is told 3:00 PM PT for
    a game that starts at 12:00 PM PT.
    """
    sevilla = _Row(
        15307701,
        sport_key="soccer_spain_la_liga",
        home="Sevilla",
        away="Barcelona",
        commence_time=datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc),
        commence_time_source="kalshi",
        sources={"kalshi": 0.31},
    )

    assert recover_kalshi_occurrence_starts([sevilla]) == 1
    assert sevilla.commence_time == datetime(2026, 9, 19, 19, 0, tzinfo=timezone.utc)


def test_the_lone_row_is_still_served_it_is_not_hidden():
    """Kalshi is the only venue holding next weekend's La Liga.

    Correcting the hour must not cost the reader the card or the price — the
    fold returns it, with its number, at the right time.
    """
    sevilla = _Row(
        15307701,
        sport_key="soccer_spain_la_liga",
        home="Sevilla",
        away="Barcelona",
        commence_time=datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc),
        commence_time_source="kalshi",
        sources={"kalshi": 0.31},
    )

    result = fold_twin_events([sevilla])

    assert [e.id for e in result.events] == [15307701]
    assert result.events[0].win_probability_sources == {"kalshi": 0.31}
    assert result.events[0].commence_time.hour == 19


def test_a_row_nobody_should_touch_keeps_its_stored_hour():
    """The recovery must be a no-op for the overwhelming majority of rows."""
    anchored = _Row(1, commence_time=KICKOFF, external_id="a1b2c3…")

    assert recover_kalshi_occurrence_starts([anchored]) == 0
    assert anchored.commence_time == KICKOFF


def test_one_unreadable_row_does_not_cost_the_page_its_other_corrections():
    """Gotcha #42 applied to a stage."""

    class _Exploding:
        @property
        def commence_time_source(self):
            raise RuntimeError("this row is not readable")

    good = _Row(
        1,
        commence_time=EXPECTED_EXPIRATION,
        commence_time_source="kalshi",
    )

    assert recover_kalshi_occurrence_starts([_Exploding(), good]) == 1
    assert good.commence_time == KICKOFF


def test_the_europa_ghost_folds_into_the_real_card():
    real, ghost = _europa_pair()

    result = fold_twin_events([real, ghost])

    assert [e.id for e in result.events] == [
        15298547
    ], "the anchored 19:00Z row must be the one card served"
    assert result.dropped_ids == [15307677]


def test_the_reader_keeps_the_kalshi_number_the_ghost_was_carrying():
    """Folding a card must not cost the venue that was only on the dropped row.

    The ghost is the ONLY row holding Kalshi here, so a fold that merely hides it
    would trade a duplicate card for a less-blended one — which is the standing
    ruling the fold exists under, not an improvement.
    """
    real, ghost = _europa_pair()

    result = fold_twin_events([real, ghost])

    assert result.merged_sources[15298547] == {"betting": 0.81, "kalshi": 0.86}


def test_without_the_recovery_the_pair_is_three_hours_apart_and_cannot_fold():
    """The strawman: pins that the fold is doing the work, not the fixture.

    If this test ever passes while the one above fails, the pair is folding for
    some reason other than #5905 and the guard above is vacuous.
    """
    real, ghost = _europa_pair()
    ghost.commence_time_source = "odds_api"  # take the recovery away

    assert twin_fold_key(real) != twin_fold_key(ghost)
    assert fold_twin_events([real, ghost]).dropped_ids == []


def test_the_recovered_key_is_the_anchored_rows_key_to_the_minute():
    """The key itself is untouched — it is the minute offered to it that moves."""
    real, ghost = _europa_pair()

    recover_kalshi_occurrence_starts([real, ghost])

    assert twin_fold_key(ghost) == twin_fold_key(real)
    assert twin_fold_key(ghost)[3] == KICKOFF


# ── the refusals, each one a way this could move a time it must not ───────────


def test_an_anchored_row_is_never_moved():
    """`external_id` set means Odds API or ESPN REPORTED this start."""
    anchored = _Row(
        1,
        commence_time=EXPECTED_EXPIRATION,
        commence_time_source="kalshi",
        external_id="7fe8727a…",
    )

    assert kalshi_occurrence_scheduled_start(anchored, "soccer_epl") is None


def test_a_ticker_midnight_is_never_moved():
    """`kalshi_ticker` is a DATE resolved to midnight, not this instant.

    Subtracting the pad from it would produce 21:00 the previous day and serve
    that as a kick-off — a stand-in moved onto a different date entirely.
    """
    midnight = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)
    row = _Row(1, commence_time=midnight, commence_time_source="kalshi_ticker")

    assert kalshi_occurrence_scheduled_start(row, "soccer_epl") is None


def test_mma_is_never_moved():
    """Measured 2026-09-13: MMA's pad is 255/265/275/285/295/345 minutes.

    A spread, not a constant — a fight card's expected expiration tracks a card
    that runs long. Applying soccer's exact 180 here would fabricate an hour.
    """
    row = _Row(
        1,
        sport_key="mma_mixed_martial_arts",
        commence_time=EXPECTED_EXPIRATION,
        commence_time_source="kalshi",
    )

    assert kalshi_occurrence_scheduled_start(row, "mma_mixed_martial_arts") is None


def test_the_pad_is_not_inherited_by_other_sports():
    for key in (
        "americanfootball_nfl",
        "baseball_mlb",
        "basketball_nba",
        "boxing_boxing",
        "tennis_atp_us_open",
        "icehockey_nhl",
    ):
        row = _Row(
            1,
            sport_key=key,
            commence_time=EXPECTED_EXPIRATION,
            commence_time_source="kalshi",
        )
        assert kalshi_occurrence_scheduled_start(row, key) is None, key


def test_an_unknown_sport_key_is_refused_rather_than_assumed():
    row = _Row(1, commence_time=EXPECTED_EXPIRATION, commence_time_source="kalshi")

    assert kalshi_occurrence_scheduled_start(row, None) is None


def test_every_soccer_league_key_is_reached_not_just_the_ones_we_listed():
    """~40 soccer keys and growing; the gate is a prefix for that reason."""
    for key in (
        "soccer_spain_la_liga",
        "soccer_uefa_europa_league",
        "soccer_italy_coppa_italia",
        "soccer_conmebol_copa_libertadores",
        "soccer_a_competition_added_next_week",
    ):
        row = _Row(
            1,
            sport_key=key,
            commence_time=EXPECTED_EXPIRATION,
            commence_time_source="kalshi",
        )
        assert kalshi_occurrence_scheduled_start(row, key) == KICKOFF, key


# ── it must not cost anything that works today ────────────────────────────────


def test_it_cannot_unfold_a_pair_that_agrees():
    """Measured: the ghost census has no 0-minute bucket.

    Not one Kalshi-timed soccer row shares a minute with its twin today, so
    there is no correct fold for the shift to spoil. If one ever did, this is
    what would catch it — the recovery would move it AWAY from its partner.
    """
    real, ghost = _europa_pair()
    ghost.commence_time = KICKOFF  # the hypothetical already-agreeing row

    assert fold_twin_events([real, ghost]).dropped_ids == []
    assert ghost.commence_time == KICKOFF - KALSHI_EXPECTED_EXPIRATION_PAD


def test_two_different_fixtures_three_hours_apart_still_do_not_fold():
    """The shift must not reach a DIFFERENT match between other clubs."""
    real = _Row(1, home="Celtic", away="Ferencvaros", commence_time=KICKOFF)
    other = _Row(
        2,
        home="Plzen",
        away="Union Gilloise",
        commence_time=EXPECTED_EXPIRATION,
        commence_time_source="kalshi",
    )

    assert fold_twin_events([real, other]).dropped_ids == []


def test_an_unloaded_sport_relationship_does_not_raise_or_move_the_row():
    """Gotcha #42: every fold call site wraps this in a bare `except`.

    A lazy load from inside the recovery would not fail loudly — it would
    disable the whole stage for that page. So an object that cannot answer for
    its sport must read as "not soccer" and leave the row exactly where it is.
    """

    class _NoSport:
        id = 1
        sport_id = 7
        home_team_name = "Olympiakos"
        away_team_name = "Jagiellonia"
        commence_time = EXPECTED_EXPIRATION
        commence_time_source = "kalshi"
        external_id = None
        espn_id = None
        home_score = None
        away_score = None
        win_probability_sources = None

        @property
        def sport(self):  # pragma: no cover - must never be reached
            raise AssertionError("the key must not touch an unloaded relationship")

    row = _NoSport()

    assert recover_kalshi_occurrence_starts([row]) == 0
    assert twin_fold_key(row)[3] == EXPECTED_EXPIRATION


def test_the_pad_is_the_measured_constant_not_a_tolerance():
    """180 minutes exactly, 11 of 11 anchored comparisons on 2026-09-13.

    Pinned so a later widening has to argue with the census rather than nudge a
    number — an approximate pad turns an exact recovery into a guess.
    """
    assert KALSHI_EXPECTED_EXPIRATION_PAD == timedelta(hours=3)


# ── the branch production actually takes ──────────────────────────────────────


def test_a_real_orm_row_is_corrected_and_is_NOT_left_dirty():
    """The safety claim, on the object type production hands this.

    Everything above runs the plain-assignment arm, because its rows are test
    doubles. That arm is the one production NEVER takes, so without this test
    the load-bearing half — "a served reading can never be flushed into
    `events`" — would be asserted by a docstring and nothing else.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.models.models import Event, Sport

    row = Event(
        id=15307701,
        sport_id=7,
        home_team_name="Sevilla",
        away_team_name="Barcelona",
        commence_time=datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc),
        commence_time_source="kalshi",
        external_id=None,
    )
    row.sport = Sport(key="soccer_spain_la_liga")

    assert recover_kalshi_occurrence_starts([row]) == 1
    assert row.commence_time == datetime(2026, 9, 19, 19, 0, tzinfo=timezone.utc)
    assert not sa_inspect(row).attrs["commence_time"].history.has_changes(), (
        "the recovery must use set_committed_value; a plain assignment would "
        "make the next flush write a serve-time reading into events"
    )


def test_an_orm_row_whose_sport_was_not_eager_loaded_is_left_alone():
    """Documents the REACH of this ship, so nobody over-reads it.

    `GET /api/events` (list and search) and `/api/feed` `selectinload(Event.sport)`
    before folding, so their rows are corrected. `/api/teams/{identifier}` and
    `/api/leagues/{sport_key}` do not, so theirs are served exactly as the
    database holds them — unchanged from today, never wrong in a NEW way, and
    the one-line fix is an eager load on routes this ship does not own.
    """
    from app.models.models import Event

    row = Event(
        id=15307701,
        sport_id=7,
        home_team_name="Sevilla",
        away_team_name="Barcelona",
        commence_time=datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc),
        commence_time_source="kalshi",
        external_id=None,
    )

    assert recover_kalshi_occurrence_starts([row]) == 0
    assert row.commence_time == datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc)


# ── the same objects, folded more than once ───────────────────────────────────
#
# Found by authority/179 on this sha before it landed, and latent rather than
# live: `/api/leagues/{sport_key}` folds the same upcoming rows twice in one
# request, and it is the one route whose query does not eager-load `Event.sport`,
# so nothing fires there today. These pin the arithmetic anyway, because the
# thing that makes it live is a one-line eager load on someone else's route.


def test_folding_the_same_rows_twice_moves_the_hour_once():
    """The recovery keys on a field it does not change, so it must self-stop.

    Without the stamp this is 16:00Z — a kick-off served three hours BEFORE the
    whistle, which is a worse lie than the three-hours-late one this ship fixes.
    """
    real, ghost = _europa_pair()
    rows = [real, ghost]

    fold_twin_events(rows)
    fold_twin_events(rows)

    assert ghost.commence_time == KICKOFF
    assert real.commence_time == KICKOFF


def test_the_leagues_route_folds_the_same_objects_twice_in_one_request():
    """The caller shape, not a synthetic repeat.

    `league_futures.py:2483` folds `_g_events`, then `:2543` folds
    `[*upcoming, *results, *unreported]` with no re-query between them — the same
    row objects, twice. A reader on that page must be told one hour.
    """
    real, ghost = _europa_pair()
    upcoming = [real, ghost]
    results = [_Row(99, home="Roma", away="Lille", commence_time=KICKOFF)]

    fold_twin_events(upcoming)  # _folded_upcoming
    fold_twin_events([*upcoming, *results])  # _folded_past_rails

    assert ghost.commence_time == KICKOFF, (
        "the second fold subtracted a second pad: 19:00Z kick-off served at 16:00Z"
    )


def test_a_third_and_fourth_pass_change_nothing_either():
    """Idempotent, not merely twice-safe — no caller promises a count of folds."""
    _, ghost = _europa_pair()

    for _ in range(4):
        recover_kalshi_occurrence_starts([ghost])

    assert ghost.commence_time == KICKOFF


def test_a_second_pass_reports_no_corrections_so_a_count_is_never_doubled():
    """The return value is corrections MADE, and a caller may report it."""
    _, ghost = _europa_pair()

    assert recover_kalshi_occurrence_starts([ghost]) == 1
    assert recover_kalshi_occurrence_starts([ghost]) == 0


def test_it_is_the_stamp_that_stops_the_second_pass_and_nothing_else():
    """Anti-vacuous: prove the guard is load-bearing.

    If the second pass were a no-op for some other reason — a changed source, a
    guard somewhere else — this test would pass with the stamp deleted and the
    three above would be worth nothing.
    """
    _, ghost = _europa_pair()

    assert recover_kalshi_occurrence_starts([ghost]) == 1
    assert getattr(ghost, KALSHI_RECOVERY_STAMP) is True

    delattr(ghost, KALSHI_RECOVERY_STAMP)

    assert recover_kalshi_occurrence_starts([ghost]) == 1
    assert ghost.commence_time == KICKOFF - KALSHI_EXPECTED_EXPIRATION_PAD


def test_a_real_orm_row_folded_twice_moves_once_and_is_still_not_dirty():
    """The stamp on the object type production hands this.

    An unmapped attribute must not become a pending write: the mapper does not
    map it, so there is nothing to flush — but that is the claim, and this is
    where it is checked rather than asserted in a docstring.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.models.models import Event, Sport

    row = Event(
        id=15307701,
        sport_id=7,
        home_team_name="Sevilla",
        away_team_name="Barcelona",
        commence_time=datetime(2026, 9, 19, 22, 0, tzinfo=timezone.utc),
        commence_time_source="kalshi",
        external_id=None,
    )
    row.sport = Sport(key="soccer_spain_la_liga")

    assert recover_kalshi_occurrence_starts([row]) == 1
    assert recover_kalshi_occurrence_starts([row]) == 0
    assert row.commence_time == datetime(2026, 9, 19, 19, 0, tzinfo=timezone.utc)

    state = sa_inspect(row)
    assert not state.attrs["commence_time"].history.has_changes()
    assert KALSHI_RECOVERY_STAMP not in {attr.key for attr in state.mapper.attrs}, (
        "the stamp must be a name the mapper does not know, or it is a column "
        "write wearing a sentinel's clothes"
    )


def test_the_lazy_safe_sport_read_is_public_and_its_old_name_still_resolves():
    """`#5918`'s soccer gate imports this; two copies of it is how one rots.

    The private alias stays because a branch based on the sha that had only the
    private name must keep importing.
    """
    from app.utils import kalshi_occurrence_start as mod

    row = _Row(1, sport_key="soccer_spain_la_liga")

    assert mod.loaded_sport_key(row) == "soccer_spain_la_liga"
    assert mod._loaded_sport_key is mod.loaded_sport_key
    assert "loaded_sport_key" in mod.__all__
