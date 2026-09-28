"""A /politics card neither shrinks nor crowns a market whose legs can all be true — #9474.

Found at 390px on https://bainluck.com/politics, 2026-09-28 22:05Z:

    What cases will the Supreme Court agree to hear ...     (56775624)
        card:    Bird v. Iowa 35% · DOGE 32% · Norfolk 32%
        stored:  0.39 · 0.36 · 0.36          (`futures_outcomes`, 22:10Z)

`_market_row` handed every row to `_normalize_outcome_probs`, whose docstring
says "Only call this for MUTUALLY-EXCLUSIVE fields". The market is
`mutually_exclusive = false` — the court can take all three cases — so the top
three summing past 105 was never an over-round, and dividing by 111 printed
numbers no market quoted. The row now also carries the flag, so the card stops
labelling the top rung of a ladder "Leader" (57 of 68 cards that minute).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.politics import _market_row

NOW = datetime(2026, 9, 28, 22, 10, 0, tzinfo=timezone.utc)
STAMP = "2026-09-28T21:50:00+00:00"

# Production's ten priced legs of 56775624, read from `futures_outcomes` 22:10Z.
SCOTUS_CASES = [
    ("Bird v. Iowa Migrant Movement for Justice", 0.39),
    ("U.S. DOGE Service v. U.S. District Court", 0.36),
    ("Norfolk Southern Railway v. Mallory", 0.36),
    ("Republican National Committee v. Wetzel", 0.325),
    ("Pharmaceutical Research and Manufacturers v. McCuskey", 0.315),
    ("Roybal v. Griffith", 0.30),
    ("Buenrostro-Mendez v. Blanche", 0.205),
    ("Duncan v. Bonta", 0.165),
    ("Khalid Shaikh Mohammad v. United States", 0.125),
    ("Moylan v. Guam Society of Obstetricians", 0.125),
]
# A cumulative ladder from the same payload (59693681): nests, so not exclusive.
STUDENT_LOAN_CAP = [
    ("Before Jan 3, 2027", 0.105),
    ("Before Dec 12, 2026", 0.075),
    ("Before Oct 2, 2026", 0.045),
]


def _market(legs, mutually_exclusive="absent"):
    m = SimpleNamespace(
        id=56775624,
        name="What cases will the Supreme Court agree to hear in 2026?",
        source="kalshi",
        external_id="kx-test",
        outcomes=[
            SimpleNamespace(
                id=i + 1,
                name=n,
                current_probability=p,
                probability_change_24h=None,
                rank=None,
                last_updated=STAMP,
                is_winner=False,
            )
            for i, (n, p) in enumerate(legs)
        ],
    )
    if mutually_exclusive != "absent":
        m.mutually_exclusive = mutually_exclusive
    return m


def _probs(row):
    return [o["prob"] for o in row["top_outcomes"]]


class TestTheShip:
    def test_a_pick_several_market_prints_its_stored_prices(self):
        row = _market_row(_market(SCOTUS_CASES, False), now=NOW)
        assert _probs(row) == [39.0, 36.0, 36.0]
        assert row["prob"] == 39.0

    def test_the_row_says_the_legs_are_not_one_field(self):
        assert _market_row(_market(SCOTUS_CASES, False), now=NOW)["mutually_exclusive"] is False
        assert _market_row(_market(STUDENT_LOAN_CAP, False), now=NOW)["mutually_exclusive"] is False

    def test_a_ladder_under_105_is_unchanged(self):
        row = _market_row(_market(STUDENT_LOAN_CAP, False), now=NOW)
        assert _probs(row) == [10.5, 7.5, 4.5]


class TestControls:
    """The over-round removal is RIGHT for a one-winner field and must survive:
    the same three prices on an exclusive market are still divided by 111."""

    def test_a_one_winner_field_is_still_devigged(self):
        row = _market_row(_market(SCOTUS_CASES, True), now=NOW)
        assert _probs(row) == [35.1, 32.4, 32.4]
        assert row["mutually_exclusive"] is True

    def test_an_unstamped_row_keeps_todays_behaviour(self):
        """No attribute at all — an older carrier, and every fixture in the
        sibling suites — reads as `None` and is treated as today."""
        row = _market_row(_market(SCOTUS_CASES), now=NOW)
        assert _probs(row) == [35.1, 32.4, 32.4]
        assert row["mutually_exclusive"] is None

    def test_an_explicit_null_keeps_todays_behaviour(self):
        row = _market_row(_market(SCOTUS_CASES, None), now=NOW)
        assert _probs(row) == [35.1, 32.4, 32.4]


class TestTheDefectReproduces:
    """🔴 RED-FIRST: the pre-#9474 call, unconditional, over the same legs."""

    def test_the_old_call_printed_35_over_a_stored_39(self):
        from app.routes.politics import _normalize_outcome_probs

        top = [{"name": n, "prob": round(p * 100, 1)} for n, p in SCOTUS_CASES[:3]]
        _normalize_outcome_probs(top)
        assert [o["prob"] for o in top] == [35.1, 32.4, 32.4]
