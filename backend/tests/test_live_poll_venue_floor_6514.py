"""The venue floor is two-sided, so the minority venue is never zeroed (#6514).

## the ship

Two REFUSE-TO-WRITE gates live only inside the live poll's Kalshi loop, and
both of them are things a reader sees on the page when they fail:

- **#5896** — the pre-kickoff settled-book refusal, which stops a settled
  book's grade being written into the price column before kick-off.
- **#4356** — `_clear_withdrawn_outcome`, the twin clear for a leg the venue
  withdrew.

Measured on `bainluck` `worker-realtime`, four consecutive passes 08:14–08:20Z
2026-09-16, neither could fire:

    kalshi_fetched          0 / 0 / 0 / 0
    kalshi_outcomes_updated 0 / 0 / 0 / 0
    budget_stops            {"kalshi_fetch": 18} every pass

`budget_stops["kalshi_fetch"] == len(kalshi_ids)` means `_out_of_budget` was
already true at `_seen = 0` — the loop broke before its first request, not
part-way through. The Kalshi arm was admitted for **zero seconds**.

## the defect

`_LIVE_POLL_MIN_VENUE_FLOOR_SECONDS` is documented as "the smallest fetch
window a venue with ANY rows is allowed to be left with" and was applied to
`_polymarket_reserve` only. The other venue took the remainder, clamped at
zero:

    polymarket_reserve      = max(144 x 134/152, 20) = 126.9s
    kalshi_admission_window = 144 - 126.9 - 20       = -2.9s -> 0

So the guarantee held for whichever venue happened to be in the MAJORITY, and
the minority one could be starved to nothing. Kalshi's window was positive only
while `p < 6.2k`; with `k = 18` that is `p < 112`, and `p` was 134. #6179
measured this same arithmetic with the populations the other way round (107
Kalshi keys / 153 Polymarket keys, Kalshi got 39.3 s and fitted every call),
which is exactly why it read as correct.

## why the counters could not say so

Prices did NOT go stale — the `worker-ws` dyno batch-writes
`FuturesOutcome.current_probability` continuously, and 0 legs of the beat's own
population sat more than 30 min behind. Both starved gates are "refuse to
write" / "take the price off" branches, so a starved arm does not restore the
artifact either: `kalshi_pre_kickoff_settled_legs: 0` reads as "the refusal
held with nothing to take back" and means "the stage never started". That is
gotcha #53 — an empty result that is a response shape, not an absence — and it
is the reason this file asserts on FETCHES MADE rather than on any counter the
beat reports about its own success.

## what is held here, and what is held next door

This file holds the arm the fix exists for: the minority venue's floor. The
MAJORITY direction — that a venue whose proportional share exceeds the floor
keeps that share and is not cut down to it — is already held by
`test_live_poll_fetch_share_6179.py::...::test_the_per_item_wall_is_subtracted_from_the_first_venue`
(6 Kalshi keys at 30 s against 1 Polymarket key: it requires the full 103.4 s
ceiling and fails at a flat 20 s floor), and the single-venue case by
`...::test_rows_with_no_fetch_key_reserve_nothing`. Re-asserting either here
would be duplication, so the rig is imported from that file instead.
"""

from __future__ import annotations

from app.tasks.prediction_market_matching import (
    _LIVE_POLL_BUDGET_SECONDS,
    _LIVE_POLL_FETCH_BUDGET_SHARE,
    _LIVE_POLL_MIN_VENUE_FLOOR_SECONDS,
    _LIVE_POLL_VENUE_CALL_TIMEOUT_SECONDS,
)

# Aliased to a non-`Test*` name ON PURPOSE: `pytest.ini` collects
# `python_classes = Test*` by attribute name, so importing the rig under its
# own name would re-run all six of #6179's arms inside this module.
from tests.test_live_poll_fetch_share_6179 import (  # noqa: E402
    TestTheVenueReserveIsCountedInCallsAndNotInRows as _Rig,
)
from tests.test_live_poll_commit_boundary_5682 import _run, _Session  # noqa: E402

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


class TestTheMinorityVenueIsNotAdmittedForZeroSeconds:
    """Production's shape, scaled down by a factor of nine.

    `k = 2` Kalshi keys against `p = 15` Gamma event keys is a call ratio of
    0.882, against production's 134/152 = 0.882 — the same population, small
    enough to journal. The reserve is `max(144 x 15/17, 20) = 127.06 s` and the
    old remainder was `144 - 127.06 - 20 = -3.06 s`, which is production's
    -2.9 s to within a tenth.
    """

    POLY_EVENTS = 15

    async def test_the_kalshi_arm_makes_its_calls_instead_of_breaking_at_seen_zero(
        self, monkeypatch
    ):
        """THE DEFECT ARM.

        Revert the floor to one-sided and Kalshi's admission window is -3.06 s,
        clamped to 0. `_out_of_budget` is tested BEFORE the first fetch and
        `0 < 0` is false, so the loop breaks at `_seen = 0` and the venue makes
        no request at all — `budget_stops["kalshi_fetch"] == 2`, which is the
        whole plan, exactly as production reported 18 of 18.

        With the floor two-sided the window is one call's worth (20 s) and both
        2-second fetches are admitted. THE COST IS 2 s AND NOT 30 s ON PURPOSE:
        the claim being held is that the arm RUNS, not that a 20-second floor
        fits an unbounded number of calls, and a cost that overran the floor
        would make this arm pass or fail on the call cost rather than on the
        admission window.
        """
        clock = _Rig._clock(monkeypatch)
        journal = []
        beat = _Rig._beat(2, poly_rows_per_event=1, n_poly_events=self.POLY_EVENTS)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = _Rig._venues(
            journal,
            clock,
            n_kalshi=2,
            poly_event_ids=[f"poly-evt-{j}" for j in range(1, self.POLY_EVENTS + 1)],
            kalshi_cost=2,
            poly_cost=1,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        kalshi_fetches, _poly_fetches = _Rig._fetches(journal)
        assert kalshi_fetches, (
            "the Kalshi arm was admitted for ZERO seconds and broke at "
            "_seen = 0 — the minority venue has no floor. "
            f"budget_stops={stats.get('budget_stops')}"
        )
        assert len(kalshi_fetches) == 2, kalshi_fetches
        # The stage did not merely start, it FINISHED: nothing of its plan was
        # charged to the budget. A stage that ran one of two calls would still
        # satisfy the assertion above.
        assert "kalshi_fetch" not in (stats.get("budget_stops") or {}), (
            stats.get("budget_stops")
        )

    async def test_the_other_venue_is_not_paid_for_out_of_this(self, monkeypatch):
        """THE CONTROL: a floor for one venue is not a ceiling on the other.

        This is the failure mode the fix could plausibly introduce and the one
        #6179 was itself filed about — a reserve that protects one arm by
        starving the other. Kalshi's floor takes 20 s of admission plus its
        20 s wall from a 144 s window, so Polymarket runs from t=4 (both Kalshi
        calls having actually cost 2 s each) against the full window and every
        one of its 15 events is still fetched.

        Asserted on the SAME POPULATION as the arm above deliberately, and it
        re-asserts that arm's Kalshi count before its own: a control drawn from
        a population where Kalshi's floor does NOT bind would be measuring the
        unchanged path and could not say these two facts hold at once.
        """
        clock = _Rig._clock(monkeypatch)
        journal = []
        beat = _Rig._beat(2, poly_rows_per_event=1, n_poly_events=self.POLY_EVENTS)
        session = _Session([beat, beat], journal=journal)
        kalshi, poly = _Rig._venues(
            journal,
            clock,
            n_kalshi=2,
            poly_event_ids=[f"poly-evt-{j}" for j in range(1, self.POLY_EVENTS + 1)],
            kalshi_cost=2,
            poly_cost=1,
        )

        stats = await _run(monkeypatch, session, kalshi=kalshi, poly=poly)

        kalshi_fetches, poly_fetches = _Rig._fetches(journal)
        assert len(kalshi_fetches) == 2, kalshi_fetches
        assert len(poly_fetches) == self.POLY_EVENTS, (
            "the new Kalshi floor was taken out of Polymarket's own window: "
            f"{len(poly_fetches)} of {self.POLY_EVENTS} fetched, "
            f"budget_stops={stats.get('budget_stops')}"
        )
        assert stats["terminal"] == "complete", stats


class TestTheConstantsCanAffordTheFloorTheyPromise:
    """The four constants that decide whether the floor is a floor or a clip.

    Kalshi's floor is capped at `window - polymarket_floor - wall`, because a
    claim on a window cannot exceed the window. The cap is what keeps the
    second venue whole, and it is load-bearing in a way this file does not have
    to prove: #5767's zero-budget arms go red against an uncapped floor.

    What the cap CANNOT do is tell anyone it fired. Below
    `window >= 2 x floor + wall` it silently clips Kalshi's floor to less than
    one call, and #6514 returns in a quieter form — the minority venue gets a
    window too short to buy a fetch, with no arithmetic anywhere admitting it.
    Today that threshold is 60 s against a 144 s window, 84 s of headroom, and
    it is a relationship between four constants declared hundreds of lines
    apart that nothing else reads together. Lowering
    `_LIVE_POLL_FETCH_BUDGET_SHARE` or `_LIVE_POLL_BUDGET_SECONDS`, or raising
    either of the two 20-second constants, breaks it. These arms are the alarm.
    """

    WINDOW = _LIVE_POLL_BUDGET_SECONDS * _LIVE_POLL_FETCH_BUDGET_SHARE

    def test_the_fetch_window_can_seat_both_floors_and_the_wall(self):
        assert self.WINDOW >= (
            2 * _LIVE_POLL_MIN_VENUE_FLOOR_SECONDS
            + _LIVE_POLL_VENUE_CALL_TIMEOUT_SECONDS
        ), (
            "the fetch window can no longer seat both venues' floors plus the "
            "per-item wall, so the cap clips the first venue's floor below one "
            f"call and #6514 is back: window={self.WINDOW}, "
            f"floor={_LIVE_POLL_MIN_VENUE_FLOOR_SECONDS}, "
            f"wall={_LIVE_POLL_VENUE_CALL_TIMEOUT_SECONDS}"
        )

    def test_the_cap_does_not_currently_clip_the_floor_it_caps(self):
        """The same threshold said as the quantity the code computes.

        Stated separately because the sum above is the relationship and this is
        the consequence: a reader who changes a constant should be able to see
        from the failure which of the two they broke, and by how much.
        """
        cap = (
            self.WINDOW
            - _LIVE_POLL_MIN_VENUE_FLOOR_SECONDS
            - _LIVE_POLL_VENUE_CALL_TIMEOUT_SECONDS
        )
        assert cap >= _LIVE_POLL_MIN_VENUE_FLOOR_SECONDS, (
            "the first venue's floor is being clipped by the cap: it may hold "
            f"{cap}s of a {self.WINDOW}s window, and one call is "
            f"{_LIVE_POLL_MIN_VENUE_FLOOR_SECONDS}s"
        )
