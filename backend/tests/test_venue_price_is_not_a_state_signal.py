"""live/042 — a venue price tick is never a state signal.

Six US Open matches served ``{"status": "live", "completed_at": "..."}`` from
``/api/events/{id}`` on the morning of 2026-09-02. A match cannot be running and
finished at once, and neither half was true: ESPN, the authority, had all six
SCHEDULED to resume that afternoon with partial set scores in its notes. They
had been suspended, not played out.

Two writers produced that state, and they fed each other:

**The HOLD.** ``game_may_still_be_running`` reads the last post-commence
snapshot as evidence the game is still being played. Its query counted every
source. Kalshi's live poll writes a ``win_prob_snapshots`` row every two
minutes, so the guard's 30-minute window never emptied and the staleness net
held the row live indefinitely — ``held_still_running``, forever, renewed by a
price.

**The FLIP.** When Kalshi did go quiet long enough for the net to close the row,
it stamped a ``completed_at`` derived from the last KALSHI TICK and a
``final_result`` off a mid-match score. The next Odds API scores poll then saw
``completed: false`` with a start in the past, wrote ``status='live'`` straight
back over the settlement, and left ``completed_at`` where it was — because
nothing on that path clears it. Lap after lap.

MEASURED, production 2026-09-02T13:43Z. Every post-commence
``win_prob_snapshots`` row on all seven candidate events was ``source='kalshi'``
— 1,037 rows, zero from ESPN, MLB, stat_model or StatPal:

    event_id   source   n    last_snap
    15293686   kalshi    88  13:43:56Z
    15293702   kalshi   115  13:43:54Z
    15293705   kalshi   191  13:47:29Z
    15293808   kalshi    31  12:21:38Z
    15293822   kalshi   141  13:46:23Z
    15295047   kalshi   244  13:47:08Z
    15295881   kalshi   227  13:33:17Z

Event 15293808 is the control the production data handed us: its Kalshi ticks
stopped at 12:21, the 30-minute window emptied, and the net closed it at 13:37
— while its six siblings, still being ticked, stayed live. Same code, same
sport, same morning; the only variable was whether a venue was still quoting.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    LAST_POST_COMMENCE_SNAPSHOT_SQL,
    STILL_ACTIVE_MINUTES,
    derive_completed_at,
    game_may_still_be_running,
)

# `VENUE_PRICE_SOURCES` and `venue_live_write_is_a_resurrection` are the symbols
# live/042 adds, and they are imported LAZILY inside each test on purpose. A
# module-level import of a symbol that does not exist yet collapses the whole
# red-first run into one collection error, which proves the file is new — not
# that any single assertion can see the defect it claims to catch.


def _venue_sources():
    from app.utils.event_completion import VENUE_PRICE_SOURCES

    return VENUE_PRICE_SOURCES


def _resurrection(status, completed_at):
    from app.utils.event_completion import venue_live_write_is_a_resurrection

    return venue_live_write_is_a_resurrection(status, completed_at)


def _dt(*args):
    return datetime(*args, tzinfo=timezone.utc)


# The measurement above, as data. Absolute datetimes, never offsets from the
# wall clock (gotcha #44): these are assertions about seven real rows on one
# real morning, and `now` does not get a vote.
MEASURED_AT = _dt(2026, 9, 2, 13, 51)

# (event_id, label, commence, [(source, last post-commence snapshot), ...])
US_OPEN_STUCK_LIVE = [
    (15293686, "Kasatkina v Badosa", _dt(2026, 9, 1, 21, 59), [("kalshi", _dt(2026, 9, 2, 13, 43))]),
    (15293702, "Jović v Frech", _dt(2026, 9, 2, 1, 7), [("kalshi", _dt(2026, 9, 2, 13, 43))]),
    (15293705, "Maria v Ostapenko", _dt(2026, 9, 1, 22, 5), [("kalshi", _dt(2026, 9, 2, 13, 47))]),
    (15293822, "Bergs v Taberner", _dt(2026, 9, 1, 21, 14), [("kalshi", _dt(2026, 9, 2, 13, 46))]),
    (15295047, "De Jong v Passaro", _dt(2026, 9, 1, 21, 2), [("kalshi", _dt(2026, 9, 2, 13, 47))]),
    (15295881, "Linette v Jones", _dt(2026, 9, 2, 1, 8), [("kalshi", _dt(2026, 9, 2, 13, 33))]),
]

# The row whose venue went quiet. It closed on its own at 13:37 with no code
# change at all — the natural control for the whole mechanism.
US_OPEN_VENUE_WENT_QUIET = (
    15293808, "Molcan v Bonzi", _dt(2026, 9, 1, 22, 29),
    [("kalshi", _dt(2026, 9, 2, 12, 21))],
)

# The venue names, written out so the CONTROL below can run on the pre-fix
# source too. Pinned against the shipped constant by
# `test_the_control_reads_the_shipped_denylist`.
_KNOWN_VENUES = {"betting", "kalshi", "polymarket"}

# A genuinely-running game, reported on by a source that watches the game. This
# is the must-not-regress direction (gotcha #43: assert BOTH arms): the fix must
# not turn the staleness net into a guillotine for long games, which is the
# CAL-P002 frozen-score defect the hold guard exists to prevent.
STILL_BEING_PLAYED = [
    ("extra-innings MLB, ESPN still posting", [("espn", _dt(2026, 9, 2, 13, 40))]),
    ("overtime NBA, our own model still ticking", [("stat_model", _dt(2026, 9, 2, 13, 35))]),
    ("MLB Stats API mid-game", [("mlb", _dt(2026, 9, 2, 13, 25))]),
    ("StatPal livescore, absent from WIN_PROB_SOURCES", [("statpal", _dt(2026, 9, 2, 13, 30))]),
    ("a book AND ESPN — the play source still counts", [
        ("betting", _dt(2026, 9, 2, 13, 50)), ("espn", _dt(2026, 9, 2, 13, 30)),
    ]),
]


def _last_snap(inventory, *, exclude_venues):
    """Replay of ``LAST_POST_COMMENCE_SNAPSHOT_SQL`` over a snapshot inventory.

    The SQL's whole content is "MAX(captured_at) over the post-commence rows
    this source filter admits". `exclude_venues=False` is the pre-fix rule.
    Bound to the real statement by ``TestTheQueryItselfExcludesVenues`` below,
    so this cannot drift into testing a private re-implementation.
    """
    admitted = [
        ts for src, ts in inventory
        if not (exclude_venues and src in _venue_sources())
    ]
    return max(admitted) if admitted else None


class TestThePriceTickNoLongerHoldsTheMatchLive:
    """The fails-first half: every one of these holds live on the old rule."""

    @pytest.mark.parametrize("eid,label,commence,inventory", US_OPEN_STUCK_LIVE)
    def test_the_old_rule_held_it_live(self, eid, label, commence, inventory):
        # Reproduce the defect before asserting it is gone — a regression arm
        # that never went red proves nothing about the detector.
        held = game_may_still_be_running(
            _last_snap(inventory, exclude_venues=False), MEASURED_AT
        )
        assert held is True, f"{eid} {label}: specimen does not reproduce the bug"

    @pytest.mark.parametrize("eid,label,commence,inventory", US_OPEN_STUCK_LIVE)
    def test_a_kalshi_tick_is_no_longer_evidence_of_play(self, eid, label, commence, inventory):
        held = game_may_still_be_running(
            _last_snap(inventory, exclude_venues=True), MEASURED_AT
        )
        assert held is False, f"{eid} {label}: a price tick is still holding it live"

    @pytest.mark.parametrize("eid,label,commence,inventory", US_OPEN_STUCK_LIVE)
    def test_no_end_time_is_derived_from_a_price_tick(self, eid, label, commence, inventory):
        """The other half of the fabrication: `completed_at` came off a tick.

        A NULL is the honest answer here and the module already prefers it — a
        visible gap a repair can fill beats a plausible wrong value nothing ever
        questions.
        """
        assert derive_completed_at(
            _last_snap(inventory, exclude_venues=True), commence
        ) is None

    def test_the_control_that_closed_itself_still_closes(self):
        eid, label, commence, inventory = US_OPEN_VENUE_WENT_QUIET
        # It was closeable under BOTH rules — its venue had already gone quiet.
        # If the fix changed this row's verdict, the fix is reading something
        # other than the source of the snapshot.
        for exclude in (False, True):
            assert game_may_still_be_running(
                _last_snap(inventory, exclude_venues=exclude), MEASURED_AT
            ) is False, f"{eid} {label}"


class TestAGameSomethingIsWatchingIsStillHeld:
    """gotcha #43 — the guard must still stop the frozen-score producer.

    THE CONTROL, and it is deliberately written to be green in BOTH arms. These
    read the play source's own timestamp rather than going through
    ``_last_snap``, so they touch nothing live/042 adds. A control that goes red
    on the pre-fix source proves nothing about whether the fix broke the healthy
    direction — it just re-reports that the fix is absent, which the treatment
    arm above already says.
    """

    @pytest.mark.parametrize("label,inventory", STILL_BEING_PLAYED)
    def test_a_play_source_still_holds_the_game(self, label, inventory):
        play_ts = max(ts for src, ts in inventory if src not in _KNOWN_VENUES)
        assert game_may_still_be_running(play_ts, MEASURED_AT) is True, label

    @pytest.mark.parametrize("label,inventory", STILL_BEING_PLAYED)
    def test_a_play_source_still_derives_the_end_time(self, label, inventory):
        commence = _dt(2026, 9, 2, 9, 0)
        play_ts = max(ts for src, ts in inventory if src not in _KNOWN_VENUES)
        assert derive_completed_at(play_ts, commence) is not None, label

    def test_the_control_reads_the_shipped_denylist(self):
        """...but the control's own literal must not drift from the real one.

        The price of writing the control without the new symbol is a second copy
        of the venue names. This is the one place that copy is checked, so the
        control can never quietly start testing a set the code does not use.
        """
        assert _KNOWN_VENUES == set(_venue_sources())

    def test_an_unknown_source_is_treated_as_a_witness(self):
        """A denylist, and this is why: StatPal is real and is not in the registry.

        An allowlist would have dropped it silently, which is the same class of
        error in the other direction — the net would start closing games a
        source is actively reporting on.
        """
        assert game_may_still_be_running(
            _last_snap([("some_new_scoreboard", _dt(2026, 9, 2, 13, 40))], exclude_venues=True),
            MEASURED_AT,
        ) is True

    def test_the_window_boundary_is_unchanged(self):
        base = _dt(2026, 9, 2, 12, 0)
        inside = base + timedelta(minutes=STILL_ACTIVE_MINUTES) - timedelta(seconds=1)
        assert game_may_still_be_running(base, inside) is True
        assert game_may_still_be_running(
            base, base + timedelta(minutes=STILL_ACTIVE_MINUTES)
        ) is False


class TestTheQueryItselfExcludesVenues:
    """Binds the replay above to the statement that actually runs."""

    def test_every_venue_source_is_named_in_the_sql(self):
        for src in _venue_sources():
            assert f"'{src}'" in LAST_POST_COMMENCE_SNAPSHOT_SQL, src

    def test_the_source_column_is_filtered_at_all(self):
        assert "w.source NOT IN (" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_a_null_source_still_counts(self):
        # Most of the table predates a disciplined source column; treating
        # unknown provenance as a venue would freeze the net for old rows.
        assert "w.source IS NULL" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_the_bookmaker_arm_is_gone(self):
        assert "odds_snapshots" not in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_it_is_still_one_batched_bind(self):
        from sqlalchemy import text

        assert sorted(text(LAST_POST_COMMENCE_SNAPSHOT_SQL)._bindparams) == ["event_ids"]

    def test_every_market_source_is_named_a_venue(self):
        """The completeness tripwire for the denylist.

        A new prediction market or book added to the registry as
        ``source_type: "market"`` and NOT added to ``VENUE_PRICE_SOURCES`` would
        quietly become evidence of play again — the exact defect, on a new
        source. The registry already makes every source declare which kind it
        is; this makes the two agree.
        """
        from app.config.win_prob_sources import WIN_PROB_SOURCES

        market_sources = {
            k for k, v in WIN_PROB_SOURCES.items() if v.get("source_type") == "market"
        }
        assert market_sources, "registry has no market sources — the check went vacuous"
        assert market_sources <= _venue_sources(), (
            f"unclassified venue price source(s): {sorted(market_sources - _venue_sources())}"
        )


class TestAVenueMayNotUnsettleARow:
    """The FLIP half: `completed: false` must not overrule a settlement."""

    @pytest.mark.parametrize("status", ["closed", "completed"])
    def test_a_settled_row_refuses_the_venue_promotion(self, status):
        assert _resurrection(status, None) is True

    def test_a_row_carrying_a_completion_refuses_it_whatever_the_status(self):
        # This is the production shape: status was already flipped back to
        # `live` on an earlier lap, and `completed_at` never got cleared. The
        # predicate has to catch the row on the SECOND lap too, or the loop
        # simply continues from where it is.
        assert _resurrection(
            "live", _dt(2026, 9, 2, 4, 1)
        ) is True

    @pytest.mark.parametrize("status", ["scheduled", "live", None])
    def test_an_unsettled_row_is_promoted_normally(self, status):
        # Both directions: the ordinary scheduled -> live promotion is the whole
        # point of this branch and must survive.
        assert _resurrection(status, None) is False

    def test_the_authority_unsettle_re_enables_the_venue(self):
        """#1201 clears `completed_at` in the same write, so the row reopens.

        The refusal is not a one-way latch: once ESPN has un-settled a replayed
        game, the venue may drive it live again like any other row.
        """
        assert _resurrection("live", None) is False


class TestTheScoresBlockCannotSilentlyLoseTheGuard:
    """Wiring. Asserted on executable tokens only — a getsource check that a
    docstring can satisfy is not a check (the warning text in that block quotes
    the defect, so nothing here may match prose)."""

    def test_the_scores_block_calls_the_predicate(self):
        import inspect

        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        assert "venue_live_write_is_a_resurrection(" in src

    def test_the_refusal_is_counted_not_swallowed(self):
        import inspect

        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        assert "scores_refused_resurrection += 1" in src, (
            "a silent guard cannot be told from no guard"
        )

    def test_the_counter_rides_out_with_the_run(self):
        import inspect

        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        assert '"scores_refused_resurrection": scores_refused_resurrection' in src

    def test_one_predicate_one_implementation(self):
        import inspect

        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling)
        assert 'event_status = None  # settled' not in src
        # The writer must not re-derive the settled test inline.
        assert 'in ("completed", "closed")' not in src

    def test_both_staleness_nets_read_the_same_evidence_rule(self):
        """espn_sync and odds_polling must not drift on what counts as play."""
        import inspect

        from app.tasks import espn_sync, odds_polling

        for mod in (espn_sync, odds_polling):
            assert "LAST_POST_COMMENCE_SNAPSHOT_SQL" in inspect.getsource(mod), mod.__name__
