"""#2950 — /economics must not print a confident 0% for a market it holds no price for.

Alex's shop found `WTI Crude Oil (WTI) Up or Down on September 4?` rendering
**0%** on September 3rd. The market has no outcomes at all.

THE DEFECT.  ``_market_row`` opened ``prob = 0.0`` and gave that one name two
jobs — the running maximum, and the value returned when the loop never ran.
Its only refusal was ``len(outcomes) > 5``: too MANY outcomes.  It never
refused zero, so an outcome-less market fell through and its initialiser was
served as a measurement.

THE CENSUS THAT DECIDED THE FIX.  Four functions in this codebase turn a
market into a row.  Three already refuse an unpriced market, and **two of the
three are in the same file as the defect**:

    politics.py       _market_row           `if not outcomes: return None`   OK
    entertainment.py  _market_row           `if not outcomes: return None`   OK
    economics.py      _cross_source_row_fn  `if not outcomes: return None`   OK
    economics.py      _distribution_row     "Returns None when nothing is
                                             priced."                        OK
    economics.py      _market_row           neither                          <- the bug

``_distribution_row`` is the direct sibling: it handles the >5 half of the very
same arity split, and its docstring opens *"Render a multi-outcome market that
``_market_row`` refuses."*  The two halves of one branch disagreed about
whether an unpriced market is a row.

MEASURED, 2026-09-04, production, same minute on all three surfaces:

    /api/politics       68 rows   0 printing 0%
    /api/entertainment 105 rows   0 printing 0%
    /api/economics      58 rows   5 printing 0%     <- Aug Inflation US, Canada
                                                       unemployment, WTI weekly,
                                                       WTI Up-or-Down (x2 rows)

    open economics markets            2269
    carrying zero outcomes             175   (7.7%)  <- reachable by this fix
    with outcomes but all NULL-priced    0           <- guarded, currently inert

WHAT IS AND IS NOT A CONTROL HERE.  A *priced* zero is data — the market is
saying "no" — and must still render.  A NULL is the absence of data and must
not.  The tests that pin that distinction are green on both arms and are
labelled CONTROL.  The tests that pin the refusal are red on the parent and are
not.

Fixtures use ``Decimal``, not ``float``: ``current_probability`` is
``Numeric(7, 6)``, so production hands this function a ``Decimal`` (gotcha:
``Mapped[Optional[float]]`` describes intent, not runtime — #2554, #2710).  A
float fixture would silently not exercise the falsiness trap the fix turns on.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.routes.economics import _market_row

# ---------------------------------------------------------------------------
# Mock builders — same shape as tests/integration/test_route_economics.py
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars


def _outcome(name, probability, *, outcome_id=1, rank=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=rank,
    )


def _market(
    *, market_id=1, name="Will the event happen?", outcomes, external_id="kxmock"
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source="kalshi",
        category="news",
        llm_sport_category="economics",
        outcomes=outcomes,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# The specimen from the shop, reproduced with its real name and real emptiness.
def _wti_up_or_down():
    return _market(
        market_id=60124816,
        name="WTI Crude Oil (WTI) Up or Down on September 4?",
        external_id="kxwtiupdown-26sep04",
        outcomes=[],
    )


# ===========================================================================
# THE SHIP — red on the parent
# ===========================================================================


class TestAnUnpricedMarketIsNotARow:
    def test_a_market_with_no_outcomes_is_refused(self):
        """The reported specimen. Master returns a row reading 0.0."""
        assert _market_row(_wti_up_or_down()) is None

    def test_a_market_whose_every_outcome_is_unpriced_is_refused(self):
        """No instances in production today (measured 0 of 2269), but it reaches
        the same initialiser by a different road: `float(None or 0)` is 0.0."""
        m = _market(
            market_id=2,
            outcomes=[
                _outcome("Yes", None, outcome_id=20, rank=1),
                _outcome("No", None, outcome_id=21, rank=2),
            ],
        )
        assert _market_row(m) is None

    def test_the_returned_row_never_carries_the_initialiser(self):
        """Whatever this function returns, its `prob` came from an outcome.

        Stated as a property rather than a value so it survives the next
        rewrite: there is no sentinel left to be mistaken for a measurement.
        """
        for outcomes in (
            [],
            [_outcome("Yes", None, outcome_id=30)],
            [_outcome("Yes", None, outcome_id=31), _outcome("No", None, outcome_id=32)],
        ):
            row = _market_row(_market(market_id=3, outcomes=outcomes))
            assert row is None, f"{outcomes!r} produced {row!r}"

    def test_garbage_placeholder_outcomes_are_filtered_like_the_siblings(self):
        """Joins the file's own `_clean_outcomes` convention.

        NOT a control — it is red on the parent, because six raw outcomes trip
        the `> 5` gate before anything is filtered. Measured inert on today's
        data: 0 of 2269 open economics markets carry a garbage-named outcome,
        so this changes no rendered row right now. It is here so the four row
        builders cannot drift apart again.
        """
        m = _market(
            market_id=4,
            outcomes=[
                _outcome("Yes", Decimal("0.600000"), outcome_id=40, rank=1),
                _outcome("No", Decimal("0.400000"), outcome_id=41, rank=2),
                _outcome("Maybe", Decimal("0.100000"), outcome_id=42, rank=3),
                _outcome("Later", Decimal("0.100000"), outcome_id=43, rank=4),
                _outcome("Never", Decimal("0.100000"), outcome_id=44, rank=5),
                _outcome("Option A", Decimal("0.010000"), outcome_id=45, rank=6),
            ],
        )
        row = _market_row(m)
        assert row is not None, "the garbage placeholder should not count toward arity"
        assert row["prob"] == 60.0


class TestTheRouteDoesNotServeTheZero:
    async def test_the_outcomeless_market_is_absent_from_the_payload(
        self, client, mock_db
    ):
        """Asserted on the served body, not the helper.

        A helper-only guard stays green if someone deletes the call; this drives
        `GET /api/economics` and looks for the market by id.
        """
        mock_db.execute.return_value = _MockResult([_wti_up_or_down()])
        body = (await client.get("/api/economics")).json()

        ids = _all_market_ids(body)
        assert 60124816 not in ids, (
            "the outcome-less market reached the payload; "
            f"rows served: {_all_rows(body)!r}"
        )

    async def test_no_row_anywhere_in_the_payload_reads_zero(self, client, mock_db):
        """The user-visible claim, stated over the whole document."""
        mock_db.execute.return_value = _MockResult([_wti_up_or_down()])
        body = (await client.get("/api/economics")).json()

        zeros = [r for r in _all_rows(body) if r.get("prob") == 0]
        assert zeros == [], f"rows printing a confident 0%: {zeros!r}"


# ===========================================================================
# CONTROLS — green on the parent too. These are what stop the fix from
# becoming "drop anything that computes to zero".
# ===========================================================================


class TestControls:
    def test_CONTROL_a_normal_binary_market_still_renders(self):
        m = _market(
            market_id=5,
            outcomes=[
                _outcome("Yes", Decimal("0.550000"), outcome_id=50, rank=1),
                _outcome("No", Decimal("0.450000"), outcome_id=51, rank=2),
            ],
        )
        row = _market_row(m)
        assert row is not None and row["prob"] == 55.0

    def test_CONTROL_a_priced_zero_is_data_and_still_renders(self):
        """`Decimal("0.000000")` is FALSY, which is why the old `or 0` could not
        tell it from a NULL. A market that says "no" is answering the question;
        it must keep its row and print 0%."""
        m = _market(
            market_id=6,
            outcomes=[
                _outcome("Yes", Decimal("0.000000"), outcome_id=60, rank=1),
                _outcome("No", Decimal("1.000000"), outcome_id=61, rank=2),
            ],
        )
        row = _market_row(m)
        assert row is not None and row["prob"] == 100.0

    def test_CONTROL_an_all_zero_market_still_renders_its_zero(self):
        """Every side priced, every side at zero. Nothing is missing here — the
        book is just empty of belief — so the row stays and reads 0%. This is
        the case a naive "refuse if prob == 0" fix would delete."""
        m = _market(
            market_id=7,
            outcomes=[
                _outcome("Yes", Decimal("0.000000"), outcome_id=70, rank=1),
                _outcome("No", Decimal("0.000000"), outcome_id=71, rank=2),
            ],
        )
        row = _market_row(m)
        assert row is not None and row["prob"] == 0.0

    def test_CONTROL_one_priced_side_beside_a_null_side_still_renders(self):
        m = _market(
            market_id=8,
            outcomes=[
                _outcome("Yes", Decimal("0.730000"), outcome_id=80, rank=1),
                _outcome("No", None, outcome_id=81, rank=2),
            ],
        )
        row = _market_row(m)
        assert row is not None and row["prob"] == 73.0

    def test_CONTROL_more_than_five_outcomes_is_still_refused(self):
        """The arity refusal is untouched — `_distribution_row` owns that half."""
        m = _market(
            market_id=9,
            outcomes=[
                _outcome(f"Bucket {i}", Decimal("0.100000"), outcome_id=90 + i, rank=i)
                for i in range(6)
            ],
        )
        assert _market_row(m) is None

    def test_CONTROL_the_row_keeps_its_shape(self):
        m = _market(
            market_id=11,
            outcomes=[_outcome("Yes", Decimal("0.420000"), outcome_id=110, rank=1)],
        )
        row = _market_row(m)
        assert set(row.keys()) == {"q", "prob", "src", "delta", "market_id"}
        assert row["market_id"] == 11
        assert row["delta"] is None


# ---------------------------------------------------------------------------
# Extractors — they report their own yield rather than returning quietly.
# ---------------------------------------------------------------------------


def _all_rows(body: dict) -> list[dict]:
    """Every market-shaped row anywhere in the payload.

    A row is `{q, prob, ...}`. Walking the whole document rather than naming a
    theme means a row that moves between sections cannot escape the assertion.
    """
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if "q" in node and "prob" in node:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(body)
    return found


def _all_market_ids(body: dict) -> set:
    return {
        r.get("market_id") for r in _all_rows(body) if r.get("market_id") is not None
    }


def test_the_extractor_can_see_a_row_at_all():
    """Guards the guard.

    Both route tests above assert an ABSENCE, and an extractor that finds
    nothing would make them pass for the wrong reason (ux/1040's lesson #4).
    This pins that `_all_rows` does find a row in a document shaped like the
    real payload.
    """
    doc = {
        "themes": {
            "energy": {
                "side_markets": [
                    {"q": "Will oil top $100?", "prob": 12.0, "market_id": 1},
                    {"q": "Will gas fall?", "prob": 0.0, "market_id": 2},
                ]
            }
        }
    }
    rows = _all_rows(doc)
    assert len(rows) == 2
    assert _all_market_ids(doc) == {1, 2}
    assert [r for r in rows if r["prob"] == 0] == [rows[1]]
