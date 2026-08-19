"""#1981 — the FOURTH team-pair/stale-id ingest site: the Odds API scores block.

PR #1971 gave the pairing guard to three writers (`espn_helpers.sync_scheduled_events`,
`statpal_sync._sync_statpal_schedules`, `statpal_sync._sync_statpal_livescores`). It did
not touch the fourth, because that one does not pair on a team name at all — it pairs on
an **id**, and an id looks like identity right up until it goes stale.

The mechanism, verified row by row against the live Odds API payload (queue 370):

    Each contaminated row's `external_id` is the PREVIOUS night's Odds API event id. The
    scores endpoint answers for that id with `completed=true` and the previous night's
    final. `_poll_all_odds` compared *the score record's* commence to `now` — never to
    the ROW'S OWN commence — and then wrote `status='completed'`, a batch `completed_at`,
    and the wrong game's final, `WHERE external_id = :external_id`. Every 300 seconds
    (`SCORE_FETCH_INTERVAL`), for as long as the row exists.

Every specimen below is a PRODUCTION row, measured 2026-08-18T23:24Z from
`/v4/sports/baseball_mlb/scores/?daysFrom=3` joined to `events` by `external_id`. Anchors
are absolute datetimes, not offsets from `now` (gotcha #44): these are assertions about a
fixed pair of real games, and the wall clock does not get a vote.

Shadow read on that data — the same replay this suite encodes:

    replay A (as deployed)   15 writes, 9 of them onto the known population
    replay B (with the guard) 3 writes, all within 12h of the row's own commence

Ruling (b)(2), queue 371: stale-`external_id` ownership goes WITH THE WRITER. The writer
re-verifies, re-binds, or nulls a stale id; it never compares against one. This site takes
the re-verify arm — see the docstring on `external_id_currency`.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.game_pairing import (
    SAME_GAME_MAX_SEPARATION,
    IdCurrency,
    external_id_currency,
)


def _dt(*args):
    return datetime(*args, tzinfo=timezone.utc)


# (row id, label, the row's OWN commence, the provider record's start)
#
# The eight flappers established from `score_snapshots` (one transaction = one identical
# microsecond stamp), plus the five further victims replay A also reached. Separations run
# 18h to 66h — a team pair could never tell these apart, and neither can an id.
CONTAMINATING = [
    (15194472, "Braves @ Twins", _dt(2026, 8, 18, 23, 40), _dt(2026, 8, 18, 0, 30)),
    (15198638, "Rangers @ Athletics", _dt(2026, 8, 16, 20, 5), _dt(2026, 8, 16, 1, 41, 43)),
    (15199882, "Padres @ Mets", _dt(2026, 8, 18, 23, 10), _dt(2026, 8, 17, 23, 11)),
    (15199884, "White Sox @ Cubs", _dt(2026, 8, 19, 0, 5), _dt(2026, 8, 18, 0, 6)),
    (15199886, "Marlins @ Phillies", _dt(2026, 8, 18, 22, 40), _dt(2026, 8, 17, 22, 42, 56)),
    (15199901, "Tigers @ Pirates", _dt(2026, 8, 18, 22, 40), _dt(2026, 8, 17, 23, 6)),
    (15199902, "Dodgers @ Rockies", _dt(2026, 8, 19, 0, 40), _dt(2026, 8, 18, 0, 41)),
    (15200216, "Athletics @ Royals", _dt(2026, 8, 20, 18, 10), _dt(2026, 8, 17, 23, 41)),
    (15200229, "D-backs @ Red Sox", _dt(2026, 8, 18, 23, 10), _dt(2026, 8, 17, 23, 11)),
    # Three victims that appeared in the 2026-08-18 replay and NOT in queue 370's —
    # Aug-20 rows being stamped `live` 42-48h before first pitch. The blast radius was
    # still growing while the ticket sat open, which is why this was the p0.
    (15200806, "Giants (Aug-20 row)", _dt(2026, 8, 20, 17, 10), _dt(2026, 8, 18, 22, 41)),
    (15200817, "Yankees (Aug-20 row)", _dt(2026, 8, 20, 22, 35), _dt(2026, 8, 18, 22, 36)),
    (15200818, "Blue Jays (Aug-20 row)", _dt(2026, 8, 20, 17, 10), _dt(2026, 8, 18, 22, 41)),
]

# The three writes replay B kept: the id on the row still names the row's own game.
LEGITIMATE = [
    (15194464, "Orioles", _dt(2026, 8, 17, 22, 5), _dt(2026, 8, 17, 22, 5, 2)),
    (15200380, "Cardinals", _dt(2026, 8, 17, 17, 40), _dt(2026, 8, 17, 17, 42)),
    (15201156, "Cardinals @ Reds", _dt(2026, 8, 18, 22, 40), _dt(2026, 8, 18, 22, 41)),
]


class TestTheStaleIdIsRefused:
    """Every contaminating write in the shadow read must come back STALE."""

    @pytest.mark.parametrize("row_id,label,ours,theirs", CONTAMINATING)
    def test_specimen_id_reads_stale(self, row_id, label, ours, theirs):
        assert external_id_currency(ours, theirs) is IdCurrency.STALE, f"{row_id} {label}"

    @pytest.mark.parametrize("row_id,label,ours,theirs", CONTAMINATING)
    def test_specimen_is_refused_by_the_caller_gate(self, row_id, label, ours, theirs):
        # The caller's gate is literally `is not IdCurrency.CURRENT` — pin the shape the
        # writer depends on, not just the enum value.
        assert external_id_currency(ours, theirs) is not IdCurrency.CURRENT


class TestTheLegitimateWritesSurvive:
    """A guard that also stops the real work is not a fix (gotcha #43: both directions)."""

    @pytest.mark.parametrize("row_id,label,ours,theirs", LEGITIMATE)
    def test_current_id_still_writes(self, row_id, label, ours, theirs):
        assert external_id_currency(ours, theirs) is IdCurrency.CURRENT, f"{row_id} {label}"

    def test_the_replay_counts_hold(self):
        """The shadow read as an assertion: 15 as deployed, 3 with the guard.

        Replay A writes wherever a row holds the id; replay B writes only where the id is
        still current. The numbers are what queue 370 pre-certified and what queue 371
        re-measured against live data.
        """
        deployed = CONTAMINATING + LEGITIMATE
        guarded = [
            s for s in deployed
            if external_id_currency(s[2], s[3]) is IdCurrency.CURRENT
        ]
        assert len(deployed) == 15
        assert len(guarded) == 3
        assert {s[0] for s in guarded} == {s[0] for s in LEGITIMATE}


class TestCouldNotCheckIsNotCurrent:
    """Doctrine: a check that could not run must never read as a check that passed."""

    def test_missing_provider_start_is_unverifiable(self):
        assert external_id_currency(_dt(2026, 8, 18, 22, 40), None) is IdCurrency.UNVERIFIABLE

    def test_missing_row_commence_is_unverifiable(self):
        assert external_id_currency(None, _dt(2026, 8, 17, 23, 6)) is IdCurrency.UNVERIFIABLE

    def test_no_row_holds_the_id_is_unbound_not_current(self):
        assert external_id_currency(None, _dt(2026, 8, 17, 23, 6), row_found=False) is (
            IdCurrency.UNBOUND
        )

    def test_only_current_passes(self):
        for verdict in IdCurrency:
            if verdict is not IdCurrency.CURRENT:
                assert verdict is not IdCurrency.CURRENT

    def test_doubleheader_still_reads_current(self):
        """The constant must not be so tight it splits a real doubleheader."""
        game1 = _dt(2026, 8, 18, 17, 5)
        assert external_id_currency(game1, game1 + timedelta(hours=6)) is IdCurrency.CURRENT

    def test_boundary_is_the_shared_constant(self):
        base = _dt(2026, 8, 18, 12, 0)
        assert external_id_currency(base, base + SAME_GAME_MAX_SEPARATION) is IdCurrency.CURRENT
        assert external_id_currency(
            base, base + SAME_GAME_MAX_SEPARATION + timedelta(seconds=1)
        ) is IdCurrency.STALE


class TestTheFourthSiteCannotSilentlyLoseItsGuard:
    """Source-shape assertions on `_poll_all_odds` — this is the fails-first half.

    On the pre-fix source every assertion here fails: the scores block imported nothing
    from `game_pairing`, and its UPDATE was addressed by the id under suspicion.
    """

    def test_the_scores_block_gates_on_id_currency(self):
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        assert "external_id_currency(" in src, (
            "the scores block found the row BY external_id, so external_id cannot also be "
            "the evidence that the row is the right one"
        )
        assert "IdCurrency.CURRENT" in src

    def test_the_score_update_is_addressed_by_primary_key(self):
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        assert "Event.id == event_obj.id" in src, (
            "verifying one row and then writing WHERE external_id = ... joins the check "
            "and the write by nothing but the id under suspicion"
        )
        assert ".where(Event.external_id == external_id)" not in src

    def test_refusals_are_counted_not_swallowed(self):
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        for counter in (
            "scores_refused_stale_id",
            "scores_refused_unverifiable",
            "scores_unbound_id",
        ):
            assert counter in src, f"{counter} — a silent guard cannot be told from no guard"

    def test_one_predicate_one_implementation(self):
        """No second copy of the separation constant in the writer."""
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling)
        assert "timedelta(hours=12)" not in src, (
            "the writer re-declared the separation constant — ruling 082 says every "
            "pairing site reads it from game_pairing"
        )
