"""The capture's correctness suite: every non-affirmative shape must REFUSE.

Queue 389 Item 1 (#2077), constraint (a). The organising idea is that a passing
test here is worth very little on its own — a classifier that returned
``AMBIGUOUS_EMPTY`` for literally every input would pass most of the negative
controls. So the suite is built in two halves that can only both pass if the
classifier is actually discriminating:

* **Positive arms** prove each source's settled shape IS recognised.
* **Negative controls** prove that every OTHER shape — and in particular every
  shape that is byte-similar to a settlement — is refused, by name.

The `_ALL_NON_SETTLED_SHAPES` sweep is the load-bearing one: it asserts the
structural invariant across every shape at once, so a future branch added to the
classifier cannot quietly acquire the ability to settle without appearing here.
"""

from __future__ import annotations

import json

import pytest

from app.utils.settlement_truth import (
    CANDIDATE_REASONS,
    Disposition,
    ProbeOutcome,
    SettlementClaim,
    UnverifiedGradingRefused,
    assert_grading_licensed,
    classify_kalshi,
    classify_polymarket,
)


# ---------------------------------------------------------------------------
# The structural invariant: a claim cannot exist without its licence
# ---------------------------------------------------------------------------


class TestOutcomeInvariant:
    """``ProbeOutcome`` must make the bad state UNREPRESENTABLE, not merely unused."""

    def test_settled_requires_a_claim(self):
        with pytest.raises(ValueError, match="must carry a SettlementClaim"):
            ProbeOutcome(Disposition.SETTLED)

    @pytest.mark.parametrize(
        "disposition",
        [d for d in list(Disposition) if d is not Disposition.SETTLED],
    )
    def test_no_other_disposition_may_carry_a_claim(self, disposition):
        """The whole of constraint (a) in one assertion.

        If this ever passes for some disposition, the capture can persist a
        settlement it was not licensed to have — which is the manufactured-fact
        failure the module exists to prevent.
        """
        with pytest.raises(ValueError, match="only SETTLED may carry a claim"):
            ProbeOutcome(
                disposition,
                claim=SettlementClaim(winning_outcome="Yes", channel="test"),
            )

    def test_licenses_grading_is_exactly_settled(self):
        licensed = [d for d in list(Disposition) if d.licenses_grading()]
        assert licensed == [Disposition.SETTLED]

    def test_purged_is_not_a_source_claim_about_the_market(self):
        """PURGED is true, and it is about RETENTION — not about the market.

        A sweep that counted it as market knowledge would report the retention
        cliff as coverage.
        """
        assert Disposition.PURGED.is_source_claim() is False
        assert Disposition.SETTLED.is_source_claim() is True
        assert Disposition.OPEN_NO_SETTLEMENT.is_source_claim() is True

    def test_purged_is_not_retryable_but_the_non_facts_are(self):
        """Retrying the already-dead forever is the CAL-P009 starvation shape."""
        assert Disposition.PURGED.is_retryable() is False
        assert Disposition.NOT_FOUND.is_retryable() is False
        for d in (
            Disposition.AMBIGUOUS_EMPTY,
            Disposition.RATE_LIMITED,
            Disposition.TRANSPORT_ERROR,
        ):
            assert d.is_retryable() is True


# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------


class TestKalshiPositive:
    def test_settled_market_yields_the_result_verbatim(self):
        out = classify_kalshi(200, {"market": {"result": "Sevilla", "status": "settled"}})
        assert out.disposition is Disposition.SETTLED
        assert out.claim is not None
        assert out.claim.winning_outcome == "Sevilla"
        assert out.claim.channel == "kalshi_market"
        assert ("kalshi_market", 200) in out.channels

    def test_a_bare_market_body_without_the_wrapper_still_parses(self):
        out = classify_kalshi(200, {"result": "Yes", "status": "settled"})
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "Yes"


class TestKalshiNegativeControls:
    """Each of these is a shape that a naive reader turns into a fact."""

    def test_open_market_is_a_real_claim_not_an_error(self):
        out = classify_kalshi(200, {"market": {"result": "", "status": "active"}})
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert out.claim is None
        assert out.disposition.is_source_claim() is True
        assert out.disposition.is_retryable() is False

    @pytest.mark.parametrize("result", ["void", "cancelled", "no_result", "  "])
    def test_non_result_strings_are_never_settlements(self, result):
        """`result: "void"` is truthy. A `if result:` check settles on it."""
        out = classify_kalshi(200, {"market": {"result": result, "status": "settled"}})
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert out.claim is None

    def test_event_with_empty_markets_is_PURGED_not_no_settlement(self):
        """THE CLIFF (gotcha #35/#53): 200 + `markets: []` is a retention fact."""
        out = classify_kalshi(404, None, event_status=200, event_body={"markets": []})
        assert out.disposition is Disposition.PURGED
        assert out.claim is None
        assert "unknowable rather than absent" in out.reason

    def test_market_404_without_consulting_the_event_refuses_to_conclude(self):
        """A bare 404 is unattributable — our bad ticker or Kalshi's retention."""
        out = classify_kalshi(404, None)
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert "cannot distinguish" in out.reason

    def test_both_404_is_NOT_FOUND_and_routes_to_us(self):
        out = classify_kalshi(404, None, event_status=404, event_body=None)
        assert out.disposition is Disposition.NOT_FOUND
        assert "our external_id" in out.reason

    def test_market_404_but_event_still_lists_markets_is_ambiguous(self):
        out = classify_kalshi(
            404, None, event_status=200, event_body={"markets": [{"ticker": "X"}]}
        )
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY

    @pytest.mark.parametrize("status", [429, 500, 502, 503, -1])
    def test_transport_failures_are_never_facts(self, status):
        out = classify_kalshi(status, None)
        assert out.disposition in (
            Disposition.RATE_LIMITED,
            Disposition.TRANSPORT_ERROR,
        )
        assert out.disposition.is_source_claim() is False
        assert out.disposition.is_retryable() is True

    def test_429_on_the_event_leg_does_not_become_purged(self):
        """gotcha #36: a rate limit that reads as 'not found' is the classic bug."""
        out = classify_kalshi(404, None, event_status=429, event_body=None)
        assert out.disposition is Disposition.RATE_LIMITED

    def test_200_with_an_unparseable_body_is_a_transport_error(self):
        out = classify_kalshi(200, {"market": "not-a-dict"})
        assert out.disposition is Disposition.TRANSPORT_ERROR


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------


class TestPolymarketPositive:
    def test_gamma_decided_prices_pick_the_second_outcome(self):
        out = classify_polymarket(
            200,
            [{"outcomePrices": ["0", "1"], "outcomes": ["ARETE", "T1 Academy"]}],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "T1 Academy"

    def test_gamma_decided_prices_pick_the_first_outcome(self):
        out = classify_polymarket(
            200,
            [{"outcomePrices": ["1", "0"], "outcomes": ["Hanwha", "Doosan"]}],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "Hanwha"

    def test_gamma_returns_these_fields_as_json_STRINGS_in_production(self):
        """Gamma serialises both arrays as strings; a list-only parser sees nothing."""
        out = classify_polymarket(
            200,
            [
                {
                    "outcomePrices": json.dumps(["0", "1"]),
                    "outcomes": json.dumps(["A", "B"]),
                }
            ],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "B"

    def test_clob_settles_what_gamma_has_aged_out(self):
        """The independent second channel — #989/L2-32's recovered-404 population."""
        out = classify_polymarket(
            200,
            [],
            clob_status=200,
            clob_body={
                "closed": True,
                "tokens": [
                    {"outcome": "Yes", "winner": False},
                    {"outcome": "No", "winner": True},
                ],
            },
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "No"
        assert out.claim.channel == "clob"


class TestPolymarketDegradedForms:
    """C-DEGRADED-FORM-1's finalized rules, adopted verbatim (2026-08-21).

    The no-cliff relief is only real if the degraded forms still yield a winner
    determination, so these are the tests that decide whether 250,526 markets are
    recoverable or merely reachable.
    """

    def test_the_worst_observed_spread_resolves_cleanly(self):
        """1.16e-06 — the worst the census found, three orders inside the rule."""
        out = classify_polymarket(
            200,
            [{"outcomePrices": ["0.00000116", "0.99999884"], "outcomes": ["No", "Yes"]}],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "Yes"
        assert out.claim.evidence["form"] == "near"

    def test_the_documented_near_form_specimen(self):
        out = classify_polymarket(
            200,
            [{"outcomePrices": ["0.0000005", "0.9999945"], "outcomes": ["A", "B"]}],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "B"

    def test_near_form_works_in_the_other_direction(self):
        out = classify_polymarket(
            200,
            [{"outcomePrices": ["0.9999945", "0.0000005"], "outcomes": ["A", "B"]}],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "A"

    @pytest.mark.parametrize(
        "prices",
        [
            ["0.001", "0.999"],    # exactly AT the threshold — not below it
            ["0.01", "0.99"],      # an order of magnitude out
            ["0.4", "0.6"],
            ["0.5", "0.5"],
        ],
    )
    def test_prices_outside_the_rule_are_never_settled(self, prices):
        """The threshold is `< 0.001`. `<=` would widen it on the boundary row."""
        out = classify_polymarket(200, [{"outcomePrices": prices, "outcomes": ["A", "B"], "closed": False}])
        assert out.disposition is not Disposition.SETTLED
        assert out.claim is None

    def test_two_tiny_prices_are_malformed_not_decided(self):
        """A guard ADDED beyond the adopted rule, and flagged as such.

        ``min(price) < 0.001`` alone is satisfied by ``["0.0000001","0.0000002"]``,
        which is not a decided market in any reading. Refusing costs nothing;
        emitting would manufacture a winner from a malformed body.
        """
        out = classify_polymarket(
            200, [{"outcomePrices": ["0.0000001", "0.0000002"], "outcomes": ["A", "B"], "closed": True}]
        )
        assert out.disposition is not Disposition.SETTLED
        assert out.claim is None

    def test_the_no_resolved_class_is_PERMANENTLY_undeterminable(self):
        """~8k markets, all 365+ days: closed, held, and carrying no price field.

        It must not read as ambiguity — ambiguity implies a retry that will never
        pay, and it would keep 8k unpayable rows inside the recoverable denominator.
        """
        out = classify_polymarket(200, [{"outcomes": ["A", "B"], "closed": True}])
        assert out.disposition is Disposition.PRICE_UNDETERMINABLE
        assert out.disposition.is_retryable() is False
        assert out.disposition.licenses_grading() is False
        assert out.claim is None

    def test_closed_WITH_an_undecided_price_field_stays_merely_ambiguous(self):
        """The distinction the ~8k count depends on: absent field vs undecided value."""
        out = classify_polymarket(
            200, [{"outcomePrices": ["0.5", "0.5"], "outcomes": ["A", "B"], "closed": True}]
        )
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert out.disposition.is_retryable() is True

    def test_an_empty_price_LIST_counts_as_no_price_field(self):
        out = classify_polymarket(200, [{"outcomePrices": [], "outcomes": ["A", "B"], "closed": True}])
        assert out.disposition is Disposition.PRICE_UNDETERMINABLE

    def test_gamma_serialises_near_form_prices_as_strings_too(self):
        out = classify_polymarket(
            200,
            [
                {
                    "outcomePrices": json.dumps(["0.0000005", "0.9999945"]),
                    "outcomes": json.dumps(["A", "B"]),
                }
            ],
        )
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "B"


class TestPolymarketNegativeControls:
    def test_the_empty_200_is_refused_by_name(self):
        """gotcha #53's canonical specimen. `200 []` is a SHAPE, not an absence."""
        out = classify_polymarket(200, [])
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert out.claim is None
        assert "cannot distinguish" in out.reason

    def test_undecided_prices_are_not_a_settlement(self):
        out = classify_polymarket(
            200, [{"outcomePrices": ["0.5", "0.5"], "outcomes": ["A", "B"], "closed": False}]
        )
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert out.claim is None

    def test_closed_without_decided_prices_is_ambiguous_not_open(self):
        """This is #2077's own specimen: resolved, 0.5/0.5, no winner anywhere."""
        out = classify_polymarket(
            200, [{"outcomePrices": ["0.5", "0.5"], "outcomes": ["Over", "Under"], "closed": True}]
        )
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert out.claim is None

    def test_two_winning_tokens_is_refused_rather_than_picked(self):
        out = classify_polymarket(
            200,
            [],
            clob_status=200,
            clob_body={
                "tokens": [
                    {"outcome": "Yes", "winner": True},
                    {"outcome": "No", "winner": True},
                ]
            },
        )
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert "2 winning tokens" in out.reason

    def test_closed_clob_with_no_winner_token_is_ambiguous(self):
        out = classify_polymarket(
            200,
            [],
            clob_status=200,
            clob_body={"closed": True, "tokens": [{"outcome": "Yes", "winner": False}]},
        )
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY

    def test_not_found_requires_BOTH_stores_to_deny_it(self):
        out = classify_polymarket(200, [], clob_status=404, clob_body=None)
        assert out.disposition is Disposition.NOT_FOUND
        assert "both stores" in out.reason

    @pytest.mark.parametrize("status", [429, 500, 503, -1])
    def test_gamma_transport_failures_are_never_facts(self, status):
        out = classify_polymarket(status, None)
        assert out.disposition.is_source_claim() is False
        assert out.disposition.is_retryable() is True

    def test_a_clob_429_does_not_downgrade_to_not_found(self):
        """The gotcha #36 shape on the corroborating leg."""
        out = classify_polymarket(200, [], clob_status=429, clob_body=None)
        assert out.disposition is Disposition.RATE_LIMITED
        assert out.disposition is not Disposition.NOT_FOUND


# ---------------------------------------------------------------------------
# The cross-shape sweep — the assertion a new branch cannot dodge
# ---------------------------------------------------------------------------

#: Shapes in which the source told us NOTHING about the market — because the body
#: could not distinguish absence from emptiness, or because the transport failed.
#: These may not produce a settlement AND may not produce a claim about the market
#: at all. Kept separate from ``_ALL_NON_SETTLED_SHAPES`` because the weaker
#: assertion (``is not SETTLED``) does not catch a classifier that downgrades an
#: unattributable body to ``OPEN_NO_SETTLEMENT`` — which is still a manufactured
#: fact, just a quieter one. A mutation that made gamma's empty 200 read as
#: "no settlement" passed the sweep below and was caught only here.
_NO_KNOWLEDGE_SHAPES = [
    ("kalshi_bare_404", lambda: classify_kalshi(404, None)),
    ("kalshi_event_lists_markets", lambda: classify_kalshi(404, None, 200, {"markets": [{"t": "X"}]})),
    ("kalshi_429", lambda: classify_kalshi(429, None)),
    ("kalshi_500", lambda: classify_kalshi(500, None)),
    ("kalshi_event_429", lambda: classify_kalshi(404, None, 429, None)),
    ("kalshi_garbage_body", lambda: classify_kalshi(200, {"market": "x"})),
    ("gamma_empty_200", lambda: classify_polymarket(200, [])),
    ("gamma_429", lambda: classify_polymarket(429, None)),
    ("gamma_500", lambda: classify_polymarket(500, None)),
    ("clob_429", lambda: classify_polymarket(200, [], 429, None)),
    (
        "gamma_closed_no_prices",
        lambda: classify_polymarket(200, [{"outcomes": ["A", "B"], "closed": True}]),
    ),
    (
        "clob_two_winners",
        lambda: classify_polymarket(
            200, [], 200, {"tokens": [{"outcome": "A", "winner": True}, {"outcome": "B", "winner": True}]}
        ),
    ),
]


@pytest.mark.parametrize(
    "label,shape", _NO_KNOWLEDGE_SHAPES, ids=[s[0] for s in _NO_KNOWLEDGE_SHAPES]
)
def test_an_unattributable_body_yields_no_claim_about_the_market(label, shape):
    """The strong form of constraint (a).

    "The source says there is no settlement" is a FACT. An empty 200, a bare 404
    and a timeout are not that fact — they are the absence of an answer. A
    classifier that reports them as ``OPEN_NO_SETTLEMENT`` has invented market
    knowledge out of transport behaviour, which is exactly #683's ten-week failure
    in miniature.
    """
    out = shape()
    assert not out.disposition.is_source_claim(), (
        f"{label} produced {out.disposition.value} — a claim ABOUT THE MARKET from "
        f"a body that carries no knowledge of it"
    )


#: Every non-settled shape either classifier can produce, as (label, callable).
_ALL_NON_SETTLED_SHAPES = [
    ("kalshi_open", lambda: classify_kalshi(200, {"market": {"result": ""}})),
    ("kalshi_void", lambda: classify_kalshi(200, {"market": {"result": "void"}})),
    ("kalshi_bare_404", lambda: classify_kalshi(404, None)),
    ("kalshi_purged", lambda: classify_kalshi(404, None, 200, {"markets": []})),
    ("kalshi_not_found", lambda: classify_kalshi(404, None, 404, None)),
    ("kalshi_429", lambda: classify_kalshi(429, None)),
    ("kalshi_500", lambda: classify_kalshi(500, None)),
    ("kalshi_event_429", lambda: classify_kalshi(404, None, 429, None)),
    ("kalshi_garbage", lambda: classify_kalshi(200, {"market": "x"})),
    ("gamma_empty_200", lambda: classify_polymarket(200, [])),
    (
        "gamma_undecided",
        lambda: classify_polymarket(200, [{"outcomePrices": ["0.4", "0.6"], "outcomes": ["A", "B"]}]),
    ),
    (
        "gamma_closed_no_prices",
        lambda: classify_polymarket(200, [{"outcomes": ["A", "B"], "closed": True}]),
    ),
    ("gamma_404", lambda: classify_polymarket(404, None)),
    ("gamma_429", lambda: classify_polymarket(429, None)),
    ("gamma_500", lambda: classify_polymarket(500, None)),
    ("clob_429", lambda: classify_polymarket(200, [], 429, None)),
    ("clob_404", lambda: classify_polymarket(200, [], 404, None)),
    (
        "clob_two_winners",
        lambda: classify_polymarket(
            200, [], 200, {"tokens": [{"outcome": "A", "winner": True}, {"outcome": "B", "winner": True}]}
        ),
    ),
    (
        "gamma_no_resolved",
        lambda: classify_polymarket(200, [{"outcomes": ["A", "B"], "closed": True}]),
    ),
    (
        "gamma_near_form_boundary",
        lambda: classify_polymarket(
            200, [{"outcomePrices": ["0.001", "0.999"], "outcomes": ["A", "B"]}]
        ),
    ),
    (
        "gamma_two_tiny_prices",
        lambda: classify_polymarket(
            200, [{"outcomePrices": ["0.0000001", "0.0000002"], "outcomes": ["A", "B"], "closed": True}]
        ),
    ),
]


@pytest.mark.parametrize("label,shape", _ALL_NON_SETTLED_SHAPES, ids=[s[0] for s in _ALL_NON_SETTLED_SHAPES])
def test_no_non_affirmative_shape_ever_produces_a_settlement(label, shape):
    """The acceptance criterion for queue 389 Item 1, as one sweep.

    Every shape above is a real body one of our two sources returns. None of them
    is an affirmative settlement, so none may produce one — and none may carry a
    claim, which is the thing the writer persists.
    """
    out = shape()
    assert out.disposition is not Disposition.SETTLED, f"{label} manufactured a settlement"
    assert out.claim is None, f"{label} carried a claim without a licence"
    assert not out.disposition.licenses_grading(), f"{label} licensed a grading write"


@pytest.mark.parametrize("label,shape", _ALL_NON_SETTLED_SHAPES, ids=[s[0] for s in _ALL_NON_SETTLED_SHAPES])
def test_every_non_settled_shape_explains_itself(label, shape):
    """A disposition with no reason is a row a human cannot triage."""
    out = shape()
    assert out.reason.strip(), f"{label} recorded no reason"
    assert out.channels, f"{label} recorded no channel provenance"


def test_every_disposition_is_exercised_by_the_sweep_or_the_positive_arms():
    """Coverage of the VOCABULARY, so a new disposition cannot land untested.

    ``NOT_PROBED_BEYOND_HORIZON`` is produced by the sweep (budget policy), not by
    a classifier, so it is excluded here and asserted in the sweep's own suite.
    """
    seen = {shape().disposition for _, shape in _ALL_NON_SETTLED_SHAPES}
    seen.add(Disposition.SETTLED)
    expected = set(list(Disposition)) - {Disposition.NOT_PROBED_BEYOND_HORIZON}
    assert seen == expected, f"unexercised dispositions: {expected - seen}"


# ---------------------------------------------------------------------------
# Constraint (b) — the candidate pool never grades
# ---------------------------------------------------------------------------


class TestCandidatePoolNeverGrades:
    def test_scores_derivable_is_a_candidate_reason_not_a_verdict(self):
        assert "scores_derivable" in CANDIDATE_REASONS

    @pytest.mark.parametrize(
        "disposition",
        [d for d in list(Disposition) if d is not Disposition.SETTLED],
    )
    def test_grading_is_refused_for_every_unlicensed_disposition(self, disposition):
        with pytest.raises(UnverifiedGradingRefused) as exc:
            assert_grading_licensed(disposition, "scores_derivable")
        # The message must name the tempting input, not just the missing licence.
        assert "scores_derivable" in str(exc.value)

    def test_a_settled_probe_is_the_one_thing_that_passes(self):
        assert_grading_licensed(Disposition.SETTLED, "missing_winner")

    def test_a_frozen_mid_game_score_cannot_grade_via_any_path(self):
        """`project_events_score_not_ground_truth`: closed events keep MID-GAME scores.

        So a score-derived winner is a guess wearing arithmetic. It may nominate a
        market for probing; it may never settle one. There is no disposition
        reachable from scores alone, which is why this loops the whole vocabulary.
        """
        for disposition in list(Disposition):
            if disposition is Disposition.SETTLED:
                continue
            with pytest.raises(UnverifiedGradingRefused):
                assert_grading_licensed(disposition, "scores_derivable")
