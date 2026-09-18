"""#6846 — an ask-only Kalshi leg inside a PROVED single-winner field is not a price.

WHAT A READER SAW. ``/futures/61056094`` ("2027 The Masters Champion") named Ryan
Gerard, Collin Morikawa, Jon Rahm and Bryson DeChambeau joint favourites at 39%,
Tiger Woods at 38%, over a field summing to 554% — while Scottie Scheffler
carried no price at all. Fourteen legs store ``yes_bid 0.0000 / yes_ask = the
served price / last_price 0.0000``: no bid, no trade, only an untaken offer.

The shipped ask-only rule missed them for exactly one reason —
``is_lone_ask_on_empty_book`` ends ``return yes_ask > ASK_ONLY_TRUSTED_MAX`` and
``ASK_ONLY_TRUSTED_MAX`` is 0.50, so 0.39 was served. This file guards the class:
inside a proved exhaustive single-winner partition the bound does not apply,
because an ask-only book states an UPPER BOUND and a field's column is read as a
distribution.

The specimen values below are the production rows, read 2026-09-18 from
``futures_markets.id = 61056094``.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    EXCLUSIVITY_PROVED_RELATIONS,
    market_is_proved_exclusive_field,
    needs_trade_evidence,
    price_is_unsupported,
)
from app.utils.kalshi_empty_book import (
    ASK_ONLY_TRUSTED_MAX,
    is_lone_ask_in_exclusive_field,
    is_lone_ask_on_empty_book,
)

#: The production shape verdict on the specimen market, verbatim from
#: ``market_metadata->'shape'``.
MASTERS_SHAPE = {
    "v": 2,
    "shape": "field",
    "evidence": [
        "exactly_one_structured",
        "expected_winners:1",
        "mutually_exclusive:true",
    ],
    "side_kind": "competitors",
    "confidence": "high",
    "exhaustive": True,
    "outcome_count": 51,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "classifier_version": 2,
}
MASTERS_METADATA = {"shape": MASTERS_SHAPE}

#: (name, current_probability, yes_bid, yes_ask, last_price) — the production rows.
ASK_ONLY_LEGS = [
    ("Collin Morikawa", 0.390, 0.0, 0.390, 0.0),
    ("Ryan Gerard", 0.390, 0.0, 0.390, 0.0),
    ("Bryson DeChambeau", 0.390, 0.0, 0.390, 0.0),
    ("Jon Rahm", 0.390, 0.0, 0.390, 0.0),
    ("Tiger Woods", 0.380, 0.0, 0.380, 0.0),
    ("Justin Thomas", 0.350, 0.0, 0.350, 0.0),
    ("Aaron Rai", 0.240, 0.0, 0.240, 0.0),
]

#: Legs with a REAL two-sided book. These must never be touched by this rule — and
#: Scheffler is the point of the whole issue: he is unpriced today *because* his
#: book is real, his 0.0010 bid excluding him from the ask-only arm entirely.
TWO_SIDED_LEGS = [
    ("Rory McIlroy", 0.2155, 0.0010, 0.430, 0.0),
    ("Wyndham Clark", 0.2150, 0.0100, 0.420, 0.0),
    ("Russell Henley", 0.1750, 0.0100, 0.340, 0.0),
    ("Joaquin Niemann", 0.1405, 0.0010, 0.280, 0.0),
    ("Scottie Scheffler", None, 0.0010, 0.500, 0.0),
]


class TestTheSpecimenIsWithheldOnlyInsideAField:
    """The 14 legs fall in the field frame and are served in the standalone frame."""

    @pytest.mark.parametrize("name,prob,bid,ask,last", ASK_ONLY_LEGS)
    def test_withheld_inside_a_proved_field(self, name, prob, bid, ask, last):
        assert price_is_unsupported(
            "kalshi",
            None,
            bid,
            ask,
            last,
            has_trade_evidence=True,
            in_exclusive_field=True,
        ), f"{name} at {ask} must not be served inside a proved single-winner field"

    @pytest.mark.parametrize("name,prob,bid,ask,last", ASK_ONLY_LEGS)
    def test_served_outside_a_field_exactly_as_today(self, name, prob, bid, ask, last):
        # The other half of the assertion, and the reason this file is not
        # vacuous: the SAME row, same predicate, the frame the only difference.
        # If the #6846 arm were reverted, the test above would return this answer.
        assert not price_is_unsupported(
            "kalshi", None, bid, ask, last, has_trade_evidence=True
        ), f"{name} is a standalone longshot line and that population is not spent here"

    @pytest.mark.parametrize("name,prob,bid,ask,last", TWO_SIDED_LEGS)
    def test_a_real_two_sided_book_is_never_touched(self, name, prob, bid, ask, last):
        for frame in (True, False):
            assert not price_is_unsupported(
                "kalshi",
                None,
                bid,
                ask,
                last,
                has_trade_evidence=True,
                in_exclusive_field=frame,
            ), f"{name} has a bid of {bid}; this rule is about books with none"

    def test_the_inversion_the_issue_names_is_gone(self):
        """No ask-only leg may outrank the best surviving two-sided leg."""
        survivors = [
            (name, prob)
            for name, prob, bid, ask, last in ASK_ONLY_LEGS + TWO_SIDED_LEGS
            if prob is not None
            and not price_is_unsupported(
                "kalshi",
                None,
                bid,
                ask,
                last,
                has_trade_evidence=True,
                in_exclusive_field=True,
            )
        ]
        assert survivors, "withholding everything would be a different defect"
        top_name, top_prob = max(survivors, key=lambda row: row[1])
        assert top_name == "Rory McIlroy"
        assert top_prob == pytest.approx(0.2155)
        # And the field no longer claims more than certainty from these rows.
        assert sum(prob for _, prob in survivors) < 1.0


class TestTheBoundIsTheOnlyThingThatMoves:
    """Everything else about the rule is identical in both frames."""

    def test_a_graded_row_is_exempt_in_a_field_too(self):
        # Settled means settled: withholding here would delete a result and
        # pre-empt the settled-language ship.
        assert not needs_trade_evidence(
            "kalshi", "api_settlement", 0.0, 0.39, in_exclusive_field=True
        )

    def test_polymarket_is_out_of_scope_in_a_field_too(self):
        assert not needs_trade_evidence(
            "polymarket", None, 0.0, 0.39, in_exclusive_field=True
        )

    def test_a_missing_bid_is_not_a_zero_bid_in_a_field_too(self):
        # None means "the poller never recorded a book", which is not evidence.
        assert not is_lone_ask_in_exclusive_field(None, 0.39, 0.0)
        assert not needs_trade_evidence(
            "kalshi", None, None, 0.39, in_exclusive_field=True
        )

    def test_a_real_trade_still_beats_the_book_in_a_field(self):
        # last_price > 0 is trade evidence; that is rule 2's territory and the
        # freshness question is a different ship.
        assert not is_lone_ask_in_exclusive_field(0.0, 0.39, 0.12)

    def test_absent_trade_evidence_still_fails_open_in_a_field(self):
        assert not price_is_unsupported(
            "kalshi",
            None,
            0.0,
            0.39,
            None,
            has_trade_evidence=False,
            in_exclusive_field=True,
        )

    def test_above_the_bound_both_frames_agree(self):
        # The shipped rule already refused these; the field frame must not
        # somehow acquit them.
        for frame in (True, False):
            assert price_is_unsupported(
                "kalshi",
                None,
                0.0,
                0.98,
                0.0,
                has_trade_evidence=True,
                in_exclusive_field=frame,
            )


class TestTheRefactorDidNotMoveTheShippedRule:
    """``is_lone_ask_on_empty_book`` is bound to the write side and must not drift."""

    @pytest.mark.parametrize(
        "bid,ask,last",
        [
            (None, 0.9, 0.0),
            (0.0, None, 0.0),
            (0.1, 0.9, 0.0),
            (0.0, 0.9, 0.5),
            (0.0, 0.9, 0.0),
            (0.0, 0.51, 0.0),
            (0.0, 0.50, 0.0),
            (0.0, 0.49, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 1.0, None),
            (0.0, 0.39, 0.0),
            (0.0, 0.01, 0.0),
        ],
    )
    def test_matches_the_pre_refactor_definition(self, bid, ask, last):
        def original(yes_bid, yes_ask, last_price):
            if yes_bid is None or yes_ask is None:
                return False
            if yes_bid > 0:
                return False
            if last_price is not None and last_price > 0:
                return False
            return yes_ask > ASK_ONLY_TRUSTED_MAX

        assert is_lone_ask_on_empty_book(bid, ask, last) is original(bid, ask, last)

    def test_the_field_form_is_a_strict_superset(self):
        for bid in (None, 0.0, 0.001, 0.1):
            for ask in (None, 0.0, 0.01, 0.39, 0.50, 0.51, 0.98, 1.0):
                for last in (None, 0.0, 0.3):
                    if is_lone_ask_on_empty_book(bid, ask, last):
                        assert is_lone_ask_in_exclusive_field(bid, ask, last), (
                            f"the field form must never acquit what the shipped "
                            f"rule refuses: {bid}/{ask}/{last}"
                        )

    def test_the_default_keeps_every_existing_caller_where_it_was(self):
        # No `last_price` dimension here, deliberately: `needs_trade_evidence`
        # takes no such argument — it is the cheap row-only screen, and the trade
        # term is `price_is_unsupported`'s. An earlier revision looped one anyway
        # and CodeQL called it (py/unused-loop-variable, "1 new alert including 1
        # error"): three identical assertions wearing a matrix's clothes.
        for bid in (None, 0.0, 0.001):
            for ask in (None, 0.39, 0.98):
                assert needs_trade_evidence("kalshi", None, bid, ask) is (
                    needs_trade_evidence(
                        "kalshi", None, bid, ask, in_exclusive_field=False
                    )
                )


class TestExclusivityIsProvedNotAssumed:
    """The gate reads the classifier's verdict, never the default-true column."""

    def test_the_specimen_market_passes(self):
        assert market_is_proved_exclusive_field("field", MASTERS_METADATA)

    @pytest.mark.parametrize(
        "market_type,metadata,why",
        [
            ("field", None, "no metadata at all"),
            ("field", {}, "no shape verdict"),
            ("field", {"shape": None}, "shape is null"),
            ("field", {"shape": "field"}, "shape is a string, not the verdict dict"),
            ("quantity", MASTERS_METADATA, "not a field market"),
            ("container_member", MASTERS_METADATA, "not a field market"),
            (
                "field",
                {"shape": {**MASTERS_SHAPE, "exhaustive": False}},
                "not exhaustive",
            ),
            (
                "field",
                {"shape": {**MASTERS_SHAPE, "exhaustive": None}},
                "exhaustive unproved",
            ),
            (
                "field",
                {"shape": {**MASTERS_SHAPE, "expected_winners": 3}},
                "Top-N, not one winner",
            ),
            (
                "field",
                {
                    "shape": {
                        **MASTERS_SHAPE,
                        "outcome_relation": "cumulative_thresholds",
                    }
                },
                "gotcha #17 co-winning ladder rungs",
            ),
            (
                "field",
                {
                    "shape": {
                        **MASTERS_SHAPE,
                        "outcome_relation": "independent_participation",
                    }
                },
                "independent binaries",
            ),
            (
                "field",
                {"shape": {**MASTERS_SHAPE, "outcome_relation": "unknown"}},
                "the classifier declined to resolve it",
            ),
        ],
    )
    def test_fails_closed(self, market_type, metadata, why):
        assert not market_is_proved_exclusive_field(market_type, metadata), why

    def test_jsonb_string_coercion(self):
        # Values can arrive from JSONB as native types or as strings.
        assert market_is_proved_exclusive_field(
            "field",
            {"shape": {**MASTERS_SHAPE, "exhaustive": "true", "expected_winners": "1"}},
        )

    def test_the_default_true_column_is_never_consulted(self):
        # `futures_markets.mutually_exclusive` defaults to TRUE and is set for
        # Yes/No claims and duels alike. A market carrying it with an unproved
        # shape must still fail.
        unproved = {"shape": {**MASTERS_SHAPE, "outcome_relation": "unknown"}}
        assert not market_is_proved_exclusive_field("field", unproved)


class TestTheLocalCopyDoesNotDriftFromTheCanonicalGate:
    """#6846's gate mirrors ``precompute_calibration.market_exclusivity_is_proved``.

    That helper cannot be imported on the futures serve path — it lives in a
    Celery task module the web dyno does not load, and D45 forbids this lane
    editing that file to lift the symbol out. So the two are pinned here
    instead, the way ``ASK_ONLY_TRUSTED_MAX`` is pinned to rule 3 by a test
    rather than by an import. A test can afford the import; a request cannot.
    """

    def test_the_relation_sets_are_identical(self):
        from app.tasks.precompute_calibration import (
            EXCLUSIVITY_PROVED_RELATIONS as CANONICAL,
        )

        assert EXCLUSIVITY_PROVED_RELATIONS == CANONICAL

    def test_the_verdicts_agree_across_the_matrix(self):
        from app.tasks.precompute_calibration import market_exclusivity_is_proved

        relations = [
            "competitors",
            "exclusive_ranges",
            "cumulative_thresholds",
            "independent_participation",
            "complements",
            "unknown",
            None,
        ]
        checked = 0
        for market_type in (
            "field",
            "quantity",
            "container_member",
            "participation",
            None,
        ):
            for exhaustive in (True, False, None, "true", "1"):
                for expected_winners in (1, 2, 3, None, "1"):
                    for relation in relations:
                        mine = market_is_proved_exclusive_field(
                            market_type,
                            {
                                "shape": {
                                    "exhaustive": exhaustive,
                                    "expected_winners": expected_winners,
                                    "outcome_relation": relation,
                                }
                            },
                        )
                        canonical = market_exclusivity_is_proved(
                            market_type, exhaustive, expected_winners, relation
                        )
                        assert mine is canonical, (
                            f"drift at {market_type}/{exhaustive}/"
                            f"{expected_winners}/{relation}: {mine} vs {canonical}"
                        )
                        checked += 1
        assert (
            checked == 875
        ), "the matrix shrank; a drift guard that checks less is not one"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.rows)


def _outcome(id, bid, ask, resolution_source=None):
    return SimpleNamespace(
        id=id,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
    )


@pytest.mark.asyncio
class TestTheRouteActuallyReachesTheSpecimen:
    """Every predicate above can be right while the ROUTE never asks them.

    The wiring is what a reader feels: the shape verdict has to be read off the
    market, once, and handed to BOTH the candidate screen and the verdict. A
    route that widened the screen but not the verdict would count these legs as
    candidates, pay for the snapshot query, and then serve them anyway.
    """

    @staticmethod
    async def _ids(outcomes, rows, *, metadata, market_type="field"):
        from app.routes.futures import _unsupported_price_outcome_ids

        market = SimpleNamespace(
            id=61056094,
            source="kalshi",
            outcomes=outcomes,
            market_type=market_type,
            market_metadata=metadata,
        )
        db = _FakeSession(rows)
        return await _unsupported_price_outcome_ids(db, market), db

    async def test_the_masters_legs_are_withheld_and_rory_survives(self):
        # Ryan Gerard and Tiger Woods: ask-only, no trade. Rory: a real bid.
        outcomes = [
            _outcome(1, 0.0, 0.390),
            _outcome(2, 0.0, 0.380),
            _outcome(3, 0.0010, 0.430),
        ]
        ids, db = await self._ids(
            outcomes, [(1, 0.0), (2, 0.0), (3, 0.0)], metadata=MASTERS_METADATA
        )
        assert ids == {1, 2}, "the two untaken offers fall, the real book stands"
        assert db.statements, "the field frame must reach the trade read"

    async def test_the_same_legs_on_an_unproved_market_are_untouched(self):
        # Same rows, same route, classifier declined to prove the partition.
        unproved = {"shape": {**MASTERS_SHAPE, "outcome_relation": "unknown"}}
        outcomes = [_outcome(1, 0.0, 0.390), _outcome(2, 0.0, 0.380)]
        ids, db = await self._ids(outcomes, [(1, 0.0), (2, 0.0)], metadata=unproved)
        assert ids == set(), "exclusivity is proved, never assumed"
        assert (
            not db.statements
        ), "and the screen is on the row, so an unproved market pays nothing"

    async def test_a_market_missing_its_shape_columns_fails_open(self):
        outcomes = [_outcome(1, 0.0, 0.390)]
        ids, _ = await self._ids(outcomes, [(1, 0.0)], metadata=None, market_type=None)
        assert ids == set()

    async def test_above_the_bound_still_falls_without_any_field_proof(self):
        # The shipped #5611 behaviour is untouched by this change.
        outcomes = [_outcome(1, 0.0, 0.98)]
        ids, _ = await self._ids(outcomes, [(1, 0.0)], metadata=None, market_type=None)
        assert ids == {1}

    async def test_a_graded_leg_in_a_proved_field_is_still_exempt(self):
        outcomes = [_outcome(1, 0.0, 0.390, resolution_source="api_settlement")]
        ids, db = await self._ids(outcomes, [(1, 0.0)], metadata=MASTERS_METADATA)
        assert ids == set(), "settled means settled; withholding would delete a result"
        assert not db.statements


class TestTheChartAndTheTableDoNotDisagree:
    """#6757's premise, one rule further on.

    Withholding the price from the ladder while the graph above it goes on
    drawing that same leg is the defect #5898 and #6757 both exist to prevent.
    On the specimen it is not hypothetical: the Probability Trend on
    ``/futures/61056094`` charts Collin Morikawa, Jon Rahm and Bryson DeChambeau
    — three of the fourteen — as a flat line at 39%.
    """

    @staticmethod
    def _snapshot(
        outcome_id, bookmaker="kalshi", prob=0.39, bid=0.0, ask=0.39, last=0.0
    ):
        return SimpleNamespace(
            outcome_id=outcome_id,
            bookmaker=bookmaker,
            probability=prob,
            yes_bid=bid,
            yes_ask=ask,
            last_price=last,
        )

    @staticmethod
    def _charted(id, bid, ask, resolution_source=None, is_winner=None):
        return SimpleNamespace(
            id=id,
            current_yes_bid=bid,
            current_yes_ask=ask,
            resolution_source=resolution_source,
            is_winner=is_winner,
        )

    def test_the_points_fall_with_the_row(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [self._charted(1, 0.0, 0.39), self._charted(2, 0.0010, 0.43)]
        snaps = [
            self._snapshot(1),
            self._snapshot(2, prob=0.2155, bid=0.0010, ask=0.43),
        ]
        kept = _drop_unsupported_snapshot_points(snaps, outcomes, {1, 2})
        assert [s.outcome_id for s in kept] == [
            2
        ], "the ask-only leg's points go with its price; the real book's stay"

    def test_without_the_field_verdict_every_point_survives(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [self._charted(1, 0.0, 0.39)]
        snaps = [self._snapshot(1)]
        assert len(_drop_unsupported_snapshot_points(snaps, outcomes)) == 1
        assert len(_drop_unsupported_snapshot_points(snaps, outcomes, set())) == 1

    def test_an_outcome_we_were_given_no_verdict_for_keeps_its_points(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [self._charted(1, 0.0, 0.39)]
        snaps = [self._snapshot(99)]
        assert len(_drop_unsupported_snapshot_points(snaps, outcomes, {1})) == 1

    def test_a_settled_series_is_shown_whole(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        # Settled means settled: the completed journey is drawn whole, which is
        # exactly why #6757's arm sits inside the grade branch.
        outcomes = [self._charted(1, 0.0, 0.39, resolution_source="api_settlement")]
        snaps = [self._snapshot(1)]
        assert len(_drop_unsupported_snapshot_points(snaps, outcomes, {1})) == 1

    def test_each_market_in_a_multi_chart_is_judged_on_its_own_shape(self):
        from app.routes.futures import _exclusive_field_outcome_ids

        proved = SimpleNamespace(
            market_type="field",
            market_metadata=MASTERS_METADATA,
            outcomes=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        )
        unproved = SimpleNamespace(
            market_type="field",
            market_metadata={"shape": {**MASTERS_SHAPE, "outcome_relation": "unknown"}},
            outcomes=[SimpleNamespace(id=3)],
        )
        assert _exclusive_field_outcome_ids([proved, unproved]) == {1, 2}

    def test_a_market_missing_its_columns_contributes_nothing(self):
        from app.routes.futures import _exclusive_field_outcome_ids

        bare = SimpleNamespace(outcomes=[SimpleNamespace(id=7)])
        assert _exclusive_field_outcome_ids([bare, None]) == set()
