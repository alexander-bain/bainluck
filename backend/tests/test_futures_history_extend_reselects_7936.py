"""#7936 — the sparse-window extend stops filtering through a selection made
before the window was known to be wrong.

WHAT A READER SAW. ``/futures/60608901`` ("AFC Defensive Player of the Month in
September", a 50-outcome Kalshi board) drew a real two-series probability trend
captioned *"Too few prices in 7 days — showing 30 days."* Six minutes later, and
on two further shots — the last after an 80-second quiet window, so it is not
rate limiting — the same page drew **"Limited price history available"** and no
chart at all, over a market whose 30-day read serves ten points across ten legs.

Re-read on production 2026-09-22 05:31Z, unchanged:

    /api/futures/60608901/history?hours=168 -> outcomes: 1,  total_data_points: 1
    /api/futures/60608901/history?hours=720 -> outcomes: 10, total_data_points: 10

THE CAUSE IS THAT THE SELECTION OUTLIVED ITS WINDOW. The charted legs are chosen
from the REQUESTED window: chartable legs first (#7546), then the rest by
``current_probability``. When seven days hold one supported point, ``chartable``
is one id and the other nine slots go to the top ``current_probability`` legs —
which on a 50-leg board are untraded longshots holding no point at 30 days
either. ``_EXTEND_TIERS`` then widened to 720 hours and filtered the result
through those same ten ids, so its ``>`` test compared 1 against 1, refused,
and ``actual_hours`` stayed 168. The extend was present and correctly aimed; it
was asking whether legs chosen from a window too sparse to choose from had got
any richer, and on exactly the markets the tier exists to rescue the answer is
no by construction.

THE CLASS IS WIDER THAN THE EMPTY CHART, measured on production the same night
over the 60 open markets (of 400 sampled, all with >10 outcomes) whose 7-day
window holds under 20 points, i.e. every market for which the tier fires. Seven
were served strictly fewer points or lines than a direct 30-day read of the same
market returns — ``108687`` served 38 points across 3 lines where 720 hours
holds 220 across 10. The empty chart is this defect's worst case, not its only
one; a chart silently missing seven of its ten lines is the common one.

THE FIXTURE IS THE PRODUCTION SHAPE AND ITS NUMBERS ARE THE PRODUCTION NUMBERS:
fifty legs, forty of them untraded longshots ranked top by
``current_probability``, ten holding one supported point each, and exactly one
of those ten inside the seven-day window. The requested window therefore serves
1 point over 1 leg and the wider window serves 10 over 10 — the served payload
above, reproduced. Ages are offsets from ``now`` so the fixture cannot age out of
the window it describes (gotcha #44 — offset first, never anchor on a date).

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it rather
than trust it. ``TestTheFixtureStillCarriesTheDefect`` asserts each one directly:

- If the field shrank to ten legs or fewer, every leg would be charted, the two
  windows could not disagree, and the ship arm would pass on a market with no
  selection to make.
- If a second leg's point drifted inside the seven-day window, the pre-extend
  selection would already reach the legs that hold points and the old code would
  have widened correctly.
- If the support filter began refusing these points, both windows would serve
  nothing and every count below would agree at zero.
- If the ten legs that hold points were ranked ABOVE the forty that do not, the
  pre-extend selection would sweep them in by ``current_probability`` alone and
  the re-derivation would be doing no work. The inversion is asserted.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.routes.futures import _select_charted_outcome_ids


# ── The board ───────────────────────────────────────────────────────────────
# Forty untraded longshots, ids 1001-1040, ranked TOP by `current_probability`
# and holding no point in any window. This is the production inversion: on a
# Kalshi field board the untraded legs carry the biggest number in that column.
_DEAD_IDS = list(range(1001, 1041))
# Ten legs holding one supported point each, ids 1041-1050, ranked BOTTOM. Nine
# of their points sit 8-25 days back; 1050's sits two hours back, so it is the
# single leg the seven-day window can see.
_LIVE_IDS = list(range(1041, 1051))
_RECENT_ID = 1050
# A graded winner priced BELOW every leg that can draw, added only by the #225
# test: the eleventh chartable leg on a ten-slot chart, so the forcing clause is
# the only thing that can seat it.
_WINNER_ID = 1051


def _outcome(oid, prob, *, is_winner=None, name=None):
    return SimpleNamespace(
        id=oid,
        name=name or f"Player {oid}",
        team_id=None,
        probability_change_24h=None,
        current_probability=prob,
        # A real two-sided book, so #5898 admits every point these legs hold.
        current_yes_bid=0.0200,
        current_yes_ask=0.1800,
        resolution_source=None,
        is_winner=is_winner,
        external_id=f"KXNFLDPOM-26SEP-{oid}",
    )


def _snap(oid, age_hours, prob=0.05):
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker="kalshi",
        probability=prob,
        yes_bid=0.0200,
        yes_ask=0.1800,
        last_price=0.0500,
        captured_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )


def _refused_snap(oid, age_hours, prob=0.30):
    """A point #5898 refuses: nobody bid and the venue reports no trade.

    These sit on the TOP-priced dead legs in the wider window, so a
    re-derivation that selected on the raw extended field rather than the
    support-filtered one would spend the chart's slots on legs that draw
    nothing — #7546's defect, rebuilt inside its own repair.
    """
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker="kalshi",
        probability=prob,
        yes_bid=0.0000,
        yes_ask=prob,
        last_price=0.0000,
        captured_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )


def _venue_row(oid, age_hours, prob=0.05):
    """A venue observation (#7351): real stamp, raw value, own provenance."""
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker="kalshi_venue",
        probability=prob,
        captured_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )


def _field(overrides=None):
    """Fifty legs; the forty that cannot draw rank above the ten that can."""
    overrides = overrides or {}
    dead = [
        _outcome(oid, 0.30 - 0.005 * i, **overrides.get(oid, {}))
        for i, oid in enumerate(_DEAD_IDS)
    ]
    live = [
        _outcome(oid, 0.020 - 0.001 * i, **overrides.get(oid, {}))
        for i, oid in enumerate(_LIVE_IDS)
    ]
    return dead + live


def _seven_day_rows():
    """What the requested window holds: one supported point, on one leg."""
    return [_snap(_RECENT_ID, 2)]


# The five top-priced dead legs also carry a REFUSED point in the wider window.
# They are what makes the support filter load-bearing in the re-derivation: on
# the raw field they are the five best-ranked chartable legs there are.
_REFUSED_IDS = _DEAD_IDS[:5]


def _thirty_day_rows():
    """What the wider window holds: ten supported points across ten legs, plus
    five refused points on the legs priced above all of them."""
    older = [_snap(oid, 24 * (8 + 2 * i)) for i, oid in enumerate(_LIVE_IDS[:-1])]
    refused = [_refused_snap(oid, 24 * (9 + 2 * i)) for i, oid in enumerate(_REFUSED_IDS)]
    return older + _seven_day_rows() + refused


def _market(outcomes):
    """The production market row, including the shape verdict the rules read.

    ``market_type='field'`` plus this ``shape`` block is what makes
    ``market_is_proved_exclusive_field`` true. That is the real board's state —
    fifty players, one winner — and it is what brings #6846's ask-only bound to
    bear, which is the arm that refuses the untraded legs' points. Weakening it
    would leave those points supported and quietly test a different rule.
    """
    return SimpleNamespace(
        id=60608901,
        name="AFC Defensive Player of the Month in September",
        source="kalshi",
        market_type="field",
        external_id="KXNFLDPOM-26SEP",
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
            "kalshi_event_ticker": "KXNFLDPOM-26SEP",
        },
    )


def _field_ids(outcomes=None):
    """The exclusive-field id set the handler computes, so the vacuity tests
    classify rows exactly as the route does rather than with an empty set."""
    return futures_route._exclusive_field_outcome_ids([_market(outcomes or _field())])


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

    The repeat is what lets the 90-day tier re-ask without this file knowing how
    many tiers ran: it gets the 30-day rows back, so it can never improve on the
    30-day answer and the window under test is the one the assertions name.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


def _session(outcomes, seven, thirty):
    return _Session(_Result(value=_market(outcomes)), _Result(rows=seven), _Result(rows=thirty))


async def _history(db, *, hours=168, outcome_id=None, top_n=10, champion=None):
    """Call the handler the way FastAPI does — every Query parameter RESOLVED.

    Omitting one hands the function the unresolved ``Query`` default object:
    ``top_n`` then raises inside ``min()`` and ``outcome_id`` reads as a
    single-outcome filter that skips the selection this file exists to measure.
    """
    return await futures_route.get_futures_history(
        60608901, outcome_id=outcome_id, hours=hours, top_n=top_n, champion=champion, db=db
    )


def _served(payload):
    return {e["outcome_id"]: len(e["history"]) for e in payload["outcomes"]}


# ── The ship ────────────────────────────────────────────────────────────────

class TestTheShip:
    @pytest.mark.asyncio
    async def test_the_sparse_window_stops_serving_one_point_over_a_board_that_holds_ten(self):
        """The reader-facing arm: 1 point/1 leg becomes 10 points/10 legs.

        Below two points the web chart prints "Limited price history available"
        and draws nothing, which is what a reader photographed. The assertion is
        on the SERVED payload, not on the selection, because the empty state is
        a function of `total_data_points`.
        """
        outcomes = _field()
        payload = await _history(
            _session(outcomes, _seven_day_rows(), _thirty_day_rows())
        )

        assert payload["total_data_points"] == 10
        assert set(_served(payload)) == set(_LIVE_IDS)
        assert payload["actual_hours"] == 720
        assert payload["hours"] == 168, "the REQUESTED window is still reported as asked"
        assert payload.get("auto_extended") is True

    @pytest.mark.asyncio
    async def test_the_extended_request_serves_what_a_direct_thirty_day_read_serves(self):
        """The production discriminator, mirrored.

        `?hours=720` re-runs the selection over the 30-day window, so it is
        exactly what a correctly-scoped extend should deliver. On production
        these two reads disagreed 1-vs-10; they must now agree, because they are
        now the same rule over the same rows.
        """
        asked = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()), hours=168
        )
        direct = await _history(
            _session(_field(), _thirty_day_rows(), _thirty_day_rows()), hours=720
        )

        assert _served(asked) == _served(direct)
        assert asked["total_data_points"] == direct["total_data_points"] == 10


# ── Vacuity: does the fixture still carry the defect? ───────────────────────

class TestTheFixtureStillCarriesTheDefect:
    def test_the_field_is_larger_than_the_charts_ten_slots(self):
        """With <=10 legs every leg is charted and the windows cannot disagree."""
        assert len(_field()) == 50
        assert len(_field()) > 10

    def test_exactly_one_leg_is_chartable_inside_the_seven_day_window(self):
        """A second one would let the pre-extend selection reach the live legs."""
        assert {r.outcome_id for r in _seven_day_rows()} == {_RECENT_ID}

    def test_the_wider_window_holds_ten_supported_points_across_ten_legs(self):
        supported = futures_route._drop_unsupported_snapshot_points(
            _thirty_day_rows(), _field(), _field_ids()
        )
        assert len(supported) == 10
        assert {r.outcome_id for r in supported} == set(_LIVE_IDS)

    def test_the_wider_window_also_holds_refused_points_on_better_priced_legs(self):
        """Without these the support filter is inert inside the re-derivation and
        a selection taken from the RAW extended field would score identically."""
        rows = _thirty_day_rows()
        supported_ids = {
            r.outcome_id
            for r in futures_route._drop_unsupported_snapshot_points(rows, _field(), _field_ids())
        }
        refused = [r for r in rows if r.outcome_id not in supported_ids]
        assert {r.outcome_id for r in refused} == set(_REFUSED_IDS)

        by_id = {o.id: o.current_probability for o in _field()}
        assert min(by_id[i] for i in _REFUSED_IDS) > max(by_id[i] for i in _LIVE_IDS), (
            "the refused legs must out-rank every leg that can draw, or a raw-field "
            "selection would not prefer them and this fixture would prove nothing"
        )

    def test_the_legs_that_hold_points_are_ranked_below_the_legs_that_do_not(self):
        """The production inversion. Without it the pre-extend selection would
        sweep the live legs in on ``current_probability`` alone and the
        re-derivation would have nothing to repair."""
        by_id = {o.id: o.current_probability for o in _field()}
        assert max(by_id[i] for i in _LIVE_IDS) < min(by_id[i] for i in _DEAD_IDS)

    def test_the_support_filter_admits_the_seven_day_point(self):
        """If #5898 began refusing this row both windows would serve nothing and
        every count in this file would agree at zero."""
        kept = futures_route._drop_unsupported_snapshot_points(
            _seven_day_rows(), _field(), _field_ids()
        )
        assert len(kept) == 1

    def test_the_pre_extend_selection_reaches_only_one_leg_that_holds_a_point(self):
        """THE OLD RULE'S ANSWER, computed from the fixture rather than quoted.

        This is the defect itself: the selection taken from the seven-day window
        contains exactly one of the ten legs that hold points, so filtering a
        30-day read through it can only ever find that one point back — it
        compared 1 against 1 and refused to widen.
        """
        pre_extend = _select_charted_outcome_ids(
            _field(), {_RECENT_ID}, 10, None
        )
        assert len(set(pre_extend) & set(_LIVE_IDS)) == 1
        supported = futures_route._drop_unsupported_snapshot_points(
            _thirty_day_rows(), _field(), _field_ids()
        )
        reachable = [r for r in supported if r.outcome_id in set(pre_extend)]
        assert len(reachable) == 1, (
            "the old rule could see one point in thirty days, and compared it "
            "against the one point it already had"
        )


# ── The common case cannot move ─────────────────────────────────────────────

class TestTheCommonCaseCannotMove:
    @pytest.mark.asyncio
    async def test_a_dense_window_never_extends_and_keeps_todays_order(self):
        """A market with enough points never reaches the tiers at all, so this
        change cannot be observed on it."""
        outcomes = _field()
        dense = [_snap(oid, 1 + i) for i in range(3) for oid in _LIVE_IDS]
        assert len(dense) >= 20, "below the first tier this would extend and prove nothing"

        payload = await _history(_session(outcomes, dense, dense))

        assert payload["actual_hours"] == 168
        assert payload.get("auto_extended") in (False, None)
        assert set(_served(payload)) == set(_LIVE_IDS)

    @pytest.mark.asyncio
    async def test_an_extend_that_finds_the_same_legs_returns_the_same_selection(self):
        """The tier still fires, but the wider window turns up no leg the narrow
        one lacked — so the re-derived answer is the pre-extend answer."""
        outcomes = _field()
        seven = [_snap(oid, 2) for oid in _LIVE_IDS]
        thirty = seven + [_snap(oid, 24 * 12) for oid in _LIVE_IDS]

        pre_extend = _select_charted_outcome_ids(
            outcomes, {r.outcome_id for r in seven}, 10, None
        )
        payload = await _history(_session(outcomes, seven, thirty))

        assert list(_served(payload)) == [
            oid for oid in pre_extend if oid in _served(payload)
        ]
        assert set(_served(payload)) == set(pre_extend)


# ── A pinned caller is never re-selected ────────────────────────────────────

class TestAPinnedCallerIsNeverReselected:
    @pytest.mark.asyncio
    async def test_an_explicit_outcome_id_survives_the_extend_alone(self):
        """``?outcome_id=`` is a caller asking for ONE line. The tiers may widen
        its window; they may not hand it nine legs it did not ask for."""
        payload = await _history(
            _session(_field(), [], _thirty_day_rows()), outcome_id=1041
        )

        assert set(_served(payload)) <= {1041}


# ── #225 and #232 survive the re-derivation ────────────────────────────────

class TestTheForcedLinesSurviveTheRederivation:
    @pytest.mark.asyncio
    async def test_a_graded_winner_is_still_forced_in_after_the_extend_reselects(self):
        """#225 item 3 — a settled board charts the leg that won, however long a
        shot it was. The re-derivation runs the same forcing clause, so a winner
        outside the top ten is still charted after the window widens.

        🔴 THE WINNER MUST BE UNSELECTABLE BY RANK OR THIS TEST PROVES NOTHING.
        An earlier draft graded `_DEAD_IDS[-1]`, whose 0.105 out-ranks every leg
        that can draw: once it held a point it was chartable and the sort put it
        in the ten on its own, so deleting the forcing clause left the test green
        through a real regression. It is priced BELOW all ten live legs here, so
        it is the eleventh chartable leg on a ten-slot chart and only #225 can
        seat it. The mutation that deletes the clause now fails this.
        """
        winner_id = _WINNER_ID
        outcomes = _field() + [_outcome(winner_id, 0.0005, is_winner=True)]
        thirty = _thirty_day_rows() + [_snap(winner_id, 24 * 9), _snap(winner_id, 24 * 12)]

        by_id = {o.id: o.current_probability for o in outcomes}
        assert by_id[winner_id] < min(by_id[i] for i in _LIVE_IDS), (
            "a winner the sort would seat anyway cannot test the forcing clause"
        )

        selection = _select_charted_outcome_ids(
            outcomes, {r.outcome_id for r in thirty}, 10, None
        )
        assert winner_id in selection
        assert selection.index(winner_id) >= 10, "seated by the clause, not by rank"

        payload = await _history(_session(outcomes, _seven_day_rows(), thirty))
        assert winner_id in _served(payload)

    def test_the_named_champion_is_still_forced_in_after_the_extend_reselects(self):
        """#232 — the odds_api winner-field class, where the champion is known
        only by NAME and carries no ``is_winner`` grade."""
        champ_id = _DEAD_IDS[0]
        outcomes = _field()
        champ_name = next(o.name for o in outcomes if o.id == champ_id)

        # Chartable set that excludes the champion entirely: without the clause
        # it could not be selected, so this asserts the clause and not the sort.
        selection = _select_charted_outcome_ids(
            outcomes, set(_LIVE_IDS), 10, champ_name
        )
        assert champ_id in selection
        assert set(_LIVE_IDS) <= set(selection), "the chartable legs keep their slots"


# ── The adoption is whole ───────────────────────────────────────────────────

def _venue_series(rows):
    """#7351's own holder, populated — not a stand-in.

    ``in_window`` is the real one, so it filters on the window, on the charted
    ids and on `unclaimed_instants` exactly as production does. A hand-written
    stub here would be asserting my idea of the seam rather than the seam, and
    the gate under test (`charted_ids`) sits downstream of it.
    """
    venue = futures_route._GenericVenueHistory()
    venue.applicable = True
    venue.state = "ok"
    venue.payload = {"built_at": None, "status": "ok", "scale": "raw"}
    for row in rows:
        venue.rows.setdefault(row.outcome_id, []).append(row)
    return venue


class TestTheAdoptionIsWhole:
    """``charted_ids`` gates the venue series (#7351). Adopting the wider
    window's points while leaving that set on the narrow window's answer would
    serve this window's captures under the other window's gate, and the venue
    half of every re-selected leg would vanish silently.
    """

    @pytest.mark.asyncio
    async def test_a_reselected_legs_venue_points_survive_the_extend(self, monkeypatch):
        venue_leg = _LIVE_IDS[0]
        pre_extend = _select_charted_outcome_ids(_field(), {_RECENT_ID}, 10, None)
        assert venue_leg not in pre_extend, (
            "the leg must be one the narrow window did NOT chart, or the stale "
            "gate would admit it anyway and this test would prove nothing"
        )

        async def _fake_load(market, outcomes, field_ids, db):
            return _venue_series([_venue_row(venue_leg, 24 * 10)])

        async def _noop(*a, **k):
            return None

        monkeypatch.setattr(futures_route, "_load_generic_venue_history", _fake_load)
        monkeypatch.setattr(futures_route, "_consider_generic_history_fill", _noop)
        monkeypatch.setattr(futures_route, "_venue_scale_refusal", lambda *a, **k: None)

        payload = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows())
        )

        assert payload["actual_hours"] == 720
        served = _served(payload)
        assert served.get(venue_leg) == 2, (
            "one capture plus one venue observation; a stale `charted_ids` drops "
            "the venue point and leaves 1"
        )
        assert payload["total_data_points"] == 11


# ── One rule, two call sites ────────────────────────────────────────────────

class TestBothWindowsRunOneRule:
    @pytest.mark.asyncio
    async def test_the_served_selection_is_the_helper_run_on_the_window_served(self):
        """Behavioural parity, not a source scan: whatever the handler served,
        it is what the shared rule returns for the window it reports. If a later
        edit re-inlines the selection at either call site, the two answers drift
        and this fails.
        """
        outcomes = _field()
        payload = await _history(
            _session(outcomes, _seven_day_rows(), _thirty_day_rows())
        )
        assert payload["actual_hours"] == 720

        # The chartable set is taken from the SUPPORT-FILTERED extended field,
        # which is what the handler hands the rule. Building it from the raw rows
        # here would assert the mutation rather than the code.
        supported = futures_route._drop_unsupported_snapshot_points(
            _thirty_day_rows(), outcomes, _field_ids()
        )
        expected = _select_charted_outcome_ids(
            outcomes, {r.outcome_id for r in supported}, 10, None
        )
        assert set(_served(payload)) <= set(expected)
        # Every leg that holds a point in the served window is drawn; the rest of
        # the ten are legs with nothing to show, which draw no series.
        assert set(_served(payload)) == {r.outcome_id for r in supported} & set(expected)
        assert set(_served(payload)) == set(_LIVE_IDS)

    def test_the_rule_falls_back_whole_when_no_leg_is_chartable(self):
        """#7546's own fallback, which the extraction must not have dropped: with
        nothing chartable the partition carries no information and today's
        ``current_probability`` order stands."""
        outcomes = _field()
        selection = _select_charted_outcome_ids(outcomes, set(), 10, None)
        assert selection == _DEAD_IDS[:10]
