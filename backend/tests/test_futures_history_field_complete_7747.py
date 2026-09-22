"""#7747 — the hero and the chart under it agree when a leg has been WITHHELD.

#4992 put the two on one scale by running the chart through the detail route's
own two display steps. #7103 then taught the detail route a third argument for
those steps — ``field_complete=prices_withheld == 0`` — because withholding a
leg changes whether the #23 squeeze FIRES, not merely what it divides by: once a
price is refused as UNKNOWN the survivors' sum is not a proved distribution.
The chart never got that argument, so the two scales came back.

WHAT A READER SAW. `/futures/61308736` (*2027 US Open Men's Singles*) at 390px:

    hero + All Outcomes   Jannik Sinner 0.315   ("32%")
    Probability Trend     Jannik Sinner 0.203   ("20%")

both stamped 2026-09-22T03:50:54.864277Z, so it is scale and never staleness.
0.740 of the 1.555 divisor was Jakub Mensik — the one leg the page had just
declined to price (`yes_bid 0.0400` under an `yes_ask 0.7400`, no 24-hour
volume). The refused leg was not merely still in the arithmetic; it WAS the
arithmetic, holding every honest line on the board a third below the number
printed above it.

THE NUMBERS IN THIS FILE ARE PRODUCTION ROWS, read back through
`/api/admin/db-query` on 2026-09-22: all 24 `futures_odds_snapshots` rows for
that market at that instant, one book (kalshi), column sum 1.555. Kept whole
rather than trimmed to the legs under test, for the reason its #4992 sibling
gives: both display steps are functions of the entire field, so a trimmed
fixture measures a different computation.

``TestTheGateIsActuallyWired`` is the half that matters most. A first draft of
this fix changed the helper and sourced the gate from
``_drop_unsupported_snapshot_points`` — which refuses chart POINTS on the
snapshot columns, and correctly keeps Mensik's, because his ``last_price`` is
positive. That draft passed a helper-level test and would have changed nothing
on the board it was written for.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.utils.futures_history_basis import devigged_consensus_by_time


T0 = datetime(2026, 9, 22, 3, 50, 54, 864277, tzinfo=timezone.utc)

#: 230781795 Mensik (the withheld leg) · 230781778 Sinner · 230781780 Alcaraz
#: · 230781797 Ruud. The remaining twenty are the 0.01 tail, kept because the
#: squeeze divides by the field's own sum and dropping them changes it.
MENSIK, SINNER, ALCARAZ, RUUD = 230781795, 230781778, 230781780, 230781797

_FIELD = {
    MENSIK: 0.740, SINNER: 0.315, ALCARAZ: 0.270, RUUD: 0.030,
    230781779: 0.010, 230781785: 0.010, 230781796: 0.010, 230781798: 0.010,
    230781802: 0.010, 230781782: 0.010, 230781783: 0.010, 230781784: 0.010,
    230781786: 0.010, 230781787: 0.010, 230781788: 0.010, 230781789: 0.010,
    230781790: 0.010, 230781791: 0.010, 230781792: 0.010, 230781793: 0.010,
    230781799: 0.010, 230781801: 0.010, 230781781: 0.010, 230781794: 0.010,
}

#: What `/api/futures/61308736` served for the priced legs the same second.
_HERO = {SINNER: 0.315, ALCARAZ: 0.270, RUUD: 0.030}
#: What the Probability Trend drew for them the same second, before this fix.
_CHART_BEFORE = {SINNER: 0.203, ALCARAZ: 0.174, RUUD: 0.019}


def _raw(stamp=T0):
    return {stamp: {"kalshi": dict(_FIELD)}}


class TestTheServedSeries:
    def test_the_class_a_withheld_board_charts_what_the_hero_prints(self):
        """Every priced leg lands on the number the detail payload served."""
        point = devigged_consensus_by_time(
            _raw(), mutually_exclusive=True, field_complete=False
        )[T0]

        for oid, hero in _HERO.items():
            assert point[oid] == pytest.approx(hero, abs=5e-4), (
                f"outcome {oid}: chart {point[oid]:.4f} vs hero {hero:.4f} — "
                "the page is telling two stories again (#7747)"
            )

    def test_the_squeezed_value_is_gone(self):
        """Strawman guard: revert the fix and this is what fails.

        Asked as a RATIO for its #4992 sibling's reason — the divisor scales
        every leg by the same 1.555, so Ruud's absolute gap is 0.011 and an
        absolute threshold would either miss the longshots or stop
        discriminating.
        """
        point = devigged_consensus_by_time(
            _raw(), mutually_exclusive=True, field_complete=False
        )[T0]

        for oid, before in _CHART_BEFORE.items():
            assert point[oid] / before > 1.3, (
                f"outcome {oid} still charts the squeezed {before}, which is "
                "the field divided by a sum 0.740 of which is a refused leg"
            )

    def test_the_fixture_really_does_reproduce_the_defect(self):
        """The control, without which the two assertions above prove nothing.

        If this field did not squeeze, `field_complete=False` would be
        indistinguishable from a no-op and both tests above would pass on a
        reverted fix. It squeezes: the sum is 1.555, inside `_FIELD_SUM_MAX`.
        """
        squeezed = devigged_consensus_by_time(
            _raw(), mutually_exclusive=True, field_complete=True
        )[T0]

        for oid, before in _CHART_BEFORE.items():
            assert squeezed[oid] == pytest.approx(before, abs=5e-4)

    def test_a_whole_field_is_still_squeezed(self):
        """The capability half: this refuses the squeeze, it does not delete it.

        "Refuse the squeeze WHEN a leg is withheld" is two clauses, and shipping
        only the first would silently return every chart on the site to raw
        vig-inclusive prices — #4992's defect, reintroduced by its own fix. The
        admitted control is the same board with the refused leg priced honestly,
        so the field sums to 1.215 — a real distribution carrying an ordinary
        overround, and INSIDE the squeeze's own trigger. 0.20 was tried first
        and is what this replaces: at a sum of 1.015 the #23 helper declines on
        its own threshold, so the assertion passed without the squeeze ever
        running and said nothing about the capability.
        """
        whole = dict(_FIELD)
        whole[MENSIK] = 0.40
        point = devigged_consensus_by_time(
            {T0: {"kalshi": whole}}, mutually_exclusive=True, field_complete=True
        )[T0]

        assert sum(point.values()) == pytest.approx(1.0, abs=0.01)
        assert point[SINNER] != pytest.approx(0.315, abs=1e-6)


class TestTheGateIsActuallyWired:
    """The handler must SOURCE the gate from the set the detail page uses.

    The helper argument above is inert unless `/history` passes it, and the
    first draft of this fix passed one derived from the wrong predicate.
    """

    @staticmethod
    def _outcome(oid, prob, *, last_updated):
        return SimpleNamespace(
            id=oid,
            name=f"Leg {oid}",
            team_id=None,
            probability_change_24h=None,
            current_probability=prob,
            current_yes_bid=prob,
            current_yes_ask=prob,
            resolution_source=None,
            is_winner=None,
            last_updated=last_updated,
            external_id=f"KXATP-27USO-MEN-{oid}",
        )

    @classmethod
    def _market(cls, outcomes, status="open"):
        return SimpleNamespace(
            id=61308736,
            name="2027 US Open Men's Singles Winner",
            source="kalshi",
            market_type="field",
            external_id="KXATP-27USO-MEN",
            status=status,
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

    @staticmethod
    def _snaps(oids, stamps):
        return [
            SimpleNamespace(
                outcome_id=oid,
                bookmaker="kalshi",
                probability=_FIELD[oid],
                yes_bid=_FIELD[oid],
                yes_ask=_FIELD[oid],
                last_price=_FIELD[oid],
                captured_at=stamp,
            )
            for stamp in stamps
            for oid in oids
        ]

    @pytest.mark.asyncio
    async def test_a_board_with_a_withheld_leg_serves_the_unsqueezed_scale(self):
        """One stale leg is enough: the detail withholds it, so the chart must
        print the same scale the hero does."""
        fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
        outcomes = [
            self._outcome(oid, prob, last_updated=fresh)
            for oid, prob in _FIELD.items()
        ]
        # The one leg whose observation is far behind every sibling's — exactly
        # the shape `stale_observation_keys` withholds on the detail page.
        outcomes[0] = self._outcome(
            MENSIK, _FIELD[MENSIK], last_updated=fresh - timedelta(days=9)
        )

        payload = await self._history(outcomes)
        assert payload[SINNER] == pytest.approx(0.315, abs=5e-4), (
            "the handler squeezed a board whose detail page withheld a leg — "
            "the gate is not wired (#7747)"
        )

    @pytest.mark.asyncio
    async def test_a_board_with_nothing_withheld_is_still_squeezed(self):
        """The wiring's own admitted control, for `test_a_whole_field` reason."""
        fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
        outcomes = [
            self._outcome(oid, prob, last_updated=fresh)
            for oid, prob in _FIELD.items()
        ]

        payload = await self._history(outcomes)
        assert payload[SINNER] == pytest.approx(0.203, abs=5e-4), (
            "a complete field stopped being squeezed — this fix refuses the "
            "squeeze on withheld boards, it does not remove it"
        )

    async def _history(self, outcomes):
        """Serve `/history` over a stubbed session and return {oid: last value}."""
        stamps = [
            datetime.now(timezone.utc) - timedelta(hours=h) for h in (3, 2, 1)
        ]
        rows = self._snaps(list(_FIELD), stamps)
        market = self._market(outcomes)

        payload = await futures_route.get_futures_history(
            61308736,
            outcome_id=None,
            hours=168,
            top_n=50,
            champion=None,
            db=_Session(
                _Result(value=market), _Result(rows=()), _Result(rows=rows)
            ),
        )
        return {
            entry["outcome_id"]: entry["history"][-1]["probability"]
            for entry in payload["outcomes"]
            if entry["history"]
        }


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
    only thing withholding a leg in these tests is the staleness arm the cases
    set up deliberately.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]
