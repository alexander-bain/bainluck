"""#6793: the two halves of one Polymarket question stop contradicting each other.

WHAT A READER SEES. A decomposed Yes/No prop whose two rows cannot both be true.
All six are live, and each was read back from `/api/futures/{id}` on 2026-09-17:

    Dawson Knox: Anytime Touchdown                61176498   No 90%   / Yes 15%
    Galaxy vs Rapids: O/U 8.5                     60976220   Under 50%/ Over 47.5%
    Will Heidi Overton be confirmed as FDA Comm.  59348095   Yes 53%  / No 26.5%
    Will Kelly Goodnow / Naomi Nguyen advance     61114370   No 69%   / Yes 25%
    Will OpenAI release a new frontier model...   16623136   No 100%  / Yes 2.2%
    Will the next Claude Opus model be released   57055739   No 100%  / Yes 4%

WHY THE WRITER PRODUCES IT. `_process_event_batch`'s decomposed-pair path resolves
the Over/Yes price through `_resolve_market_probability_with_source` — placeholder
guard, fabricated-midpoint guard, empty-book guard, and a `last_trade_price`
substitution when those refuse — and then takes the Under/No price RAW from
`market.outcome_prices[1]`. When the resolver did not return `outcome_prices[0]`,
or when Gamma's own two prices do not sum to 1, the two stored numbers are not two
views of one question and the pair stops summing.

WHY THE EXISTING GATE DID NOT CATCH IT. `classify_pair_opening` has governed this
exact arithmetic since 2026-08 — but only over `opening_probability`. Line for
line, the refusal it computes (`sub_pair_verdict`) was already sitting in this
function and was consulted for the opening and for nothing else, so the number we
are GRADED on was protected while the number a reader SEES was not.

MEASURED ON PRODUCTION, 2026-09-17, open Polymarket markets. Stored-row counts are
read-only db-query; the SERVED count is the actual payload of `/api/futures/{id}`
fetched for all 152, not a re-derivation of the serve predicate against the
database:

    two-leg decomposed sub-markets                          8,961
    pairs not summing to 1 (tolerance 0.02)                   282
      ... live: both legs ungraded, resolution date ahead      148
      ... of those, last written within 7 days                 139
    SERVED  both contradictory legs rendered              4 and 6
    GRADED  polymarket snapshot rows on that set            3,437
      ... written in the preceding 24 hours                    552

THE FIRST NUMBER I WROTE HERE WAS 143 SERVED AND IT WAS WRONG, which is why the
method is spelled out above. That figure came from replaying `is_empty_book_
midpoint` in SQL and calling everything it did not catch "a reader sees both
halves". Fetching the payloads showed serve already hides most of it by other
means — a leg with no price, a single-leg render — and the served count is a
handful. It also CHURNS: six markets at 21:05Z, four at 21:25Z, overlapping but
not equal, because the `:15` poll rewrites the population it is drawn from. Any
single number in that row is a sample, not a level.

The same pass caught the population itself being wrong twice over: the query did
not require exactly two outcomes, so it swept in 419 FIELD markets that merely
carry a `_yes`/`_no` pair among many rungs (date ladders, "Rotten Tomatoes
80+/85+/90+/95+") where summing past 1 is legitimate (gotcha #23); and it dropped
the `resolution_source IS NULL` filter, so settled rows rendering correct SETTLED
language ("No — Won — 100%" beside "Yes LATEST 2%") were counted as defects.

So the ship is two parts, honestly sized. A handful of markets stop showing a
reader two numbers that cannot both be true — `Galaxy vs Rapids: O/U 8.5 Total
Corners` was photographed at `/futures/60976220` reading Under 50% / Over 48%.
And all 148 stop feeding the calibration curve a price their own partner refutes;
that half has no serve-time rescue whatsoever and is the larger one.

FORWARD-ONLY, and that bounds the ship: a row is repaired when it is next polled,
so the 139 written within 7 days clear on their own and the 9 older ones do not.

NOT THIS. The 38 pairs whose No leg sits on its own empty-book midpoint are
already refused at SERVE by `is_empty_book_midpoint`; that predicate's condition-3
rounding is a third, separate defect fixed in PR #6792. Neither addresses the
pairs here, whose books are perfectly ordinary.

RED-FIRST, measured rather than asserted. With `app/tasks/polymarket.py` alone
reverted to master `aabd00fe6` and this file's helper left in place (reverting the
helper too turns the run into a collection error, which proves nothing about the
writer): **14 failed, 25 passed.**

The 14 are every writer pin that names the new behaviour, across both writer
classes and the call-site pin in `TestAOneSidedMarketIsNotAPair`'s second case —
the writer stores `prob` and `under_prob` unconditionally and executes both
snapshot inserts unconditionally.

THREE CASES IN THOSE TWO CLASSES PASS BEFORE AND AFTER, and they are named here so
nobody reads them as evidence of the fix: `test_the_predicate_is_imported_not_
restated`, `test_the_book_is_still_recorded_on_both_legs` and
`test_the_opening_gate_is_still_there` are regression guards on properties master
already had — the first two would only fire if this change had inlined the
tolerance or dropped the book columns, and the third if it had REPLACED the
opening gate instead of adding to it. Likewise
`test_the_snapshot_column_is_still_not_nullable`, which pins the premise that
makes skipping (rather than nulling) the snapshot the only honest option.

`TestCoherentPairsAreUntouched`, `TestAOneSidedMarketIsNotAPair`'s predicate case
and `TestProvenanceIsTheOneClauseTheTwoGatesDisagreeOn` are the controls that stop
a green run meaning "the branch dropped everything".
"""
import inspect

import pytest

from app.tasks import polymarket
from app.utils.pair_opening_coherence import (
    OK,
    PAIR_SUM_TOLERANCE,
    PAIRED_PRICE_SOURCE,
    REFUSED_IDENTICAL_LEGS,
    REFUSED_MISSING_LEG,
    REFUSED_SUM_OUT_OF_TOLERANCE,
    REFUSED_UNPAIRED_SOURCE,
    classify_pair_opening,
    classify_pair_price,
    pair_price_allowed,
)


# The six live pairs a reader is actually served both halves of, as stored.
# Read read-only from production and confirmed against `/api/futures/{id}` on
# 2026-09-17 21:0x Z. Ids are the FuturesMarket ids so a later reader can re-check
# any of them directly.
LIVE_INCOHERENT = [
    pytest.param(0.15, 0.90, id="dawson-knox-anytime-td-61176498"),
    pytest.param(0.475, 0.50, id="galaxy-rapids-ou-8pt5-60976220"),
    pytest.param(0.53, 0.265, id="heidi-overton-fda-59348095"),
    pytest.param(0.25, 0.69, id="goodnow-nguyen-advance-61114370"),
    pytest.param(0.022, 1.0, id="openai-frontier-model-16623136"),
    pytest.param(0.04, 1.0, id="next-claude-opus-57055739"),
]


class TestThePredicateNamesTheDefect:
    """`classify_pair_price` on the numbers actually stored."""

    @pytest.mark.parametrize("yes,no", LIVE_INCOHERENT)
    def test_a_live_incoherent_pair_is_refused(self, yes, no):
        assert classify_pair_price(yes, no) != OK
        assert pair_price_allowed(yes, no) is False

    def test_both_legs_certain_is_named_as_its_own_class(self):
        """The 100%/100% rows must not be buried in a generic sum counter."""
        assert classify_pair_price(1.0, 1.0) == REFUSED_IDENTICAL_LEGS

    def test_an_ordinary_mismatch_is_named_a_sum_failure(self):
        """The FDA-commissioner row: Yes 53% / No 26.5%, summing to 0.795."""
        assert classify_pair_price(0.53, 0.265) == REFUSED_SUM_OUT_OF_TOLERANCE

    def test_a_coin_flip_pair_is_not_an_identical_leg_failure(self):
        """0.50/0.50 is the one identical pair that IS coherent."""
        assert classify_pair_price(0.5, 0.5) == OK


class TestProvenanceIsTheOneClauseTheTwoGatesDisagreeOn:
    """The current-price question is NOT the opening question (#6793 vs CAL-P094).

    This is the whole reason a second function exists rather than a second call to
    the first one. If these two ever return the same verdict for a substituted
    price, the price gate has silently become the opening gate and will blank every
    market the resolver rescued with a real last trade.
    """

    def test_a_substituted_price_that_still_sums_is_kept_as_a_price(self):
        assert classify_pair_price(0.30, 0.70) == OK

    def test_but_the_same_pair_is_refused_as_an_opening(self):
        assert (
            classify_pair_opening(0.30, 0.70, price_source="last_trade_price")
            == REFUSED_UNPAIRED_SOURCE
        )

    def test_the_price_gate_cannot_be_handed_a_source_at_all(self):
        """No keyword to pass means no call site can re-introduce the clause."""
        params = inspect.signature(classify_pair_price).parameters
        assert "price_source" not in params

    def test_the_price_gate_delegates_rather_than_restating_the_arithmetic(self):
        """Two copies of the sum test would drift; the module says so."""
        src = inspect.getsource(classify_pair_price)
        assert "classify_pair_opening(" in src
        assert "PAIRED_PRICE_SOURCE" in src

    def test_both_gates_share_one_tolerance(self):
        sig = inspect.signature(classify_pair_price)
        assert sig.parameters["tolerance"].default == PAIR_SUM_TOLERANCE


class TestCoherentPairsAreUntouched:
    """Controls. Green before the fix and green after — a pass here is never
    "the writer refused everything"."""

    @pytest.mark.parametrize(
        "yes,no",
        [(0.5, 0.5), (0.28, 0.72), (0.99, 0.01), (0.001, 0.999), (0.0, 1.0)],
    )
    def test_a_complementary_pair_survives(self, yes, no):
        assert classify_pair_price(yes, no) == OK

    def test_ordinary_rounding_and_residual_vig_pass(self):
        """The measured `complementary` class averages 1.0001 across 339,587."""
        assert classify_pair_price(0.505, 0.505) == OK
        assert classify_pair_price(0.33, 0.68) == OK

    def test_a_sum_inside_the_tolerance_is_kept_and_one_past_it_is_not(self):
        """Pinned a hair inside the bound rather than exactly on it, deliberately.

        `0.5 + PAIR_SUM_TOLERANCE` sums to 1.0000000000000002 past the bound, so the
        exact boundary here is decided by float representation, not by the rule.
        That is a real property of the shared `>` comparison and it is the same
        class PR #6792 is fixing in `is_empty_book_midpoint`'s condition 3 — it is
        NOT this ship's to change, and asserting a boundary that only holds by
        accident would encode the accident. Every measured specimen is orders of
        magnitude clear of the bound (the worst sums to 2.0, the nearest to 0.35),
        so nothing here rests on it.
        """
        assert classify_pair_price(0.5, 0.5 + PAIR_SUM_TOLERANCE - 0.001) == OK
        assert classify_pair_price(0.5, 0.5 + PAIR_SUM_TOLERANCE + 0.001) != OK


class TestAOneSidedMarketIsNotAPair:
    """A market with no second leg has nothing to contradict.

    The predicate fails closed on a `None` partner on purpose, so the protection
    that keeps thousands of one-sided markets alive is the CALL SITE's guard, and
    that is what is pinned here.
    """

    def test_the_predicate_itself_fails_closed(self):
        assert classify_pair_price(0.42, None) == REFUSED_MISSING_LEG

    def test_but_the_writer_only_asks_when_a_second_leg_exists(self):
        block = _pair_block()
        assert "if sub_under_raw is not None:" in block
        assert "sub_price_ok = True" in block


def _pair_block() -> str:
    """The decomposed-pair write path, sliced from the poll's own source.

    Same idiom and same reasoning as `test_polymarket_under_leg_book.py`: this path
    needs a live async session to execute, so the pins are structural. Both bounds
    are real constructs rather than comments kept alive as anchors.
    """
    src = inspect.getsource(polymarket._process_event_batch)
    start = src.index("# Create Over/Yes outcome")
    end = src.index("# CAL-P006 (#1527)")
    assert end > start
    return src[start:end]


class TestTheWriterRefusesAnIncoherentPair:
    """Structural pins on both upserts. Each fails on a revert."""

    def test_the_gate_is_actually_called(self):
        block = _pair_block()
        assert "classify_pair_price(" in block

    def test_the_predicate_is_imported_not_restated(self):
        """An inline `abs(yes + no - 1) > 0.02` would drift from the census."""
        block = _pair_block()
        assert "0.02" not in block
        assert "PAIR_SUM_TOLERANCE" not in block

    @pytest.mark.parametrize("leg", ["over", "under"])
    def test_the_insert_stores_the_gated_value_not_the_raw_one(self, leg):
        block = _pair_block()
        assert f"current_probability=sub_{leg}_price," in block

    @pytest.mark.parametrize("leg", ["over", "under"])
    def test_the_conflict_update_stores_it_too(self, leg):
        """An insert-only fix leaves every already-existing row lying forever —
        and every one of the 143 measured rows already exists."""
        block = _pair_block()
        assert f'"current_probability": sub_{leg}_price,' in block

    @pytest.mark.parametrize("leg", ["over", "under"])
    def test_the_american_odds_are_withdrawn_with_the_probability(self, leg):
        """A price refused as a number must not survive as a price in odds form."""
        block = _pair_block()
        assert f"current_american_odds=sub_{leg}_american," in block
        assert f'"current_american_odds": sub_{leg}_american,' in block

    def test_the_raw_values_no_longer_reach_either_upsert(self):
        """The defect in its original form: `prob` and `under_prob` written bare."""
        block = _pair_block()
        assert "current_probability=prob," not in block
        assert '"current_probability": prob,' not in block
        assert "current_probability=under_prob," not in block
        assert '"current_probability": under_prob,' not in block

    def test_the_refusal_is_symmetric(self):
        """One leg withdrawn and its partner kept is the `partial_open` shape the
        module's own doctrine forbids."""
        block = _pair_block()
        assert "sub_over_price = prob if sub_price_ok else None" in block
        assert "sub_under_price = under_prob if sub_price_ok else None" in block

    def test_the_book_is_still_recorded_on_both_legs(self):
        """A refusal is about the derived probabilities, never about the quotes —
        and every downstream book predicate reads these columns."""
        block = _pair_block()
        assert "current_yes_bid=market.best_bid," in block
        assert "current_yes_bid=under_best_bid," in block
        assert "current_yes_ask=under_best_ask," in block

    def test_a_refused_price_does_not_advance_the_change_stamp(self):
        """`price_changed_at` on a price we declined to store is a freshness stamp
        on an absence."""
        block = _pair_block()
        assert "if sub_price_ok:" in block
        assert '"price_changed_at": price_changed_at_value(' not in block

    def test_the_refusal_is_counted_by_reason(self):
        """"We declined 900 pairs" is not actionable; the reason is."""
        block = _pair_block()
        assert 'stats["pair_price_refused"]' in block
        assert 'f"pair_price_{sub_price_verdict}"' in block

    def test_the_opening_gate_is_still_there(self):
        """The price gate is an addition. Replacing the opening gate with it would
        re-open CAL-P094 — a mixed-source pair that happens to sum to 1 would be
        stamped as a published forecast again."""
        block = _pair_block()
        assert "classify_pair_opening(" in block
        assert "sub_pair_verdict" in block


class TestTheSnapshotHalfIsRefusedToo:
    """`FuturesOddsSnapshot` is the half calibration grades on.

    `calibration_probability` reads snapshots before it falls back to the opening,
    so an incoherent price stored here is graded even though the opening gate
    refused the very same pair. `probability` is NOT NULL, so the honest treatment
    is to skip the row, not to null it.
    """

    @pytest.mark.parametrize(
        "stmt",
        [
            "snap_stmt = pg_insert(FuturesOddsSnapshot)",
            "under_snap_stmt = pg_insert(FuturesOddsSnapshot)",
        ],
    )
    def test_neither_snapshot_is_written_for_a_refused_pair(self, stmt):
        """Each snapshot insert sits INSIDE the price gate.

        Checked by indentation rather than by "the gate appears somewhere above",
        which would stay green if the gate governed only the first of the two.
        """
        block = _pair_block()
        lines = block.splitlines()
        idx = next(i for i, ln in enumerate(lines) if stmt in ln)
        indent = len(lines[idx]) - len(lines[idx].lstrip())

        # Walk back to the nearest enclosing statement — the first preceding
        # code line indented strictly less than this one.
        for prev in reversed(lines[:idx]):
            stripped = prev.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if len(prev) - len(prev.lstrip()) < indent:
                assert stripped == "if sub_price_ok:", (
                    f"{stmt!r} is enclosed by {stripped!r}, not the price gate"
                )
                break
        else:
            pytest.fail(f"{stmt!r} is not nested inside anything")

    def test_the_snapshot_column_is_still_not_nullable(self):
        """If this ever becomes nullable the skip above could be reconsidered —
        until then, skipping is the only honest option and this pins the premise."""
        from app.models.models import FuturesOddsSnapshot

        assert FuturesOddsSnapshot.__table__.c.probability.nullable is False

    def test_a_skipped_snapshot_is_not_counted_as_created(self):
        """Reporting captured prices that do not exist is gotcha #53."""
        block = _pair_block()
        assert 'stats["snapshots_created"] += 1' in block
        idx = block.index('stats["snapshots_created"] += 1')
        assert "if sub_price_ok:" in block[:idx]
