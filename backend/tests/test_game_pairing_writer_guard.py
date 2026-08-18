"""#1947 / #1945 — the writer that stamped another game's identity on a real row.

The attended mini-census on #1947 inverted the open verdict: the four "MLB
duplicate pairs" were FIVE REAL SCHEDULED GAMES carrying the Aug-17 game's
``espn_id`` and final score (ruling 079). This suite pins the writers.

Every fixture below is a PRODUCTION specimen, transcribed from that census:

    our row 15199901  Tigers @ Pirates   commence 2026-08-19T16:35Z  (correct)
    wrong  espn_id    401816564          ESPN: 2026-08-17T23:00Z FINAL
    right  espn_id    401816587          ESPN: 2026-08-19T16:35Z SCHEDULED

Separation is 41.6h, which is why the team pair alone could never tell them
apart — and why a doubleheader (~6h) still must.

Anchors are absolute datetimes, not offsets from ``now`` (gotcha #44): these
assertions are about a fixed pair of real games, so the wall clock is not
allowed a vote.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.game_pairing import (
    PREGAME_LIVE_GRACE,
    SAME_GAME_MAX_SEPARATION,
    Pairing,
    live_write_is_premature,
    pair_verdict,
)


def _dt(*args):
    return datetime(*args, tzinfo=timezone.utc)


class _Row:
    """A stand-in ORM row: any column not named here reads as NULL.

    Deliberately permissive on ABSENT attributes and strict on the ones the
    specimen actually sets — the assertion is about `espn_id`, and a fake that
    has to enumerate every column of `events` to run is a fake that stops being
    run.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, _name):
        return None


# The five production specimens: (label, our commence, the Aug-17 game ESPN
# reported live when the contamination was written).
SPECIMENS = [
    ("15199901 Tigers @ Pirates", _dt(2026, 8, 19, 16, 35), _dt(2026, 8, 17, 23, 0)),
    ("15199882 Padres @ Mets", _dt(2026, 8, 19, 17, 10), _dt(2026, 8, 17, 23, 10)),
    ("15200229 D-backs @ Red Sox", _dt(2026, 8, 19, 20, 10), _dt(2026, 8, 17, 23, 10)),
    ("15199886 Marlins @ Phillies", _dt(2026, 8, 19, 22, 5), _dt(2026, 8, 17, 22, 40)),
    ("15200216 Athletics @ Royals", _dt(2026, 8, 20, 18, 10), _dt(2026, 8, 17, 23, 40)),
]


class TestPairVerdictOnProductionSpecimens:
    """The predicate must separate every real specimen."""

    @pytest.mark.parametrize("label,ours,theirs", SPECIMENS)
    def test_series_sibling_is_different(self, label, ours, theirs):
        assert pair_verdict(ours, theirs) is Pairing.DIFFERENT, label

    @pytest.mark.parametrize("label,ours,theirs", SPECIMENS)
    def test_the_true_game_is_same(self, label, ours, theirs):
        # The correctly-anchored game is the row's own time, to the minute —
        # the census verified `commence_time` was never wrong.
        assert pair_verdict(ours, ours) is Pairing.SAME, label

    def test_doubleheader_still_pairs(self):
        """The constant must not be so tight it splits a real doubleheader.

        MLB day/night: game 1 13:05 local, game 2 19:05 local — 6h. Both are
        legitimately "the same slate" for pairing purposes; what must NOT pair
        is the next day's game.
        """
        game1 = _dt(2026, 8, 17, 17, 5)
        game2 = game1 + timedelta(hours=6)
        assert pair_verdict(game1, game2) is Pairing.SAME

    def test_next_day_series_game_does_not_pair(self):
        game1 = _dt(2026, 8, 17, 17, 5)
        assert pair_verdict(game1, game1 + timedelta(hours=24)) is Pairing.DIFFERENT

    def test_boundary_is_inclusive_at_the_constant(self):
        base = _dt(2026, 8, 17, 12, 0)
        assert pair_verdict(base, base + SAME_GAME_MAX_SEPARATION) is Pairing.SAME
        assert pair_verdict(
            base, base + SAME_GAME_MAX_SEPARATION + timedelta(seconds=1)
        ) is Pairing.DIFFERENT

    def test_direction_does_not_matter(self):
        a, b = _dt(2026, 8, 19, 16, 35), _dt(2026, 8, 17, 23, 0)
        assert pair_verdict(a, b) is pair_verdict(b, a)


class TestCouldNotCheckIsNotSame:
    """Doctrine: could-not-check never renders as nothing-to-report."""

    def test_missing_their_time_is_unknown_not_same(self):
        assert pair_verdict(_dt(2026, 8, 19, 16, 35), None) is Pairing.UNKNOWN

    def test_missing_our_time_is_unknown_not_same(self):
        assert pair_verdict(None, _dt(2026, 8, 17, 23, 0)) is Pairing.UNKNOWN

    def test_both_missing_is_unknown(self):
        assert pair_verdict(None, None) is Pairing.UNKNOWN

    def test_unknown_is_never_same(self):
        """The whole point: callers gate on `is Pairing.SAME`, so UNKNOWN refuses.

        If this ever became a 2-valued bool, an absent date would read as
        agreement and the defect returns silently.
        """
        assert Pairing.UNKNOWN is not Pairing.SAME
        assert Pairing.DIFFERENT is not Pairing.SAME


class TestPrematureLiveGuard:
    """A row that has not started cannot hold live state — any provider."""

    @pytest.mark.parametrize("label,ours,theirs", SPECIMENS)
    def test_specimen_rows_refuse_live_writes(self, label, ours, theirs):
        # `now` is the moment the contamination was observed: the Aug-17 game
        # was live, the Aug-19/20 rows had not started.
        now = _dt(2026, 8, 17, 23, 30)
        assert live_write_is_premature(ours, now) is True, label

    def test_a_genuinely_live_game_is_not_premature(self):
        commence = _dt(2026, 8, 17, 23, 0)
        assert live_write_is_premature(commence, commence + timedelta(minutes=40)) is False

    def test_grace_tolerates_first_pitch_jitter(self):
        commence = _dt(2026, 8, 17, 23, 0)
        just_before = commence - PREGAME_LIVE_GRACE + timedelta(minutes=1)
        assert live_write_is_premature(commence, just_before) is False

    def test_missing_time_fails_open(self):
        """Deliberately different from `pair_verdict`, and deliberately stated.

        This guard's job is to REFUSE a write; with no commence_time there is no
        invariant to enforce and failing closed would stop every live score for
        a row missing a time. The pairing verdict fails closed because it grants
        an IDENTITY. Two guards, two directions, both on purpose.
        """
        assert live_write_is_premature(None, _dt(2026, 8, 17, 23, 30)) is False
        assert live_write_is_premature(_dt(2026, 8, 19, 16, 35), None) is False


class TestTheEspnIdWriterRefusesTheSpecimen:
    """The call site, not just the predicate — ``sync_scheduled_events``.

    FAILS-FIRST, asserted rather than claimed (the #1918 pattern): each case
    proves BOTH that the pre-fix predicate would have written the id, and that
    the guard now refuses it. Delete the guard and half 2 fails; delete the
    defect and half 1 fails.
    """

    @staticmethod
    def _run(
        our_commence,
        espn_date,
        espn_id="401816564",
        prior_espn_id=None,
        commence_time_source="statpal",
    ):
        import asyncio

        from app.utils import espn_helpers

        class _Team(_Row):
            def __init__(self, name):
                super().__init__(display_name=name, name=name)

        class _Sport:
            id = 53232
            key = "baseball_mlb"

        event = _Row(
            id=15199901,
            espn_id=prior_espn_id,
            sport=_Sport(),
            sport_id=_Sport.id,
            home_team_name="Pittsburgh Pirates",
            away_team_name="Detroit Tigers",
            home_team_normalized=None,
            away_team_normalized=None,
            home_team_id=1,
            away_team_id=2,
            commence_time=our_commence,
            commence_time_source=commence_time_source,
            broadcast_info=None,
            llm_importance=None,
            status="scheduled",
        )
        ee = _Row(
            espn_id=espn_id,
            home_team=_Team("Pittsburgh Pirates"),
            away_team=_Team("Detroit Tigers"),
            date=espn_date,
            broadcasts=[],
            season_type=None,
        )

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def all(self):
                return self._rows

        calls = {"n": 0}

        class _Session:
            async def execute(self, *_a, **_k):
                calls["n"] += 1
                return _Result([event] if calls["n"] == 1 else [])

        async def _noop_upsert(*_a, **_k):
            return None

        async def _noop_identities(*_a, **_k):
            return None

        orig_upsert = espn_helpers.upsert_team
        orig_ident = espn_helpers.register_espn_team_identities
        espn_helpers.upsert_team = _noop_upsert
        espn_helpers.register_espn_team_identities = _noop_identities
        try:
            stats: dict = {}
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                espn_helpers.sync_scheduled_events(
                    _Session(), "baseball_mlb", [ee], stats,
                )
            )
        finally:
            espn_helpers.upsert_team = orig_upsert
            espn_helpers.register_espn_team_identities = orig_ident
        return event, stats

    def test_names_really_do_match_so_the_prefix_code_would_have_written_it(self):
        """Half 1 — the defect was real: the name match hits."""
        from app.tasks.espn_sync import espn_team_matches, get_event_name_variations

        class _Team(_Row):
            def __init__(self):
                super().__init__(
                    display_name="Pittsburgh Pirates", name="Pittsburgh Pirates",
                )

        class _Away(_Row):
            def __init__(self):
                super().__init__(
                    display_name="Detroit Tigers", name="Detroit Tigers",
                )

        event = _Row(
            home_team_name="Pittsburgh Pirates",
            away_team_name="Detroit Tigers",
        )
        home_names, away_names = get_event_name_variations(event)
        assert espn_team_matches(home_names, _Team())
        assert espn_team_matches(away_names, _Away())

    def test_the_aug17_id_is_refused_on_the_aug19_row(self):
        """Half 2 — the production specimen, refused."""
        event, stats = self._run(
            our_commence=_dt(2026, 8, 19, 16, 35),
            espn_date=_dt(2026, 8, 17, 23, 0),
        )
        assert event.espn_id is None, (
            "the Aug-17 game's espn_id was stamped on the Aug-19 row — this is "
            "#1947 exactly"
        )
        assert stats.get("scheduled_pair_refused") == 1

    def test_the_correct_game_is_still_stamped(self):
        """The guard must not stop the id it exists to let through."""
        event, stats = self._run(
            our_commence=_dt(2026, 8, 19, 16, 35),
            espn_date=_dt(2026, 8, 19, 16, 35),
            espn_id="401816587",
        )
        assert event.espn_id == "401816587"
        assert stats.get("scheduled_pair_refused", 0) == 0

    def test_a_wrong_id_cannot_drag_the_game_onto_another_day(self):
        """The 2026-08-18 escalation, measured in production.

        Match arm 1 keys on the row's OWN espn_id, so it bypasses the pairing
        gate (correctly — that arm is id-anchored, ruling 048 arm A). But when
        the id is wrong, "refine the time from the id" moved five real Aug-19
        games to Aug-18, after which no row existed for the Aug-19 games. A
        correction of days is evidence the id is wrong; the game does not move
        to meet it.
        """
        aug19 = _dt(2026, 8, 19, 16, 35)
        event, stats = self._run(
            our_commence=aug19,
            espn_date=_dt(2026, 8, 18, 22, 40),  # the next-day game the bad id names
            espn_id="401816564",
            prior_espn_id="401816564",  # arm 1: the row already carries it
        )
        assert event.commence_time == aug19, "the game was dragged onto another day"
        assert stats.get("scheduled_commence_move_refused") == 1

    def test_a_minutes_level_correction_still_applies(self):
        """The refusal must not break the refinement the correction exists for."""
        ours = _dt(2026, 8, 19, 16, 35)
        theirs = _dt(2026, 8, 19, 16, 50)  # 15 min — past the 300s no-op threshold
        event, _ = self._run(
            our_commence=ours,
            espn_date=theirs,
            espn_id="401816587",
            prior_espn_id="401816587",
            commence_time_source="espn",
        )
        assert event.commence_time == theirs

    def test_espn_without_a_date_is_refused(self):
        event, _ = self._run(
            our_commence=_dt(2026, 8, 19, 16, 35), espn_date=None,
        )
        assert event.espn_id is None


class TestTheGuardsCannotBeSilentlyRemoved:
    """Source-shape assertions — the three sites keyed on the team pair alone."""

    def test_scheduled_pass_gates_on_the_pairing_verdict(self):
        import inspect

        from app.utils import espn_helpers

        src = inspect.getsource(espn_helpers.sync_scheduled_events)
        assert "pair_verdict(" in src and "Pairing.SAME" in src

    def test_statpal_schedule_sync_gates_both_the_pairing_and_the_write(self):
        import inspect

        from app.tasks import statpal_sync

        src = inspect.getsource(statpal_sync._sync_statpal_schedules)
        assert "pair_verdict(" in src, "live_by_teams is keyed on the team pair alone"
        assert "live_write_is_premature(" in src

    def test_statpal_live_scores_gates_the_write(self):
        import inspect

        from app.tasks import statpal_sync

        src = inspect.getsource(statpal_sync._sync_statpal_livescores)
        assert "live_write_is_premature(" in src, (
            "the propagator's `status='live'` query has no time bound"
        )


class TestOnePredicateOneImplementation:
    """espn_helpers must not carry a second copy of the premature guard."""

    def test_espn_helpers_reexports_the_shared_guard(self):
        from app.utils import espn_helpers, game_pairing

        assert (
            espn_helpers.espn_live_write_is_premature
            is game_pairing.live_write_is_premature
        )
        assert espn_helpers._PREGAME_LIVE_GRACE is game_pairing.PREGAME_LIVE_GRACE

    def test_no_second_grace_constant_is_defined_in_espn_helpers(self):
        import inspect

        from app.utils import espn_helpers

        src = inspect.getsource(espn_helpers)
        assert "_PREGAME_LIVE_GRACE = timedelta(" not in src, (
            "espn_helpers re-declared the grace constant — the two providers "
            "drifting apart is exactly what #1945 was"
        )
