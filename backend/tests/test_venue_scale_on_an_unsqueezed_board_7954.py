"""#7954 — a chart that has already refused the squeeze may print its venue points.

WHAT A READER SAW. `/futures/61308736` (*2027 US Open Men's Singles Winner*,
Kalshi, tier 1, open) drew its Probability Trend across Sep 17 → Sep 21 with a
wide dashed stretch through the middle and the caption **"No numbers for 12
hours in this stretch"**, then a hard vertical step where the line resumed — a
reader reads that as "nothing happened, then everything happened at once".

The venue bank for that exact market was present, durable, dated and healthy the
whole time. Read off production 2026-09-22:

    /history              "state":"refused", "points_served":0,
                          "refusals":[{"reason":
                          "exclusive_field_incomplete_at_venue_instant"}]
    /probability-timeline "state":"warm", "points_served":45,
                          "outcomes_served":6, "fill_status":"ok",
                          observed 2026-09-17T18:34Z → 2026-09-21T13:59Z

**The hole and the fill existed at the same time, on one screen.**

🔴 THE REFUSAL WAS STRUCTURAL, NOT A PROPERTY OF THE DATA, and that is the whole
finding. `_venue_scale_refusal` requires every CHARTED outcome to appear at a
venue instant — a field with a hole has no denominator, which is right when the
squeeze is running. But this board charts 10 legs and its venue bank can only
ever carry 6, because the other 4 are price-withheld: `_drop_unsupported_
snapshot_points` removes their points on the way in (39 of the bank's 84 here,
reported as `unsupported_points_withheld`). One rule withholds the legs; the
other demands them. No amount of venue data could satisfy both, so the refusal
was permanent and no reader would ever see a point.

AND THE DENOMINATOR IT WAS PROTECTING WAS NOT BEING USED. Those same withheld
legs make `field_complete` False, and #7103/#7747 read that as REFUSE THE
SQUEEZE: the chart prints the raw column. A raw venue point is already on that
scale. The completeness test was guarding an arithmetic the page had stopped
doing — which is why #7747's own ledger row predicted this file's existence
("may now admit venue points it refuses today").

WHY THIS IS NOT THE INFERENCE #7351 REMOVED. That one went from one INSTANT to
another ("the captures came through unchanged, so the unclaimed instants will
too"). `field_complete` is a property of the BOARD — #7747 says so in capitals,
"PER BOARD, NOT PER INSTANT", because squeezing some instants of a line and not
others draws a scale change as a price MOVE. "This chart does not squeeze" is
therefore true at the unclaimed instants as well, and nothing is carried across.

THE FIELD BELOW IS PRODUCTION ROWS, the same 24-row `futures_odds_snapshots`
column as the #7747 sibling (one book, kalshi, sum 1.555), kept WHOLE for the
reason that file gives: both display steps are functions of the entire field, so
a trimmed fixture measures a different computation.
"""

from datetime import datetime, timedelta, timezone
from statistics import mean
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route


T0 = datetime(2026, 9, 22, 3, 50, 54, 864277, tzinfo=timezone.utc)

#: 230781795 Mensik is the withheld leg (`yes_bid 0.0400` under `yes_ask
#: 0.7400`, no 24-hour volume) and 0.740 of the 1.555 divisor.
MENSIK, SINNER, ALCARAZ, RUUD = 230781795, 230781778, 230781780, 230781797

_FIELD = {
    MENSIK: 0.740, SINNER: 0.315, ALCARAZ: 0.270, RUUD: 0.030,
    230781779: 0.010, 230781785: 0.010, 230781796: 0.010, 230781798: 0.010,
    230781802: 0.010, 230781782: 0.010, 230781783: 0.010, 230781784: 0.010,
    230781786: 0.010, 230781787: 0.010, 230781788: 0.010, 230781789: 0.010,
    230781790: 0.010, 230781791: 0.010, 230781792: 0.010, 230781793: 0.010,
    230781799: 0.010, 230781801: 0.010, 230781781: 0.010, 230781794: 0.010,
}

#: The six legs the production bank actually holds points for — the priced ones.
#: Every venue instant is therefore missing 18 of the 24 charted legs, which is
#: the shape `exclusive_field_incomplete_at_venue_instant` fires on.
_BANKED = [SINNER, ALCARAZ, RUUD, 230781779, 230781785, 230781801]

#: Two venue instants inside the 12-hour hole, at minutes no capture reached.
_VENUE_AT = [T0 - timedelta(hours=8), T0 - timedelta(hours=6)]


def _outcome(oid):
    return SimpleNamespace(id=oid, name=f"Leg {oid}")


def _market(*, source="kalshi", mutually_exclusive=True):
    return SimpleNamespace(
        id=61308736,
        name="2027 US Open Men's Singles Winner",
        source=source,
        mutually_exclusive=mutually_exclusive,
    )


def _venue_row(oid, at):
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker="kalshi",
        probability=_FIELD[oid],
        captured_at=at,
        tier="fine",
    )


def _venue_by_outcome():
    """The bank as the route builds it: six legs, two instants, raw values."""
    return {oid: [_venue_row(oid, at) for at in _VENUE_AT] for oid in _BANKED}


def _captures_and_printed(*, printed_scale=1.0):
    """Our own captures at T0, and what the chart printed for them.

    `printed_scale` 1.0 is an unsqueezed board — the printed number IS the raw
    consensus. Anything else stands in for a de-vig or a squeeze having moved
    the line, which the per-capture comparison must still convict.
    """
    outcome_time_groups = {oid: {T0: [_FIELD[oid]]} for oid in _FIELD}
    devigged = {T0: {oid: p * printed_scale for oid, p in _FIELD.items()}}
    return outcome_time_groups, devigged


def _refusal(*, field_complete, source="kalshi", printed_scale=1.0,
             venue_by_outcome=None, charted=None):
    groups, devigged = _captures_and_printed(printed_scale=printed_scale)
    return futures_route._venue_scale_refusal(
        _market(source=source),
        [_outcome(oid) for oid in (charted if charted is not None else _FIELD)],
        _venue_by_outcome() if venue_by_outcome is None else venue_by_outcome,
        groups,
        devigged,
        field_complete=field_complete,
    )


class TestTheRule:
    def test_an_unsqueezed_board_admits_the_points_the_hole_was_drawn_over(self):
        """The ship. Same bank, same charted field, squeeze already refused."""
        assert _refusal(field_complete=False) is None, (
            "the board prints its raw column (#7747) and the venue points are "
            "raw, so there is no scale left to object to"
        )

    def test_the_same_board_is_still_refused_while_the_squeeze_fires(self):
        """🔴 THE CONTROL, without which the test above proves nothing.

        If this fixture's columns were whole, `field_complete=False` would be
        indistinguishable from a no-op: the refusal would be absent either way
        and a reverted fix would pass. They are not whole — six banked legs
        against a 24-leg charted field — so this is the defect, reproduced.
        """
        assert _refusal(field_complete=True) == (
            "exclusive_field_incomplete_at_venue_instant"
        )

    def test_an_unrecognised_source_keeps_the_refusal(self):
        """The gate fails CLOSED, which is the half a reviewer should check.

        `devig_consensus` divides an unrecognised book's column by its own sum,
        and that is a whole-field operation the captures cannot answer for at an
        unclaimed instant — this docstring's original objection wearing another
        hat. Only `kalshi` / `polymarket` / `datagolf_model` store a column that
        already IS a probability, and they are the only sources a generic-history
        bank is ever built from.
        """
        assert _refusal(field_complete=False, source="draftkings") == (
            "exclusive_field_incomplete_at_venue_instant"
        )

    def test_the_per_capture_measurement_is_not_deleted_by_the_bypass(self):
        """What remains IS the contract in this mode, and it still convicts.

        Skipping the completeness half does not make the route credulous: the
        loop below it MEASURES printed against raw on our own captures, and a
        board whose printed line sits anywhere else is refused exactly as before.
        """
        assert _refusal(field_complete=False, printed_scale=1.04) == (
            "printed_scale_is_not_the_venue_raw_scale"
        )

    def test_a_whole_venue_field_is_still_measured_when_the_squeeze_fires(self):
        """The capability control: this narrows the rule, it does not delete it.

        "Refuse the completeness test WHEN the squeeze is off" is two clauses,
        and shipping only the first would hand every squeezing board its venue
        points unmeasured — the inference #7351 exists to have removed. Here the
        field is complete, the squeeze fires, and a venue column that does not
        survive it is refused on its own evidence.
        """
        # 🪤 THE SUM IS THE WHOLE FIXTURE and the first draft got it wrong.
        # Sinner + Alcaraz alone sum to 0.585, the #23 helper declines below its
        # own trigger, the squeeze IS the identity and this passed while proving
        # nothing — the same threshold trap #7747's file records hitting at
        # 1.015. Mensik carries it to 1.325, inside the band and under
        # `_FIELD_SUM_MAX`, so the squeeze genuinely fires on this column.
        charted = [SINNER, ALCARAZ, MENSIK]
        drifted = {
            # A WHOLE column — every charted leg present at the instant, so the
            # completeness half passes and the measurement half is what speaks.
            oid: [_venue_row(oid, _VENUE_AT[0])] for oid in charted
        }
        assert _refusal(
            field_complete=True, venue_by_outcome=drifted, charted=charted
        ) == "printed_scale_is_not_the_venue_raw_scale"

    def test_a_non_exclusive_family_is_unchanged_in_both_modes(self):
        """#199's markets never entered the squeezable branch and still do not."""
        groups, devigged = _captures_and_printed()
        for complete in (True, False):
            assert futures_route._venue_scale_refusal(
                _market(mutually_exclusive=False),
                [_outcome(oid) for oid in _FIELD],
                _venue_by_outcome(),
                groups,
                devigged,
                field_complete=complete,
            ) is None


class TestTheGateIsActuallyWired:
    """The argument above is inert unless `/history` passes the same flag it
    printed the line with — and #7747's first draft sourced one from the wrong
    predicate and changed nothing on the board it was written for.

    So the handler is run for real over a stubbed session and a stubbed bank,
    and asked the only question a reader cares about: are there venue points in
    the payload.
    """

    @staticmethod
    def _outcome_row(oid, *, last_updated):
        return SimpleNamespace(
            id=oid,
            name=f"Leg {oid}",
            team_id=None,
            probability_change_24h=None,
            current_probability=_FIELD[oid],
            current_yes_bid=_FIELD[oid],
            current_yes_ask=_FIELD[oid],
            resolution_source=None,
            is_winner=None,
            last_updated=last_updated,
            external_id=f"KXATP-27USO-MEN-{oid}",
        )

    @classmethod
    def _market_row(cls, outcomes):
        return SimpleNamespace(
            id=61308736,
            name="2027 US Open Men's Singles Winner",
            source="kalshi",
            market_type="field",
            external_id="KXATP-27USO-MEN",
            status="open",
            mutually_exclusive=True,
            outcomes=outcomes,
            resolution_date=None,
            market_metadata={
                "shape": {
                    "shape": "field",
                    "exhaustive": True,
                    "expected_winners": 1,
                    "outcome_relation": "competitors",
                    "confidence": "high",
                },
                "kalshi_event_ticker": "KXATP-27USO-MEN",
            },
        )

    async def _provenance_points(self, monkeypatch, *, stale_leg):
        """Serve `/history` and count the points marked as venue history."""
        fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
        outcomes = [self._outcome_row(oid, last_updated=fresh) for oid in _FIELD]
        if stale_leg:
            # The shape `stale_observation_keys` withholds on the detail page —
            # one leg observed nine days behind every sibling. This is what
            # makes `field_complete` False, and it is the ONLY difference
            # between this case and its control.
            outcomes[0] = self._outcome_row(
                MENSIK, last_updated=fresh - timedelta(days=9)
            )

        capture_stamps = [fresh - timedelta(hours=h) for h in (30, 3)]
        snaps = [
            SimpleNamespace(
                outcome_id=oid, bookmaker="kalshi", probability=_FIELD[oid],
                yes_bid=_FIELD[oid], yes_ask=_FIELD[oid], last_price=_FIELD[oid],
                captured_at=stamp,
            )
            for stamp in capture_stamps for oid in _FIELD
        ]

        # A REAL `_GenericVenueHistory`, so `in_window`/`describe` run their own
        # code: only the LOAD is stubbed, because that is the half that needs
        # Redis. Its rows sit between the two captures, at instants no capture
        # claims — the 12-hour hole, in miniature.
        venue = futures_route._GenericVenueHistory()
        venue.applicable = True
        venue.state = "warm"
        venue.tier = "cache"
        venue.rows = {
            oid: [_venue_row(oid, fresh - timedelta(hours=h)) for h in (20, 14)]
            for oid in _BANKED
        }

        async def _stub_load(*_a, **_kw):
            return venue

        monkeypatch.setattr(
            futures_route, "_load_generic_venue_history", _stub_load
        )

        payload = await futures_route.get_futures_history(
            61308736,
            outcome_id=None,
            hours=168,
            top_n=50,
            champion=None,
            db=_Session(
                _Result(value=self._market_row(outcomes)),
                _Result(rows=()),
                _Result(rows=snaps),
            ),
        )
        served = [
            point
            for entry in payload["outcomes"]
            for point in entry["history"]
            if point.get("provenance") == "venue_history"
        ]
        return served, payload["venue_history"]

    @pytest.mark.asyncio
    async def test_a_withheld_board_serves_the_bank_it_was_refusing(self, monkeypatch):
        served, block = await self._provenance_points(monkeypatch, stale_leg=True)

        assert served, (
            "the handler still refused a bank on a board it had already stopped "
            "squeezing — the flag is not reaching `_venue_scale_refusal` (#7954)"
        )
        assert block["state"] == "warm"
        assert block["points_served"] == len(served)
        # Served at the venue's RAW value, never converted on the way out.
        by_outcome = {p["probability"] for p in served}
        assert by_outcome <= {round(float(_FIELD[oid]), 6) for oid in _BANKED}

    @pytest.mark.asyncio
    async def test_a_whole_board_still_refuses_the_same_bank(self, monkeypatch):
        """The wiring's own admitted control.

        Identical inputs but for the stale stamp. If this ever goes green the
        fix stopped being conditional and became "serve venue points always",
        which is #7351's defect with a newer issue number on it.
        """
        served, block = await self._provenance_points(monkeypatch, stale_leg=False)

        assert served == []
        assert block["state"] == "refused"
        assert block["refusals"][-1]["reason"] == (
            "exclusive_field_incomplete_at_venue_instant"
        )


class TestTheSiblingRuleIsUntouched:
    """`mean` is imported here for the same reason the route imports it: the
    per-capture comparison is an average over the books at one instant, and a
    single-book board must come out of it unchanged.
    """

    def test_a_single_book_capture_is_its_own_mean(self):
        assert mean([_FIELD[SINNER]]) == _FIELD[SINNER]


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats.

    Entry two is the trade read `_unsupported_price_outcome_ids` makes before
    any snapshot query. Empty means "no trade rows", which fails OPEN, so the
    only thing withholding a leg here is the staleness arm the cases set up.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]
