"""An absent volume figure is a MEASURED zero — the second grade, on real data.

UX-P158, following UX-P157 (#2256, #2257, Alex's 2026-08-28 ruling).

═══ WHAT WENT WRONG, AND WHY IT IS WORTH A SUITE OF ITS OWN ═══

UX-P157 shipped Alex's graded symbol with two levels, 27 tests holding them
there, and a legend on the page saying what each one means.  On the live page
only ONE of them could ever appear.  Gamma serves ``volume24hr`` on 64 of 336
US Open ladder markets and omits it on the rest, so the fact that produces the
second level was uncheckable everywhere it mattered, and every real mark was a
``thin``.  The artifact showed two levels because its legend is hand-specified.
**Alex would have looked at the artifact and seen a graded signal, and looked
at the page and seen an ungraded one.**

That is the failure this file exists to prevent recurring, and it is not a
coding failure — every test was green.  It is the failure of guarding a rule
only against invented specimens.  So the specimens here are the REAL 336
markets, banked with an independent measurement beside them, and the load-
bearing test is the one that re-derives the claim in the module's own comment
from the fixture rather than restating it.

═══ WHAT THESE GUARD ═══

  1. **The second grade fires on the real corpus.**  Not "can fire" — fires, on
     the banked books, in a count this file asserts.  A change that quietly
     returns the rule to one reachable level fails here.
  2. **The absence is only read when it was actually observed.**  A NULL with no
     stamp behind it is silence, not a zero.  115 of the 336 ladder rows are in
     exactly that state today (not pinned in the refresh register), and marking
     them would be the invention the whole module is written to refuse.
  3. **An observation is not evidence past the window it describes.**  In BOTH
     directions — a positive figure read four days ago no more says "traded
     today" than an absent one says "did not".
  4. **The window carries no tolerance.**  Parametrised across the boundary, so
     an epsilon added to "tidy up" a straddling row fails here.
  5. **The claim in the module comment is true of the banked evidence.**  The
     three-cohort separation is re-counted from the fixture, so re-banking a
     fixture that no longer supports the rule turns the rule red instead of
     leaving a comment that used to be right.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.market_liquidity import (
    LIQUIDITY_BARELY,
    LIQUIDITY_THIN,
    LIQUIDITY_TRADED,
    LIQUIDITY_UNKNOWN,
    REASON_NO_TRADES_24H,
    REASON_SPREAD_EXCEEDS_PRICE,
    VOLUME_OBSERVATION_MAX_AGE_HOURS,
    grade_liquidity,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "mocks"
    / "us-open"
    / "ladder-books-2026-08-29.json"
)


def _books() -> dict[str, dict]:
    """The 336 real ladder markets, minus the pull's own metadata block."""
    raw = json.loads(FIXTURE.read_text())
    raw.pop("_meta", None)
    return raw


# ═══════════════════════════════════════════════════════════════════════
# THE RULE — what an absence now means, and what it still does not
# ═══════════════════════════════════════════════════════════════════════


class TestAnObservedAbsenceIsAZero:
    def test_the_second_grade_fires_from_an_absent_figure(self):
        """THE SHIP, at unit scale.

        Venus Williams' quarter-final cell: a 0.00/0.08 book, and a venue we
        asked half an hour ago that reported no 24h volume at all — by omitting
        the field, which is the only way Gamma reports a zero. Before UX-P158
        this graded `thin`, because the absence was unreadable.
        """
        graded = grade_liquidity(
            bid=0.0, ask=0.08, volume_24h=None, volume_observed_age_hours=0.5
        )
        assert graded["level"] == LIQUIDITY_BARELY
        assert set(graded["reasons"]) == {
            REASON_NO_TRADES_24H,
            REASON_SPREAD_EXCEEDS_PRICE,
        }

    def test_an_absent_figure_alone_is_the_first_grade(self):
        """A tight book we asked about and nobody traded. One fact failed."""
        assert grade_liquidity(
            bid=0.69, ask=0.71, volume_24h=None, volume_observed_age_hours=0.5
        ) == {"level": LIQUIDITY_THIN, "reasons": [REASON_NO_TRADES_24H]}

    def test_an_explicit_zero_and_an_absence_grade_identically(self):
        """Kalshi serves the zero, Gamma omits it, and they are the same fact.

        A rule that treated one venue's serialisation choice as a different
        state would make the mark mean something different per source, which is
        precisely what "universal" in Alex's ruling forbids.
        """
        served = grade_liquidity(
            bid=0.0, ask=0.08, volume_24h=0, volume_observed_age_hours=0.5
        )
        omitted = grade_liquidity(
            bid=0.0, ask=0.08, volume_24h=None, volume_observed_age_hours=0.5
        )
        assert served == omitted


class TestAnAbsenceWeNeverObservedIsSilence:
    def test_no_stamp_means_the_fact_is_not_checked(self):
        """GOTCHA #53, the half that did NOT go away.

        This is the difference between "we asked and nothing came back" and "we
        never asked", and it is a live distinction: on 2026-08-29 every one of
        the 336 US Open ladder rows carried a NULL volume column with NO stamp
        behind it, because no writer that touches them had ever recorded one.
        Marking those would be inventing the measurement the rest of this
        module refuses to invent.
        """
        assert grade_liquidity(bid=0.69, ask=0.71, volume_24h=None) == {
            "level": LIQUIDITY_TRADED,
            "reasons": [],
        }
        assert grade_liquidity(volume_24h=None)["level"] == LIQUIDITY_UNKNOWN

    def test_a_poison_age_does_not_check_the_fact(self):
        """A parse failure in the timestamp must not become a mark."""
        for bad in ("recently", {}, [], float("nan")):
            assert (
                grade_liquidity(volume_24h=None, volume_observed_age_hours=bad)["level"]
                == LIQUIDITY_UNKNOWN
            )

    def test_a_stamp_in_the_future_is_refused_not_clamped(self):
        """Two clocks disagreeing is not an observation.

        Refused rather than read as "just now": a clock hours out is an
        infrastructure fault, and the honest response to "we cannot tell when
        this was measured" is the same as to "we never measured it".
        """
        assert (
            grade_liquidity(volume_24h=None, volume_observed_age_hours=-3.0)["level"]
            == LIQUIDITY_UNKNOWN
        )


class TestTheWindowIsTheFieldsOwn:
    @pytest.mark.parametrize(
        "age_hours,checked",
        [
            (0.0, True),
            (12.0, True),
            # Exactly the window: `<=`, so still evidence about today.
            (VOLUME_OBSERVATION_MAX_AGE_HOURS, True),
            # One second past it and the observed window no longer overlaps
            # today at all. No tolerance, deliberately: a straddling row is the
            # obvious place to add an epsilon and this is where that fails.
            (VOLUME_OBSERVATION_MAX_AGE_HOURS + 1 / 3600, False),
            (83.0, False),  # the real staleness on the unregistered ladder rows
        ],
    )
    def test_the_absence_is_read_only_inside_the_window(self, age_hours, checked):
        graded = grade_liquidity(
            bid=0.69, ask=0.71, volume_24h=None, volume_observed_age_hours=age_hours
        )
        assert (REASON_NO_TRADES_24H in graded["reasons"]) is checked

    def test_the_window_gates_a_positive_figure_the_same_way(self):
        """SYMMETRY, and it is the reason this is defensible as a rule rather
        than as a convenient reading of a NULL.

        $195 of volume seen four days ago is not a statement about today. It
        does not become one because it is a number rather than an absence.

        Asserted with NO book, so the volume fact is the only one in play and
        the result is a statement about it alone: both stale readings leave
        nothing checked at all.
        """
        assert (
            grade_liquidity(volume_24h=195, volume_observed_age_hours=96.0)["level"]
            == LIQUIDITY_UNKNOWN
        )
        assert (
            grade_liquidity(volume_24h=None, volume_observed_age_hours=96.0)["level"]
            == LIQUIDITY_UNKNOWN
        )
        # And with a book beside it, a stale volume reading leaves the cell
        # graded on the book alone — never marked, never cleared, by a figure
        # that is four days old.
        assert (
            grade_liquidity(
                bid=0.69, ask=0.71, volume_24h=195, volume_observed_age_hours=96.0
            )["reasons"]
            == []
        )

    def test_the_window_is_the_fields_own_twenty_four_hours(self):
        """Named so a later queue cannot move it as a tuning knob without
        arguing with the sentence that justifies it."""
        assert VOLUME_OBSERVATION_MAX_AGE_HOURS == 24.0


# ═══════════════════════════════════════════════════════════════════════
# THE EVIDENCE — the claim in the module comment, re-counted from the bank
# ═══════════════════════════════════════════════════════════════════════


class TestTheBankedEvidenceStillSupportsTheRule:
    """Read the fixture, not the comment.

    Every one of these re-derives a number the module states as measured. If a
    later queue re-banks the fixture and the separation no longer holds, the
    rule goes red here rather than keeping a comment that used to be true.
    """

    def test_gamma_never_serves_an_explicit_zero_volume(self):
        """The premise. If it ever served a 0, an absence would mean something
        else and the whole inference would need re-deriving."""
        books = _books()
        served = [b for b in books.values() if b.get("live_present")]
        assert served, "fixture has no live half"
        assert not [
            b
            for b in served
            if b.get("live_volume_24h_present") and not b["live_volume_24h"]
        ]

    def test_the_trade_tape_separates_the_three_cohorts_without_exception(self):
        """THE LOAD-BEARING MEASUREMENT.

        Gamma's volume is a computed aggregate; the trade tape is the list of
        trades that happened. Two instruments, and they agree perfectly:

            volume24hr present  → traded in the last 24h, every time
            absent + lifetime   → traded at some point, never in the last 24h
            absent + no lifetime→ never traded at all, not once
        """
        books = _books()
        served = {k: b for k, b in books.items() if b.get("live_present")}
        with_tape = {k: b for k, b in served.items() if "trades_in_24h" in b}
        assert len(with_tape) == len(served), "tape half is incomplete"

        cohort_a = [b for b in with_tape.values() if b["live_volume_24h_present"]]
        rest = [b for b in with_tape.values() if not b["live_volume_24h_present"]]
        cohort_b = [b for b in rest if (b["live_volume_lifetime"] or 0) > 0]
        cohort_c = [b for b in rest if not (b["live_volume_lifetime"] or 0) > 0]

        assert cohort_a and cohort_b and cohort_c, "a cohort emptied — re-measure"
        # No sample hit the trades cap, so "0 sampled" really is "0 ever".
        assert not [b for b in with_tape.values() if b["trades_sample_hit_cap"]]

        assert all(b["trades_in_24h"] > 0 for b in cohort_a)
        assert all(b["trades_in_24h"] == 0 for b in cohort_b)
        assert all(b["trades_sampled"] > 0 for b in cohort_b)
        assert all(b["trades_sampled"] == 0 for b in cohort_c)

    def test_the_second_grade_reaches_the_real_grid_not_just_a_specimen(self):
        """UX-P157's actual defect, asserted as a count on the real corpus.

        Under the old reading every one of these markets could only be `thin`.
        Under the measured one a substantial minority are `barely` — and the
        assertion is a floor rather than an exact number so that books moving
        overnight do not turn this red for the wrong reason, while a rule that
        went back to one reachable level does.
        """
        books = _books()
        served = [b for b in books.values() if b.get("live_present")]
        graded = [
            grade_liquidity(
                bid=b["live_bid"],
                ask=b["live_ask"],
                volume_24h=b["live_volume_24h"],
                # The live half IS the observation: these were read from Gamma
                # seconds before they were written down.
                volume_observed_age_hours=0.0,
            )["level"]
            for b in served
        ]
        assert graded.count(LIQUIDITY_BARELY) >= 100
        assert graded.count(LIQUIDITY_THIN) >= 50
        # And the mark still has to be able to say nothing: a rule that marked
        # everything would be wallpaper, not a signal.
        assert graded.count(LIQUIDITY_TRADED) >= 20

    def test_the_old_reading_could_not_reach_the_second_grade_here(self):
        """The counterfactual, so the fix is demonstrated and not just claimed.

        Grading the same corpus the way UX-P157 did — an absence unreadable —
        yields ZERO `barely` cells. This is the artifact-versus-page gap, in a
        test.
        """
        books = _books()
        served = [b for b in books.values() if b.get("live_present")]
        old = [
            grade_liquidity(
                bid=b["live_bid"],
                ask=b["live_ask"],
                volume_24h=b["live_volume_24h"],
                # No age passed = the fact is unchecked, which is exactly what
                # an unreadable absence did.
            )["level"]
            for b in served
        ]
        assert old.count(LIQUIDITY_BARELY) == 0

    def test_the_stalest_rows_carry_no_observation_and_so_stay_unmarked(self):
        """The 115 — and they are the ones this mark most wants to describe.

        Measured 2026-08-29: 115 of the 336 ladder rows had a stored price last
        written on 2026-08-25, 83 hours earlier. Not a register gap (all 336 are
        pinned); the refresh rail's own summary accounts for them exactly — 8
        Gamma no longer serves, and 107 are Q428's DECLINE, a book it will not
        publish a price from. So the rows with the deadest books were the rows
        with the oldest data about them, which is the worst possible pairing for
        a signal about deadness, and it is why the rail now records the volume
        observation for every market Gamma RETURNS rather than every market it
        can price.

        Until that runs, none of them carries a volume observation at all, so
        the rule cannot be tempted by them in either direction.
        """
        books = _books()
        pulled_at = json.loads(FIXTURE.read_text())["_meta"]["pulled_at_utc"]
        now = datetime.strptime(pulled_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        stale = []
        for book in books.values():
            stamp = book.get("stored_price_updated_at")
            if not stamp:
                continue
            when = datetime.fromisoformat(stamp.replace("+00", "+00:00"))
            if now - when > timedelta(hours=VOLUME_OBSERVATION_MAX_AGE_HOURS):
                stale.append(book)
        assert len(stale) >= 50, "the stale cohort has drained — re-read the route note"
        assert all(b.get("stored_volume_updated_at") is None for b in stale)


# ═══════════════════════════════════════════════════════════════════════
# THE WIRING — the seams that carry the observation to the page
# ═══════════════════════════════════════════════════════════════════════


class TestTheRouteReadsTheStampBesideTheFigure:
    def _load_prices_source(self) -> str:
        import inspect

        from app.routes import tournaments

        source = inspect.getsource(tournaments)
        start = source.index("async def _load_prices")
        return source[start : source.index("async def _load_series", start)]

    def test_the_loader_selects_the_stamp(self):
        """A figure without its timestamp is not a measurement, and this is the
        one query that feeds all five surfaces."""
        assert "FuturesMarket.volume_updated_at" in self._load_prices_source()

    def test_the_loader_passes_an_age_to_the_grade(self):
        assert (
            "volume_observed_age_hours=_hours_since(row.volume_updated_at, at)"
            in self._load_prices_source()
        )

    def test_hours_since_reads_a_naive_stamp_as_utc(self):
        """The driver can hand back a naive datetime. Reading it as local time
        would shift every age by the server's offset and either invent marks or
        suppress them, silently, in only some deployments."""
        from app.routes.tournaments import _hours_since

        at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
        assert _hours_since(datetime(2026, 8, 29, 9, 0), at) == pytest.approx(3.0)
        assert _hours_since(
            datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc), at
        ) == pytest.approx(3.0)
        assert _hours_since(None, at) is None

    def test_hours_since_does_not_hide_a_future_stamp(self):
        from app.routes.tournaments import _hours_since

        at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
        assert _hours_since(datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc), at) < 0


class TestTheRefreshRailWritesTheObservation:
    """The rail is the only thing that touches these markets more than once a
    week, so it is the only place a CURRENT volume observation can come from.

    Source-level, deliberately: the write is three lines inside a task whose
    session is a real database, and what can go wrong with it is somebody
    deleting it or making it conditional — both visible here, neither visible
    in a mocked call count.
    """

    def _write_source(self) -> str:
        import inspect

        from app.tasks import tournament_price_refresh

        source = inspect.getsource(tournament_price_refresh)
        start = source.index("async def _write_refreshed_prices")
        return source[start:]

    def test_the_rail_writes_the_figure_and_the_stamp_together(self):
        block = self._write_source()
        assert "volume_updated_at=now," in block
        assert "volume_24h=(" in block

    def test_the_figure_is_null_preserving(self):
        """A market Gamma serves without the field must land as NULL. An
        `or 0` here would manufacture the very "measured zero" the stamp is
        supposed to certify, and nothing downstream could tell the difference.
        """
        block = self._write_source()
        assert "if market.volume_24h is not None" in block
        assert "int(market.volume_24h or 0)" not in block

    def test_the_observation_is_written_before_the_unpriced_skip(self):
        """An unpriced market is still a market we asked about. If the write
        sat after the `continue`, the stalest rows on the surface — the ones
        this signal is most for — would be the ones it never observed."""
        block = self._write_source()
        assert block.index("volume_updated_at=now,") < block.index(
            'stats["unpriced"] += 1'
        )

    def test_the_rail_counts_what_it_observed(self):
        """`app/utils/task_verdict.py`'s rule: "it returned" is not "it worked".
        A volume write that silently stopped must not look like a healthy run.
        """
        import inspect

        from app.tasks import tournament_price_refresh

        source = inspect.getsource(tournament_price_refresh)
        assert '"volume_observed": 0,' in source
        assert 'stats["volume_observed"] += 1' in source
