"""#7284 — the chart's participant table and the ladder under it are one answer.

The phone's Market Details screen renders `/api/futures/{id}/probability-timeline`
and `/api/futures/{id}` one above the other, often inside one viewport. #4079's
numeric repair landed on the second and not the first, so the table went on
serving raw prices and per-write deltas while the ladder served the board's
normalized price and #4079's dated amount — or its refusal.

WHAT A READER SAW (native/255, iPhone 17 Pro simulator, 2026-09-19 18:48-18:55Z,
payloads fetched in the same pass):

    /futures/58776433  table `October 1 - 31, 2026  59%  +12.5%`
                       ladder `October 1 - 31, 2026  49%  (no movement)`
    /futures/60268421  table 10 movement claims against the ladder's 7, two of
                       them on rows the ladder withheld
    /futures/58321581  table -0.4% on a row whose detail value is null

Web is not affected — it has no 24h column here and picks its series off the
deduped board — which is why the ship's own AFTER-check could not see it.

#6641 fixed ONE of these disagreements (a duplicate leg) by porting one rule.
This file pins the general form: the timeline reader does not re-derive the
display policy, it ASKS `_format_market_detail` and serves the answer. So the
assertions below are mostly of one shape — *the table equals the board* — and
that is the point. A test that pinned particular numbers would pass a reader
that had merely been taught today's arithmetic.

The plotted history is deliberately NOT rescaled (codex, 2026-09-19): those are
real observations at real instants, and dividing them by today's field sum would
assert a displayed percent nobody observed. `test_the_history_is_not_rescaled`
is the control that keeps that decision visible.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.futures as futures_routes
from app.routes.futures import _format_market_detail, get_probability_timeline

#: The minute the Danube board was read off production.
MEASURED_AT = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)

# (id, name, probability) — market 58776433's `futures_outcomes` rows.
DANUBE_ROWS = [
    (1, "October 1 - 31, 2026", 0.590000),
    (2, "Does not return by November 1, 2026", 0.294500),
    (3, "Before September 1, 2026", 0.163000),
    (4, "September 15 - 30, 2026", 0.145000),
    (5, "September 1 - 14, 2026", 0.001000),
]


@contextmanager
def _at(instant: datetime = MEASURED_AT):
    """Both readers on one clock, so an expiry boundary cannot split them."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    with patch.object(futures_routes, "datetime", _Frozen):
        yield


def _outcome(oid, name, prob, *, change=None, opening=None, bid=None, ask=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"0x{oid:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=change,
        opening_probability=opening,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=MEASURED_AT,
        price_changed_at=MEASURED_AT,
        team_id=None,
        team=None,
        current_yes_bid=bid,
        current_yes_ask=ask,
    )


def _market(outcomes, *, mid=58776433, status="open", me=True, source="polymarket"):
    return SimpleNamespace(
        id=mid,
        name="When will the Danube River return to normal levels?",
        description=None,
        category="weather",
        source=source,
        external_id="828358",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=2,
        llm_sport_category="weather",
        mutually_exclusive=me,
        commence_time=MEASURED_AT - timedelta(hours=2),
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


def _danube(rows=None, **kw):
    return _market([_outcome(*r) for r in (rows or DANUBE_ROWS)], **kw)


async def _timeline(market, top=10):
    """The route, on a db that answers every query it can ask.

    Order-insensitive on purpose: the withheld-price arms run their own queries
    before the snapshot one, so a positional `side_effect` list would make this
    harness depend on how many queries the policy happens to make today.
    """
    captured = MEASURED_AT - timedelta(hours=1)
    snaps = []
    for o in market.outcomes:
        s = MagicMock()
        s.outcome_id = o.id
        s.probability = o.current_probability
        s.captured_at = captured
        s.bookmaker = market.source
        snaps.append(s)

    market_result = MagicMock()
    market_result.scalar_one_or_none.return_value = market

    def _answer(*_a, **_k):
        r = MagicMock()
        r.all.return_value = []          # the withheld-price arms read rows
        r.scalars.return_value.all.return_value = snaps
        r.scalar_one_or_none.return_value = market
        return r

    calls = {"n": 0}

    async def _execute(*a, **k):
        calls["n"] += 1
        return market_result if calls["n"] == 1 else _answer()

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    with _at():
        return await get_probability_timeline(
            market_id=market.id, top=top, hours=168, db=db
        )


def _board(market):
    with _at():
        return {o["id"]: o for o in _format_market_detail(market, None, set())["outcomes"]}


def _row(resp, name):
    return next((o for o in resp["outcomes"] if o["name"] == name), None)


class TestTheTableEqualsTheBoard:
    """The ship, stated once and asserted three ways."""

    async def test_every_served_value_is_the_boards_value(self):
        market = _danube()
        resp = await _timeline(market)
        board = _board(_danube())

        for row in resp["outcomes"]:
            if row["name"] == "Field":
                continue
            served = board[row["id"]]
            assert row["current_probability"] == served["probability"], row["name"]
            assert row["probability_change_24h"] == served["probability_change_24h"]
            assert row["opening_probability"] == served["opening_probability"]
            assert row["name"] == served["name"]

    async def test_a_genuine_zero_reaches_the_table_as_zero_not_as_no_price(self):
        """#6081's class, on the site #7284 deleted.

        The table used to carry its own copy of the strict idiom
        (`float(o.current_probability) if o.current_probability is not None`).
        Delegating to `_format_market_detail` removed that copy — which lowered
        `test_every_served_site_uses_the_strict_form`'s count from 9 to 8 — so
        the behaviour is now INHERITED rather than restated, and inherited
        behaviour is exactly the kind that goes unnoticed when it breaks.

        `0.0` is falsy, so the whole defect is one token wide: the falsy form
        serves a real 0% as "no price". Asserted on BOTH sides, because equality
        with the board alone would be satisfied if both served `None`.
        """
        # The zeroed rung must be one the board KEEPS. Zeroing an expired window
        # (the Danube fixture has two) proves nothing: #7274 drops it before the
        # price is ever read, and the test fails with the row simply absent.
        zeroed = "Does not return by November 1, 2026"
        rows = [(i, n, 0.0 if n == zeroed else p) for i, n, p in DANUBE_ROWS]
        resp = await _timeline(_danube(rows))
        board = _board(_danube(rows))

        row = _row(resp, zeroed)
        assert row is not None, "the zero rung was dropped from the table entirely"
        served = board[row["id"]]

        assert served["probability"] == 0.0, (
            "the board itself served the zero rung as "
            f"{served['probability']!r} — this test's premise is gone and the "
            "inheritance claim below proves nothing"
        )
        assert row["current_probability"] == 0.0, (
            f"a genuine 0% reached the table as {row['current_probability']!r}; "
            "the falsy form is back on the timeline's side of the delegation"
        )

    async def test_the_table_does_not_list_a_row_the_board_dropped(self):
        """The Danube specimen: two rungs whose own deadline has passed."""
        resp = await _timeline(_danube())
        names = [o["name"] for o in resp["outcomes"]]
        assert "Before September 1, 2026" not in names, names
        assert "September 1 - 14, 2026" not in names, names
        assert len(names) == 3, names

    async def test_a_dropped_row_is_not_plotted_either(self):
        """Not just the legend — the lines, and the Field they would fall into."""
        resp = await _timeline(_danube())
        assert resp["timeline"]
        for entry in resp["timeline"]:
            assert "Before September 1, 2026" not in entry["outcomes"]
            assert "September 1 - 14, 2026" not in entry["outcomes"]

    async def test_the_legend_name_and_the_series_key_are_the_same_string(self):
        """The phone joins the table to the line BY NAME."""
        resp = await _timeline(_danube())
        table = {o["name"] for o in resp["outcomes"] if o["name"] != "Field"}
        plotted = set()
        for entry in resp["timeline"]:
            plotted |= set(entry["outcomes"]) - {"Field"}
        assert plotted <= table, f"a line nothing in the table can name: {plotted - table}"


class TestTheRefusalsTravelWithTheNumbers:
    def _squeezed(self):
        """A field summing 1.44 — inside the squeeze band, so the board scales it
        and #4079's scale ruling withholds every movement claim beside it."""
        return _market(
            [
                _outcome(1, "Alpha", 0.62, change=0.125, opening=0.50),
                _outcome(2, "Bravo", 0.48, change=-0.02, opening=0.40),
                _outcome(3, "Charlie", 0.34, change=0.01, opening=0.30),
            ],
            mid=999001,
        )

    async def test_a_squeezed_board_hands_the_table_the_squeezed_price(self):
        resp = await _timeline(self._squeezed())
        board = _board(self._squeezed())
        alpha = _row(resp, "Alpha")
        assert alpha["current_probability"] == board[1]["probability"]
        assert alpha["current_probability"] < 0.62, (
            "the table is still printing the raw price the ladder scaled"
        )

    async def test_a_squeezed_board_withholds_the_movement_on_the_table_too(self):
        """This is the +12.5 the reader saw: a raw delta beside a divided percent."""
        resp = await _timeline(self._squeezed())
        assert _row(resp, "Alpha")["probability_change_24h"] is None
        assert _row(resp, "Alpha")["opening_probability"] is None

    def _empty_book_board(self):
        """0.50 IS the midpoint of a 0.00/1.00 book, which is what makes the row
        a fabricated price rather than a longshot: the predicate tests the
        distance from the midpoint, not the bid alone."""
        return _market(
            [
                _outcome(1, "Quoted", 0.40, change=0.10),
                _outcome(2, "Empty book", 0.50, change=0.05, bid=0.0, ask=1.0),
            ],
            mid=999002,
            me=False,  # non-ME, so the squeeze is not a second cause of the null
        )

    async def test_a_withheld_price_reaches_the_table_as_a_refusal(self):
        """#7284's exact-score specimen printed a movement badge on exactly such
        a row — a price the ladder had already refused to publish."""
        resp = await _timeline(self._empty_book_board())
        empty = _row(resp, "Empty book")
        assert empty is not None, "the row itself is not dropped, only its price"
        assert empty["current_probability"] is None
        assert empty["probability_change_24h"] is None
        assert _row(resp, "Quoted")["current_probability"] == pytest.approx(0.40)


class TestTheFieldAndTheOrderAreOnTheSameScale:
    async def test_field_sums_the_boards_numbers(self):
        """`top=1` on the Danube board leaves two survivors in Field.

        Summed raw they are 0.4395; the board's numbers are the same here only
        because #7274 took the squeeze off this specimen — so the assertion is
        written against the board, not against a literal.
        """
        resp = await _timeline(_danube(), top=1)
        board = _board(_danube())
        field = _row(resp, "Field")
        expected = sum(
            board[i]["probability"] or 0.0
            for i in (2, 4)  # the two survivors outside the top 1
        )
        assert field["current_probability"] == pytest.approx(expected)

    async def test_the_table_is_ordered_by_the_number_it_prints(self):
        resp = await _timeline(_danube())
        printed = [
            o["current_probability"] or 0.0
            for o in resp["outcomes"]
            if o["name"] != "Field"
        ]
        assert printed == sorted(printed, reverse=True), printed


class TestWhatMustNotMove:
    async def test_the_history_is_not_rescaled(self):
        """Codex's ruling, kept visible: the plotted points are observations.

        The squeezed board's table prints ~0.43 for Alpha; the line keeps the
        0.62 that was actually observed. Dividing history by today's field sum
        would assert a displayed percent nobody ever saw.
        """
        market = _market(
            [
                _outcome(1, "Alpha", 0.62, change=0.125),
                _outcome(2, "Bravo", 0.48),
                _outcome(3, "Charlie", 0.34),
            ],
            mid=999003,
        )
        resp = await _timeline(market)
        plotted = [e["outcomes"].get("Alpha") for e in resp["timeline"]]
        assert plotted and all(p == pytest.approx(0.62) for p in plotted), plotted
        assert _row(resp, "Alpha")["current_probability"] < 0.62

    async def test_a_board_with_nothing_to_decide_serves_the_stored_price(self):
        """The control. Where the policy is a no-op the price is unchanged."""
        market = _market(
            [
                _outcome(1, "Yes", 0.62, change=0.04, opening=0.55),
                _outcome(2, "No", 0.38, change=-0.04, opening=0.45),
            ],
            mid=999004,
            me=False,  # non-ME, so no squeeze
        )
        resp = await _timeline(market)
        yes = _row(resp, "Yes")
        assert yes["current_probability"] == pytest.approx(0.62)
        assert yes["opening_probability"] == pytest.approx(0.55)

    async def test_the_per_write_delta_is_not_echoed_when_nothing_can_date_it(self):
        """#4079's rule, arriving here: a stored delta nobody can date is silent.

        The market above carries a real `probability_change_24h` of 0.04 and no
        bank, so the ladder says nothing about the day — and before this change
        the table said `+4.0%`. This is the 85.78% of rows #4079 measured, and
        it is the majority case, so it gets its own assertion rather than riding
        on the board-equality one.
        """
        market = _market(
            [_outcome(1, "Yes", 0.62, change=0.04), _outcome(2, "No", 0.38)],
            mid=999006,
            me=False,
        )
        resp = await _timeline(market)
        assert _row(resp, "Yes")["probability_change_24h"] is None

    async def test_a_dated_amount_does_travel(self):
        """…and the other side of it: where the bank CAN date the day, the table
        prints the dated amount, not the per-write delta.

        Without this the test above is satisfied by a reader that always says
        null, which would be a refusal rule rather than a shared basis.
        """
        from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

        basis_at = (MEASURED_AT - timedelta(hours=19)).strftime("%Y-%m-%dT%H:%M:%SZ")
        market = _market(
            [_outcome(1, "Yes", 0.62, change=0.04), _outcome(2, "No", 0.38)],
            mid=999007,
            me=False,
        )
        market.market_metadata = {DATED_BASIS_METADATA_KEY: {"1": [0.50, basis_at]}}
        resp = await _timeline(market)
        assert _row(resp, "Yes")["probability_change_24h"] == pytest.approx(0.12)

    async def test_identity_fields_still_come_off_the_row(self):
        """`rank`, `id` and the team enrichment are not display decisions."""
        row = _outcome(1, "Alpha", 0.62)
        row.rank = 3
        row.team_id = 77
        resp = await _timeline(_market([row, _outcome(2, "Bravo", 0.10)], mid=999005))
        alpha = _row(resp, "Alpha")
        assert alpha["id"] == 1
        assert alpha["rank"] == 3
        assert alpha["team_id"] == 77
