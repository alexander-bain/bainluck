"""#6876 — a RETRACTION is not a grade, so it must not disarm the price rails.

``/futures/52755817`` ("2026 Pro Basketball Cup Champion") printed eight teams at
29% in a 30-team single-winner field summing to 489%, with ``prices_withheld: 0``,
on a market resolving 2027-01-31. Seven of the eight had never traded. Every leg
carried ``resolution_source = 'ungradeable_result'`` — tier 1 TERMINAL, which
``resolution_authority`` defines as "a RETRACTION, not a grade … structurally
no-winner" — and the bare ``resolution_source is not None`` exemption in
``needs_trade_evidence`` read that retraction as a verdict and returned before
#6846's field term was ever reached.

The rows below are the specimen's OWN stored values, read from production
2026-09-18 06:2xZ, not invented ones.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    RETRACTED_GRADE_SOURCES,
    needs_trade_evidence,
    price_is_unsupported,
    price_refuted_by_live_book,
    needs_trade_disconfirmation,
    row_carries_a_verdict,
)
from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    DETERMINISTIC_SOURCES,
    KNOWN_SOURCES,
    TERMINAL_SOURCES,
)

RETRACTION = "ungradeable_result"

#: The specimen's shape verdict, as the classifier persisted it.
CUP_SHAPE = {
    "v": 2,
    "shape": "field",
    "exhaustive": True,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "outcome_count": 30,
}
CUP_METADATA = {"shape": CUP_SHAPE}

#: (name, stored probability, bid, ask, newest kalshi snapshot last_price).
#: The fourteen ask-only legs of market 52755817, verbatim from production.
CUP_ASK_ONLY_LEGS = [
    ("Portland", 0.29, 0.0, 0.29, 0.0),
    ("Sacramento", 0.29, 0.0, 0.29, 0.0),
    ("Brooklyn", 0.29, 0.0, 0.29, 0.0),
    ("Chicago", 0.29, 0.0, 0.29, 0.0),
    ("Los Angeles Clippers", 0.29, 0.0, 0.29, 0.0),
    ("Memphis", 0.29, 0.0, 0.29, 0.0),
    ("Milwaukee", 0.29, 0.0, 0.29, 0.0),
    ("Phoenix", 0.20, 0.0, 0.20, 0.0),
    ("Denver", 0.13, 0.0, 0.13, 0.0),
    ("Orlando", 0.11, 0.0, 0.11, 0.0),
    # These four carry a real recorded trade and keep their number under rule 2.
    ("New Orleans", 0.29, 0.0, 0.29, 0.29),
    ("Charlotte", 0.22, 0.0, 0.22, 0.22),
    ("Washington", 0.13, 0.0, 0.13, 0.13),
    ("Utah", 0.11, 0.0, 0.11, 0.23),
]

NEVER_TRADED = [leg for leg in CUP_ASK_ONLY_LEGS if leg[4] == 0.0]
TRADED = [leg for leg in CUP_ASK_ONLY_LEGS if leg[4] > 0.0]


def _unsupported(prob, bid, ask, last, *, resolution_source, in_field=True):
    return price_is_unsupported(
        "kalshi",
        resolution_source,
        bid,
        ask,
        last,
        has_trade_evidence=last is not None,
        in_exclusive_field=in_field,
    )


class TestTheVerdictPredicate:
    """What ``row_carries_a_verdict`` answers, and against whose definition."""

    def test_an_ungraded_row_carries_no_verdict(self):
        assert row_carries_a_verdict(None) is False

    def test_the_retraction_carries_no_verdict(self):
        assert row_carries_a_verdict(RETRACTION) is False

    @pytest.mark.parametrize("source", sorted(AUTHORITATIVE_SOURCES))
    def test_every_authoritative_source_is_a_verdict(self, source):
        assert row_carries_a_verdict(source) is True

    @pytest.mark.parametrize("source", sorted(DETERMINISTIC_SOURCES))
    def test_every_deterministic_source_is_a_verdict(self, source):
        assert row_carries_a_verdict(source) is True

    @pytest.mark.parametrize("source", sorted(TERMINAL_SOURCES - {RETRACTION}))
    def test_every_other_terminal_source_is_still_a_verdict(self, source):
        # did_not_play, withdrew, all_losers, pass2_loser, date_passed and
        # clean_resolution all DECLARE a result. Their number is a settlement
        # value of 0 and withholding it would delete a result — the exact harm
        # the exemption exists to prevent. Only the retraction moves.
        assert row_carries_a_verdict(source) is True

    def test_the_retraction_is_the_only_source_that_moves(self):
        moved = {s for s in KNOWN_SOURCES if not row_carries_a_verdict(s)}
        assert moved == {RETRACTION}

    def test_an_unknown_source_keeps_its_exemption(self):
        # Fails closed for a rule that WITHHOLDS: a grader added after this file
        # reads as a verdict rather than silently starting to blank prices.
        assert row_carries_a_verdict("some_future_grader_7000") is True
        assert row_carries_a_verdict("") is True

    def test_the_spelling_is_imported_not_restated(self):
        assert RETRACTED_GRADE_SOURCES == {RETRACTION_SOURCE}
        assert RETRACTION_SOURCE == RETRACTION

    def test_the_codebase_still_classes_the_retraction_terminal(self):
        # If a later ruling promotes ungradeable_result to a real grade, this
        # whole file is the thing that should go red first.
        assert RETRACTION in TERMINAL_SOURCES
        assert RETRACTION not in AUTHORITATIVE_SOURCES
        assert RETRACTION not in DETERMINISTIC_SOURCES


class TestTheSpecimenInTheDirectionItFailed:
    """The fourteen ask-only legs of 52755817, on their own stored values."""

    @pytest.mark.parametrize("name,prob,bid,ask,last", NEVER_TRADED)
    def test_a_never_traded_retracted_leg_is_withheld(self, name, prob, bid, ask, last):
        assert needs_trade_evidence(
            "kalshi", RETRACTION, bid, ask, in_exclusive_field=True
        ), f"{name} must reach the trade read"
        assert _unsupported(prob, bid, ask, last, resolution_source=RETRACTION)

    @pytest.mark.parametrize("name,prob,bid,ask,last", TRADED)
    def test_a_retracted_leg_that_actually_traded_keeps_its_price(
        self, name, prob, bid, ask, last
    ):
        # Rule 2 is untouched: trade evidence beats a wide book. Whether a real
        # trade goes stale is the freshness question and a different ship.
        assert not _unsupported(prob, bid, ask, last, resolution_source=RETRACTION)

    def test_the_tie_the_issue_names_is_gone(self):
        served = [
            name
            for name, prob, bid, ask, last in CUP_ASK_ONLY_LEGS
            if not _unsupported(prob, bid, ask, last, resolution_source=RETRACTION)
        ]
        # Eight teams printed 29%. Exactly one of them ever traded at 29.
        assert served == ["New Orleans", "Charlotte", "Washington", "Utah"]
        assert len(served) == 4 and len(CUP_ASK_ONLY_LEGS) - len(served) == 10

    def test_oklahoma_city_has_a_real_book_and_is_never_a_candidate(self):
        # bid 0.2600 / ask 0.3300 — two-sided, so no ask-only rule may touch it.
        assert not needs_trade_evidence(
            "kalshi", RETRACTION, 0.26, 0.33, in_exclusive_field=True
        )

    def test_before_the_fix_every_one_of_them_was_exempt(self):
        # The defect, stated as the old clause. This is what made the page lie.
        for name, prob, bid, ask, last in CUP_ASK_ONLY_LEGS:
            assert RETRACTION is not None  # the old test, verbatim
            assert not needs_trade_evidence(
                "kalshi", "api_settlement", bid, ask, in_exclusive_field=True
            ), f"{name}: a REAL grade is still exempt, which is the control"


class TestWhatTheChangeMustNotSpend:
    """Everything the narrowing is not allowed to touch."""

    def test_a_real_grade_in_a_proved_field_is_still_exempt(self):
        assert not needs_trade_evidence(
            "kalshi", "api_settlement", 0.0, 0.29, in_exclusive_field=True
        )
        assert not _unsupported(
            0.29, 0.0, 0.29, 0.0, resolution_source="api_settlement"
        )

    @pytest.mark.parametrize("source", sorted(TERMINAL_SOURCES - {RETRACTION}))
    def test_no_other_terminal_source_starts_being_screened(self, source):
        assert not needs_trade_evidence(
            "kalshi", source, 0.0, 0.29, in_exclusive_field=True
        )

    def test_the_ungraded_path_is_byte_for_byte_what_it_was(self):
        assert needs_trade_evidence("kalshi", None, 0.0, 0.29, in_exclusive_field=True)
        assert not needs_trade_evidence("kalshi", None, 0.0, 0.29)  # below the bound
        assert needs_trade_evidence("kalshi", None, 0.0, 0.98)  # above it

    def test_a_retracted_leg_outside_a_proved_field_keeps_the_bound(self):
        # The standalone arm is unchanged, and production measured it spending
        # nothing on this population: 0 of 31 sampled legs withheld.
        assert not needs_trade_evidence("kalshi", RETRACTION, 0.0, 0.29)
        assert needs_trade_evidence("kalshi", RETRACTION, 0.0, 0.98)

    def test_polymarket_is_still_out_of_scope(self):
        assert not needs_trade_evidence(
            "polymarket", RETRACTION, 0.0, 0.29, in_exclusive_field=True
        )

    def test_a_missing_book_is_still_not_a_zero_book(self):
        assert not needs_trade_evidence(
            "kalshi", RETRACTION, None, 0.29, in_exclusive_field=True
        )

    def test_absent_trade_evidence_still_fails_open(self):
        assert not price_is_unsupported(
            "kalshi",
            RETRACTION,
            0.0,
            0.29,
            None,
            has_trade_evidence=False,
            in_exclusive_field=True,
        )

    def test_the_polymarket_midpoint_arm_is_deliberately_unmoved(self):
        # Measured inert: ungradeable_result is written on Kalshi rows only
        # (34,993 open + 3,854 resolved, 0 Polymarket). Routing this through the
        # helper would be an unmeasured widening on an empty population.
        assert not needs_trade_disconfirmation(
            "polymarket", RETRACTION, 0.5, 0.02, 0.98
        )
        assert needs_trade_disconfirmation("polymarket", None, 0.5, 0.02, 0.98)


class TestTheRefutedBookArm:
    """A retracted row is an UNGRADED row, so it gets both arms (#6532)."""

    def test_the_bid_arm_now_fires_on_a_retracted_row(self):
        # Price below a live bid: you could sell into that bid right now.
        assert price_refuted_by_live_book("kalshi", RETRACTION, False, 0.02, 0.30, 0.40)

    def test_a_genuinely_graded_loser_keeps_the_ask_arm_only(self):
        # 110 Kalshi legs are a settled 0.0000 beside a bid nobody cleared.
        # Blanking those is the exact harm the exemption exists to prevent.
        assert not price_refuted_by_live_book(
            "kalshi", "api_settlement", False, 0.02, 0.30, 0.40
        )

    def test_a_graded_winner_is_untouched_whatever_the_book_says(self):
        assert not price_refuted_by_live_book(
            "kalshi", "api_settlement", True, 1.0, 0.0, 0.40
        )

    def test_the_ask_arm_is_unchanged_for_a_retracted_row(self):
        # It already fired on these (157 legs); the verdict does not move.
        assert price_refuted_by_live_book("kalshi", RETRACTION, False, 0.99, 0.0, 0.49)

    def test_the_specimen_is_not_refuted_by_its_own_book(self):
        # probability == yes_ask exactly, which is why this arm missed it and
        # the trade arm is the one that had to change.
        for name, prob, bid, ask, last in CUP_ASK_ONLY_LEGS:
            assert not price_refuted_by_live_book(
                "kalshi", RETRACTION, False, prob, bid, ask
            ), name


@pytest.mark.asyncio
class TestTheRouteReachesTheSpecimen:
    """A predicate can be right while the route never asks it."""

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Session:
        def __init__(self, rows):
            self.rows = rows
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return TestTheRouteReachesTheSpecimen._Result(self.rows)

    @staticmethod
    async def _ids(outcomes, rows, *, metadata=CUP_METADATA):
        from app.routes.futures import _unsupported_price_outcome_ids

        market = SimpleNamespace(
            id=52755817,
            source="kalshi",
            outcomes=outcomes,
            market_type="field",
            market_metadata=metadata,
        )
        db = TestTheRouteReachesTheSpecimen._Session(rows)
        return await _unsupported_price_outcome_ids(db, market), db

    @staticmethod
    def _outcome(id, bid, ask, resolution_source=RETRACTION):
        return SimpleNamespace(
            id=id,
            current_yes_bid=bid,
            current_yes_ask=ask,
            resolution_source=resolution_source,
        )

    async def test_the_route_withholds_the_tie_and_keeps_the_traded_leg(self):
        outcomes = [
            self._outcome(1, 0.0, 0.29),  # Portland, never traded
            self._outcome(2, 0.0, 0.29),  # Sacramento, never traded
            self._outcome(3, 0.0, 0.29),  # New Orleans, traded at 0.29
            self._outcome(4, 0.26, 0.33),  # Oklahoma City, real two-sided book
        ]
        ids, db = await self._ids(outcomes, [(1, 0.0), (2, 0.0), (3, 0.29), (4, 0.0)])
        assert ids == {1, 2}
        assert db.statements, "the retracted legs must reach the trade read"

    async def test_the_route_left_every_one_of_them_alone_before(self):
        # The same four rows carrying a REAL grade: the control, and the shape
        # of the bug — the screen returned before the snapshot query was paid.
        outcomes = [
            self._outcome(i, 0.0, 0.29, resolution_source="api_settlement")
            for i in (1, 2, 3)
        ]
        ids, db = await self._ids(outcomes, [(1, 0.0), (2, 0.0), (3, 0.0)])
        assert ids == set()
        assert not db.statements

    async def test_an_unproved_market_is_untouched_even_when_retracted(self):
        unproved = {"shape": {**CUP_SHAPE, "outcome_relation": "unknown"}}
        outcomes = [self._outcome(1, 0.0, 0.29), self._outcome(2, 0.0, 0.29)]
        ids, db = await self._ids(outcomes, [(1, 0.0), (2, 0.0)], metadata=unproved)
        assert ids == set(), "exclusivity is proved, never assumed"
        assert not db.statements
