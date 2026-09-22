"""#7936 second half — a venue series the reader REFUSES stops counting as
density, so the sparse-window extend the first half re-aimed can actually fire.

WHAT A READER SAW, after the first half shipped. ``26a04aa10`` merged, released
as ``ad6d354e`` at 07:24Z on 2026-09-22, and ``/futures/60608901`` went on
printing **"Limited price history available"** under its default 1W tab. The
after-check failed 3/6 with all three controls unmoved — inert, not a
regression. The served payload, re-read at 07:4xZ:

    /api/futures/60608901/history?hours=168 -> outcomes: 1,  points: 1,  actual_hours: 168
    /api/futures/60608901/history?hours=720 -> outcomes: 10, points: 10, actual_hours: 720

``auto_extended`` never appeared at any width between 168 and 720, so the tier
was not choosing badly — it was never running.

THE CAUSE IS THAT THE GATE COUNTED POINTS NOBODY DRAWS. ``_EXTEND_TIERS`` opens
on ``(len(snapshots) + len(venue_rows)) < 20``, and #7351 put venue rows in that
sum because "an admitted venue observation counts toward is-this-sparse". The
word is ADMITTED. The rows counted were every row ``in_window`` returned, and on
this market the reader refuses the whole series three hundred lines below, on
``_venue_scale_refusal`` — ``venue_history`` in the served payload reads
``{state: refused, points_served: 0, refusals: [exclusive_field_incomplete_at_
venue_instant]}``. The durable bank (``durable_state_snapshots``, identity
``generic-history:60608901``) holds **170 observations inside the seven-day
window, 93 of them on the single charted leg**. So ``1 + 93 < 20`` was false, the
gate stayed shut, and the density that shut it was never drawn. All six markets
of the first half's cohort read the same way: sparse, refused, not extending.

THE FIXTURE IS A MATCHED PAIR AND THE ROW COUNTS ARE IDENTICAL. Three legs,
twenty-one venue rows, one supported capture in the seven-day window and three in
the thirty-day one. The only difference between the two markets is that one leg's
observation at one instant is moved by a minute, which leaves two of the venue's
columns missing a leg — the production refusal, reproduced structurally. The
admitted twin must NOT extend (that is #7351's ship, and it is still right); the
refused twin must. Same counts, same legs, opposite verdicts: a fix that simply
stopped counting venue rows would fail the admitted twin.

WHAT WOULD MAKE THIS FILE VACUOUS. ``TestTheFixtureStillCarriesTheDefect``
asserts each directly rather than asking a reader to trust it:

- If the refused series stopped being refused, the ship arm would be measuring
  #7351's ordinary path and the repair would be untested.
- If the admitted series were also refused, the control could not fail and the
  "stopped counting venue rows entirely" mutation would pass.
- If the venue rows fell below the twenty-point threshold, the gate would open on
  both twins whatever the verdict was.
- If the wider window held no more points than the narrow one, neither twin could
  extend and both assertions would be about nothing.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route

_LEGS = (2001, 2002, 2003)
#: The one leg whose capture lands inside the seven-day window.
_RECENT_ID = 2001
#: Raw venue values that already sum to 1.0, so the squeeze is the identity and
#: the ADMITTED twin clears the second half of the scale contract too. Without
#: this the control would be refused for the other reason and prove nothing.
_VENUE_PROBS = {2001: 0.5, 2002: 0.3, 2003: 0.2}
#: Seven instants x three legs = 21 rows, over the `< 20` threshold. Both twins
#: carry exactly this many; only their timestamps differ.
_VENUE_AGES_HOURS = (6, 18, 30, 42, 54, 66, 78)


def _outcome(oid, prob):
    return SimpleNamespace(
        id=oid,
        name=f"Leg {oid}",
        team_id=None,
        probability_change_24h=None,
        current_probability=prob,
        # A real two-sided book, so #5898 admits every capture below.
        current_yes_bid=0.0200,
        current_yes_ask=0.1800,
        resolution_source=None,
        is_winner=None,
        external_id=f"KXPAIR-26SEP-{oid}",
    )


def _field():
    return [_outcome(oid, _VENUE_PROBS[oid]) for oid in _LEGS]


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


def _seven_day_rows():
    """One supported capture, on one leg — the production sparsity."""
    return [_snap(_RECENT_ID, 2)]


def _thirty_day_rows():
    """Three supported captures across three legs; the wider window is richer."""
    return _seven_day_rows() + [_snap(2002, 24 * 11), _snap(2003, 24 * 14)]


def _venue_rows(*, punch_hole):
    """The venue series: 21 observations, three legs, seven instants.

    🔴 ONE ``now()`` FOR THE WHOLE SERIES, and it is load-bearing. A column is
    keyed on the exact ``captured_at``, so calling ``datetime.now()`` per row
    gives every leg its own microsecond and EVERY column a hole — the admitted
    twin then earns the refused twin's verdict and the control silently stops
    controlling. The first draft of this fixture did exactly that.

    ``punch_hole`` is the whole difference between the two twins: one leg's first
    observation moves by a minute, which empties that instant's column of it and
    creates a second column holding only it. Two incomplete columns, the same 21
    rows, and the refusal the served payload names on 60608901.
    """
    anchor = datetime.now(timezone.utc)
    rows = []
    for age in _VENUE_AGES_HOURS:
        for oid in _LEGS:
            nudge = 1 if (punch_hole and age == _VENUE_AGES_HOURS[0] and oid == _LEGS[-1]) else 0
            rows.append(SimpleNamespace(
                outcome_id=oid,
                bookmaker="kalshi_venue",
                probability=_VENUE_PROBS[oid],
                captured_at=anchor - timedelta(hours=age) + timedelta(minutes=nudge),
            ))
    return rows


def _admitted_venue_rows():
    """Every leg observed at every instant — a complete field, nothing to refuse."""
    return _venue_rows(punch_hole=False)


def _refused_venue_rows():
    """The same 21 rows, with one leg's first observation a minute out of column."""
    return _venue_rows(punch_hole=True)


def _market(outcomes):
    return SimpleNamespace(
        id=60608901,
        name="AFC Defensive Player of the Month in September",
        source="kalshi",
        market_type="championship",
        external_id="KXNFLDPOM-26SEP",
        outcomes=outcomes,
        resolution_date=None,
        market_metadata={"kalshi_event_ticker": "KXNFLDPOM-26SEP"},
    )


def _field_ids(outcomes=None):
    return futures_route._exclusive_field_outcome_ids([_market(outcomes or _field())])


def _venue_series(rows):
    """#7351's own holder, populated — not a stand-in.

    ``in_window`` is the real one, so the window filter, the charted-id filter
    and ``unclaimed_instants`` all behave as production does.
    """
    venue = futures_route._GenericVenueHistory()
    venue.applicable = True
    venue.state = "warm"
    venue.payload = {"built_at": None, "status": "ok", "scale": "raw"}
    for row in rows:
        venue.rows.setdefault(row.outcome_id, []).append(row)
    return venue


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
    """Answers each ``execute`` from a queue; the last entry repeats, so a
    further tier can re-ask and can never improve on the 30-day answer."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


def _session(outcomes, seven, thirty):
    return _Session(_Result(value=_market(outcomes)), _Result(rows=seven), _Result(rows=thirty))


async def _history(db, venue_rows, monkeypatch, *, hours=168):
    """Call the handler the way FastAPI does — every Query parameter RESOLVED."""

    async def _fake_load(market, outcomes, field_ids, db_):
        return _venue_series(venue_rows)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(futures_route, "_load_generic_venue_history", _fake_load)
    monkeypatch.setattr(futures_route, "_consider_generic_history_fill", _noop)
    return await futures_route.get_futures_history(
        60608901, outcome_id=None, hours=hours, top_n=10, champion=None, db=db
    )


def _served(payload):
    return {e["outcome_id"]: len(e["history"]) for e in payload["outcomes"]}


# ── The ship ────────────────────────────────────────────────────────────────

class TestTheShip:
    @pytest.mark.asyncio
    async def test_a_refused_venue_series_no_longer_holds_the_sparse_window_shut(
        self, monkeypatch
    ):
        """The reader-facing arm: the window widens and the chart gets its points.

        Below two points the web chart prints "Limited price history available"
        and draws nothing, which is what was photographed at 390px after the
        first half released. The assertion is on the SERVED payload.
        """
        payload = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()),
            _refused_venue_rows(),
            monkeypatch,
        )

        assert payload["actual_hours"] == 720
        assert payload.get("auto_extended") is True
        assert payload["total_data_points"] == 3
        assert set(_served(payload)) == set(_LEGS)
        assert payload["hours"] == 168, "the REQUESTED window is still reported as asked"

    @pytest.mark.asyncio
    async def test_the_refused_series_is_still_refused_on_the_widened_window(
        self, monkeypatch
    ):
        """Widening is a decision about how far back to READ. It is not a licence
        to draw the series the scale contract refused, and the receipt must go on
        saying so — otherwise this ship would have quietly admitted 93 points at
        a scale nobody ruled on."""
        payload = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()),
            _refused_venue_rows(),
            monkeypatch,
        )

        venue_block = payload["venue_history"]
        assert venue_block["state"] == "refused"
        assert venue_block["points_served"] == 0
        assert [r["reason"] for r in venue_block["refusals"]] == [
            "exclusive_field_incomplete_at_venue_instant"
        ]


# ── #7351's ship is still #7351's ship ──────────────────────────────────────

class TestAnAdmittedSeriesStillCountsAsDensity:
    @pytest.mark.asyncio
    async def test_an_admitted_venue_series_still_keeps_the_window_narrow(
        self, monkeypatch
    ):
        """THE CONTROL, and the reason this fix is not "stop counting venue rows".

        #7351's ship is that a market the venue documents well stops being
        stretched to thirty days to find nine points. These 21 rows are drawn, so
        they are density, so the gate stays shut — on a fixture whose captures
        and snapshot counts are otherwise identical to the twin above.
        """
        payload = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()),
            _admitted_venue_rows(),
            monkeypatch,
        )

        assert payload["actual_hours"] == 168
        assert payload.get("auto_extended") in (False, None)
        assert payload["venue_history"]["points_served"] > 0

    @pytest.mark.asyncio
    async def test_the_two_twins_differ_only_in_the_verdict_they_earn(
        self, monkeypatch
    ):
        """One assertion over the pair, so a later edit cannot fix one twin by
        breaking the other. Same leg set, same capture rows, same venue row
        count — opposite windows."""
        refused = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()),
            _refused_venue_rows(),
            monkeypatch,
        )
        admitted = await _history(
            _session(_field(), _seven_day_rows(), _thirty_day_rows()),
            _admitted_venue_rows(),
            monkeypatch,
        )

        assert len(_refused_venue_rows()) == len(_admitted_venue_rows())
        assert (refused["actual_hours"], admitted["actual_hours"]) == (720, 168)


# ── Vacuity: does the fixture still carry the defect? ───────────────────────

class TestTheFixtureStillCarriesTheDefect:
    def test_the_refused_series_is_actually_refused_by_the_readers_own_rule(self):
        """Asked of ``_venue_scale_refusal`` itself, with the reason named. If
        this series became servable the ship arm above would be measuring
        #7351's ordinary path."""
        by_outcome = {}
        for row in _refused_venue_rows():
            by_outcome.setdefault(row.outcome_id, []).append(row)

        assert futures_route._venue_scale_refusal(
            _market(_field()), _field(), by_outcome, {}, {}
        ) == "exclusive_field_incomplete_at_venue_instant"

    def test_the_admitted_series_clears_the_whole_scale_contract(self):
        """Both halves — no hole AND the squeeze is the identity at every venue
        instant. If it were refused for either reason the control could not fail
        and "stop counting venue rows entirely" would pass this file."""
        by_outcome = {}
        for row in _admitted_venue_rows():
            by_outcome.setdefault(row.outcome_id, []).append(row)

        assert futures_route._venue_scale_refusal(
            _market(_field()), _field(), by_outcome, {}, {}
        ) is None

    def test_the_venue_series_is_large_enough_to_shut_the_gate_on_its_own(self):
        """Under twenty rows the gate would open whatever the verdict was, and
        both twins would extend for a reason that has nothing to do with this
        change."""
        assert len(_seven_day_rows()) + len(_admitted_venue_rows()) >= 20
        assert len(_seven_day_rows()) < 20

    def test_the_wider_window_is_richer_than_the_narrow_one(self):
        """Without this neither twin could extend and the pair would agree by
        construction."""
        narrow = futures_route._drop_unsupported_snapshot_points(
            _seven_day_rows(), _field(), _field_ids()
        )
        wide = futures_route._drop_unsupported_snapshot_points(
            _thirty_day_rows(), _field(), _field_ids()
        )
        assert len(narrow) == 1
        assert len(wide) == 3

    def test_the_venue_rows_survive_the_window_and_the_unclaimed_instant_filter(self):
        """``in_window`` could drop these for reasons that have nothing to do
        with the verdict — the cutoff, the charted-id gate, or an instant a
        capture already speaks for. If it did, the gate would open on both twins
        and the control would be inert."""
        venue = _venue_series(_admitted_venue_rows())
        cutoff = datetime.now(timezone.utc) - timedelta(hours=168)
        kept = venue.in_window(cutoff, _seven_day_rows(), list(_LEGS))
        assert len(kept) == len(_admitted_venue_rows())


# ── One predicate, two callers ──────────────────────────────────────────────

class TestTheGateAndTheReaderShareOneRule:
    def test_the_density_count_agrees_with_the_readers_verdict_on_both_twins(self):
        """Behavioural parity, not a source scan. The gate's count and the
        reader's refusal are two callers of ``_venue_field_columns``; if a later
        edit gives either its own copy of the hole test they can drift, and the
        drift is the defect this ship closed."""
        for rows, expected in ((_refused_venue_rows(), 0), (_admitted_venue_rows(), 21)):
            by_outcome = {}
            for row in rows:
                by_outcome.setdefault(row.outcome_id, []).append(row)
            refusal = futures_route._venue_scale_refusal(
                _market(_field()), _field(), by_outcome, {}, {}
            )
            density = futures_route._venue_points_countable_as_density(
                _market(_field()), _field(), rows, set(_LEGS)
            )
            assert density == expected
            assert (density == 0) == bool(refusal)

    def test_an_unsqueezed_board_earns_no_hole_refusal_and_so_keeps_its_density(self):
        """#7954's bypass must reach BOTH callers, or this ship discounts a series
        the reader draws.

        A board that refused the squeeze (`field_complete=False` on a source whose
        stored column already IS a probability) has no whole-field operation for a
        venue point to be contemporaneous with, so the hole test does not apply and
        the reader serves the series. A gate that did not know that would go on
        counting those same rows as zero and widen a window that is not sparse —
        #7351's ship broken from the other end. The twin whose columns have holes
        is used deliberately: under the default flag it counts nothing, and the two
        answers must differ only because the flag differs.
        """
        rows = _refused_venue_rows()
        by_outcome = {}
        for row in rows:
            by_outcome.setdefault(row.outcome_id, []).append(row)

        assert _market(_field()).source in ("kalshi", "polymarket", "datagolf_model"), (
            "the bypass only applies to a source whose column is already a "
            "probability; on any other source this test would assert nothing"
        )
        assert futures_route._venue_scale_refusal(
            _market(_field()), _field(), by_outcome, {}, {}, field_complete=False
        ) is None
        assert futures_route._venue_points_countable_as_density(
            _market(_field()), _field(), rows, set(_LEGS), field_complete=False
        ) == 21
        # And the flag is the only thing that moved.
        assert futures_route._venue_points_countable_as_density(
            _market(_field()), _field(), rows, set(_LEGS), field_complete=True
        ) == 0

    def test_a_series_outside_the_charted_set_counts_nothing(self):
        """``in_window`` already filters to the charted ids, so this is belt and
        braces — but a leg nobody charts is not density on anybody's chart."""
        assert futures_route._venue_points_countable_as_density(
            _market(_field()), _field(), _admitted_venue_rows(), set()
        ) == 0

    def test_an_empty_series_counts_nothing_and_asks_nothing(self):
        assert futures_route._venue_points_countable_as_density(
            _market(_field()), _field(), [], set(_LEGS)
        ) == 0
