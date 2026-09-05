"""CAL-P128 — guards for the measured-sigma ledger and the board overlay.

The instrument these guards protect settles a question the board has been
getting wrong for seven cells: ``SIGMA_GATE`` is a rule about STANDARD ERRORS,
and the scorecard has been feeding it a binomial estimate over ROW counts on a
population whose rows are not independent. CAL-P120 removed six cells by
re-deriving the real SE in-session, CAL-P127 removed a seventh, and each one
was then carried forward as a paragraph in a handoff note.

Five claims in the CAL-P128 write-up are load-bearing, and each is pinned here
rather than described:

1. **The ledger stores the SE, not the sigma.** A sigma bakes in an ECE and a
   bar, both of which move for reasons that have nothing to do with the
   sample's correlation structure — Alex re-ratified the bars on 2026-08-28 and
   every sigma stored before that instant silently meant something else after
   it. The SE is the one term that is a property of the sample.
2. **The correction runs in BOTH directions, and the ratio is named for what
   it is a ratio TO.** ``variance_ratio_vs_board`` divides the measured
   variance by the board's ``50/sqrt(n)`` MAXIMUM-VARIANCE bound, not by an SRS
   variance — so it is not a textbook design effect and it legitimately falls
   below 1 (cricket 0.485, crypto 0.835), where the measured sigma comes out
   HIGHER than the board's. It is squared, so golf's SE ratio of 1.71 gives
   2.91 — the number criterion 3 asked for, reproduced exactly.
3. **A stale entry contributes NOTHING.** A bootstrap SE describes one specific
   set of rows. When those rows change, the entry describes a population nobody
   is looking at, and reporting it anyway is gotcha #53 in ledger form.
   *(NARROWED by CAL-P998: the test for "those rows changed" was
   ``population_version`` identity, which on 2026-09-03 dropped all 14 committed
   entries at once and left the overlay covering 0 of 14 queued cells. It is now
   ``CELL_DRIFT_BAND`` on the cell's own ``n``. The claim is unchanged and its
   guard below now uses a fixture where the cell really did move;
   ``test_calibration_sigma_carry_998.py`` holds the other side.)*
4. **The overlay REPORTS and does not DECIDE.** Adding the measured column must
   not move ``cells_at_bar``, ``cells_queued``, ``done``, or any cell's
   ``verdict``. The needle is the number the program is steered by, and a
   finding that shortens the queue deserves more suspicion than one that
   lengthens it — the flip is Alex's call, not an instrument's side effect.
5. **A proof and an estimate never share a column** (CAL-P127 lesson 10). An
   unmeasured cell renders an em-dash, never its row-grain figure.

The gate and the bars are IMPORTED from ``calibration_scorecard``, never
restated (CAL-P115's rule — an equal copy drifts on the next edit), and the
tests assert the IDENTITY rather than the equality.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ledger_mod = _load("calibration_sigma_ledger")
cs = _load("calibration_scorecard")


# --------------------------------------------------------------------------
# Fixtures — the real kalshi/golf measurement, CAL-P127, population q268.
#
# Real numbers rather than round ones on purpose: this cell IS the board's
# rank-9 row and the reason the ledger exists, so an arithmetic claim pinned to
# it is a claim about the thing that actually happened.
# --------------------------------------------------------------------------

GOLF_SIGMA_JSON = {
    "source": "kalshi",
    "category": "golf",
    "boot": 2000,
    "seed": 20260829,
    "clusters": 1045,
    "rows_per_cluster": 19.776,
    "bar": 3.0,
    "excess": 0.84,
    "klass": "B_exchange_contest",
    "sigma_gate": 2.0,
    "established": False,
    "bootstrap_ci": [2.86, 5.17],
    "payload": {
        "n": 20500,
        "ece": 3.88,
        "gap": 3.72,
        "generated_at": "2026-08-29T00:36:47.978149+00:00",
        "population_version": "q268",
    },
    "exact": {"n": 20666, "ece": 3.84, "gap": 3.68},
    "se": {
        "row": 0.3478097817005562,
        "market": 1.546720562224365,
        "bootstrap": 0.5929493304062452,
    },
    "sigma": {
        "row": 2.415113214737562,
        "market": 0.5430845238082189,
        "bootstrap": 1.4166471853918676,
    },
}


def _bucket(source, category, idx, n, winners, avg_prob, price_moved=False):
    return {
        "bucket_idx": idx,
        "source": source,
        "category": category,
        "price_moved": price_moved,
        "n": n,
        "winners": winners,
        "avg_prob": avg_prob,
        "sum_prob": n * avg_prob,
    }


def _payload(n, ece_pp, source="kalshi", category="golf", pop="q268"):
    """One cell of size n whose pooled ECE is ece_pp, by construction."""
    winners = int(round(n * (0.5 - ece_pp / 100)))
    return {
        "buckets": [_bucket(source, category, 5, n, winners, 0.50)],
        "mce_closing_line": 1.0,
        "population_version": pop,
        "total_outcomes": n,
    }


def _ledger_with(se_bootstrap, pop="q268", source="kalshi", category="golf"):
    """A minimal COHERENT ledger — its stored sigma reproduces from its SE."""
    obj = copy.deepcopy(GOLF_SIGMA_JSON)
    obj["source"], obj["category"] = source, category
    obj["se"]["bootstrap"] = se_bootstrap
    obj["payload"]["population_version"] = pop
    obj["sigma"]["bootstrap"] = obj["excess"] / se_bootstrap
    entry = ledger_mod.entry_from_sigma_json(obj, "test")
    return {
        "schema": ledger_mod.SCHEMA,
        "entries": {ledger_mod.cell_key(source, category): entry},
    }


# --------------------------------------------------------------------------


class TestTheLedgerStoresTheStandardError:
    def test_the_load_bearing_field_is_the_se_not_the_sigma(self):
        e = ledger_mod.entry_from_sigma_json(GOLF_SIGMA_JSON, "x")
        assert e["se_bootstrap_pp"] == GOLF_SIGMA_JSON["se"]["bootstrap"]

    def test_a_re_ratified_bar_changes_the_sigma_and_not_the_ledger(self):
        """The whole reason the SE is stored instead of the sigma.

        Alex re-ratified the cohort bars on 2026-08-28. If the ledger held a
        sigma, every entry would have silently changed meaning at that instant.
        Holding the SE means the consumer just divides a new numerator.
        """
        led = _ledger_with(0.5929493304062452)
        se = led["entries"]["kalshi/golf"]["se_bootstrap_pp"]

        cell_at_3 = cs.score(_payload(20_500, 3.88), led)["cells"][0]
        # Same cell, same ledger, a TIGHTER bar: the sigma must move.
        cs_bars = dict(cs.CLASS_BARS_PP)
        try:
            cs.CLASS_BARS_PP[cs.classify("kalshi", "golf")] = 2.0
            cell_at_2 = cs.score(_payload(20_500, 3.88), led)["cells"][0]
        finally:
            cs.CLASS_BARS_PP.clear()
            cs.CLASS_BARS_PP.update(cs_bars)

        assert cell_at_2["sigma_measured"] > cell_at_3["sigma_measured"]
        # ...and the ledger did not move under it.
        assert led["entries"]["kalshi/golf"]["se_bootstrap_pp"] == se

    def test_the_two_ece_bases_are_stored_separately_never_collapsed(self):
        """The bootstrap is on the exact rail; the board scores the payload.

        Golf reads 3.84 over 20,666 rail rows and 3.88 over 20,500 published
        ones. Collapsing them into one `ece` field is how a documented basis
        shift becomes an undocumented one.
        """
        m = ledger_mod.entry_from_sigma_json(GOLF_SIGMA_JSON, "x")["as_measured"]
        assert m["ece_exact"] == 3.84
        assert m["ece_payload"] == 3.88
        assert m["n_exact"] == 20666
        assert m["n"] == 20500
        assert "ece" not in m, "an unlabelled `ece` field is the collapse itself"


class TestValidateIsTheTranscriptionGuard:
    def test_a_coherent_entry_validates(self):
        assert ledger_mod.validate(_ledger_with(0.5929493304062452)) == []

    def test_a_sigma_that_does_not_reproduce_from_its_se_is_refused(self):
        """This check caught a real defect on its first run.

        The first draft of the ledger took its excess from the PAYLOAD ece,
        which is not the numerator `cluster_sigma` divided by — so golf's
        stored 1.4166 recomputed to 1.4841 and the ledger refused to build.
        That is the failure mode this guard exists for.
        """
        led = _ledger_with(0.5929493304062452)
        led["entries"]["kalshi/golf"]["as_measured"]["sigma_bootstrap"] = 99.0
        problems = ledger_mod.validate(led)
        assert problems and "stored sigma" in problems[0]

    def test_an_entry_with_no_population_is_refused(self):
        led = _ledger_with(0.5929493304062452)
        led["entries"]["kalshi/golf"]["population_version"] = None
        assert any("population_version" in p for p in ledger_mod.validate(led))

    def test_load_raises_rather_than_degrading(self, tmp_path):
        """A malformed ledger must not silently fall back to the old board."""
        led = _ledger_with(0.5929493304062452)
        led["entries"]["kalshi/golf"]["se_bootstrap_pp"] = None
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(led))
        with pytest.raises(ValueError):
            ledger_mod.load(p)

    def test_a_missing_ledger_is_an_error_not_an_empty_one(self, tmp_path):
        """🔴 REVERSED BY CAL-P129 — this asserted the opposite until 2026-08-29.

        The original read ``load(missing)["entries"] == {}`` and carried no
        rationale, one line below a sibling whose docstring says *"A malformed
        ledger must not silently fall back to the old board."* The two halves of
        the same question were answered opposite ways, and only the malformed
        half was argued.

        CAL-P129 measured what the unargued half costs. ``LEDGER_PATH`` was
        relative, so ``cd backend && python3 scripts/calibration_scorecard.py``
        — the invocation CLAUDE.md documents for every backend script — missed
        the file, took this empty reading, and printed a complete, plausible
        board reporting ``queued_cells_measured: 0`` and
        ``cells_at_bar_if_applied: 29``. From the repository root the same
        command reports 12 and 31. No error, no banner, exit 0.

        The path is now absolute, so this case is far less reachable; the
        reversal is kept anyway, because "less reachable" is not the same
        argument as "safe", and it was unreachability that hid it the first
        time. ``missing_ok=True`` is the opt-in for the one caller — ``--build``
        — that legitimately starts from no ledger.
        """
        with pytest.raises(FileNotFoundError):
            ledger_mod.load(tmp_path / "nope.json")
        assert ledger_mod.load(tmp_path / "nope.json", missing_ok=True)["entries"] == {}


class TestTheVarianceRatioIsNamedForWhatItIsARatioTo:
    def test_golf_reproduces_the_published_2_91(self):
        """CAL-P127 quoted 2.91 from a separate derivation. This must agree."""
        e = ledger_mod.entry_from_sigma_json(GOLF_SIGMA_JSON, "x")
        assert e["variance_ratio_vs_board"] == pytest.approx(2.91, abs=0.01)

    def test_it_is_squared_not_the_se_ratio(self):
        """The mutation guard. Golf's SE ratio is 1.705; the ratio is its square.

        Dropping the square is a silent, plausible-looking edit that would
        understate every correction on the board by its own square root.
        """
        se_ratio = GOLF_SIGMA_JSON["se"]["bootstrap"] / GOLF_SIGMA_JSON["se"]["row"]
        assert se_ratio == pytest.approx(1.705, abs=0.01)
        assert ledger_mod.variance_ratio_vs_board(
            GOLF_SIGMA_JSON["se"]["bootstrap"], GOLF_SIGMA_JSON["se"]["row"]
        ) == pytest.approx(se_ratio**2, abs=0.001)

    def test_a_ratio_below_one_is_legitimate_and_is_not_clamped(self):
        """The finding that renamed this field.

        ``kalshi/crypto`` measures 0.835 and ``polymarket/cricket`` 0.485. A
        CLASSICAL design effect cannot go below 1 by clustering; this one can,
        because its denominator is the board's ``p=0.5`` maximum-variance bound
        rather than an SRS variance. Clamping at 1.0 -- the obvious "fix" for a
        number that looks impossible -- would hide that the correction runs in
        BOTH directions and would overstate those two cells' sigmas.
        """
        assert ledger_mod.variance_ratio_vs_board(0.6113, 0.8776) == pytest.approx(
            0.485, abs=0.01
        )

    def test_a_cell_measuring_below_one_gets_a_HIGHER_sigma_not_a_lower_one(self):
        """Cricket reads 5.87 on the board and 8.42 measured. The overlay must
        be able to make a cell MORE established, or it is not a measurement.

        Compared against ``sigma_row``, not ``sigma``: since D62 ``sigma`` IS
        the measured value here, and the old form of this assertion silently
        became ``x > x``.
        """
        led = _ledger_with(0.6113)
        cell = cs.score(_payload(3252, 8.11), led)["cells"][0]
        assert cell["sigma_measured"] > cell["sigma_row"]
        assert cell["sigma"] == cell["sigma_measured"]

    def test_matching_ses_give_a_ratio_of_one(self):
        """The degenerate end: if the bootstrap agrees with the board's bound,
        the correction does nothing and the column says so."""
        assert ledger_mod.variance_ratio_vs_board(0.5, 0.5) == 1.0

    def test_effective_n_is_the_pair_criterion_3_asked_for(self):
        e = ledger_mod.entry_from_sigma_json(GOLF_SIGMA_JSON, "x")
        assert e["effective_n"] == pytest.approx(20_500 / 2.907, rel=0.01)
        assert e["effective_n"] < GOLF_SIGMA_JSON["payload"]["n"]


class TestPopulationDivergenceReportsButDoesNotDecide:
    """The trap the sweep walked up to: the one cell a measured sigma would
    have removed from the board is also the one where the rail and the payload
    disagree hardest about which rows are even in it."""

    def _low_cov_ledger(self, se=0.8236):
        obj = copy.deepcopy(GOLF_SIGMA_JSON)
        obj["payload"]["n"] = 13135
        obj["exact"]["n"] = 8426  # polymarket/basketball, measured 2026-08-29
        obj["se"]["bootstrap"] = se
        obj["sigma"]["bootstrap"] = obj["excess"] / se
        entry = ledger_mod.entry_from_sigma_json(obj, "test")
        return {"schema": ledger_mod.SCHEMA, "entries": {"kalshi/golf": entry}}

    def test_coverage_is_stored(self):
        e = self._low_cov_ledger()["entries"]["kalshi/golf"]
        assert e["exact_coverage"] == pytest.approx(0.641, abs=0.001)

    def test_lookup_flags_it(self):
        _, status = ledger_mod.lookup(
            self._low_cov_ledger(), "kalshi", "golf", "q268"
        )
        assert status == ledger_mod.STATUS_POPULATION_DIVERGENCE

    def test_the_sigma_is_still_reported(self):
        """It is the only measurement of that cell anyone has."""
        cell = cs.score(_payload(13135, 4.24), self._low_cov_ledger())["cells"][0]
        assert cell["sigma_measured"] is not None
        assert cell["exact_coverage"] == pytest.approx(0.641, abs=0.001)

    def test_but_it_decides_nothing_even_now_that_measurements_decide(self):
        """AMENDED CAL-P1002 — and this is the half of D62 that did NOT change.

        Before D62 this asserted the absence of a ``measured_verdict`` field,
        which after the flip would pass vacuously (nothing sets that field any
        more). The claim was never about the field: it is that a cell whose SE
        and excess describe different populations has no sigma to offer. So it
        is now asserted where it can fail — the deciding basis stays the row
        estimate and the verdict is identical to the no-ledger board.
        """
        cell = cs.score(_payload(13135, 4.24), self._low_cov_ledger())["cells"][0]
        assert cell["sigma_measured"] is not None, "the number is still shown"
        assert cell["sigma_basis"] == cs.SIGMA_BASIS_ROW
        assert cell["sigma"] == cell["sigma_row"]
        assert cell["verdict"] == cell["verdict_row_basis"]

    def test_it_is_counted_in_its_own_bucket_never_as_refuted(self):
        ms = cs.score(_payload(13135, 4.24), self._low_cov_ledger())["measured_sigma"]
        assert ms["material_cells_low_coverage"] == 1
        assert ms["cells_refuted"] == 0
        assert ms["material_cells_measured"] == 0

    def test_a_low_coverage_cell_does_not_move_the_needle(self):
        """The two bases must AGREE here — that is what "decides nothing" means
        once the overlay decides. Before D62 the same claim read the other way
        round, against a projection."""
        r = cs.score(_payload(13135, 4.24), self._low_cov_ledger())
        assert r["counts"]["cells_at_bar_row_basis"] == r["counts"]["cells_at_bar"]
        assert r["measured_sigma"]["cells_at_bar_delta_vs_row_basis"] == 0

    def test_the_render_parenthesises_it(self):
        md = cs.render_markdown(
            cs.score(_payload(13135, 4.24), self._low_cov_ledger()), []
        )
        row = [l for l in md.splitlines() if "kalshi/golf" in l][0]
        assert "(" in row and ")" in row and "⚠️" in row
        assert "🔴" not in row, "a caveated number must not read as a refutation"

    def test_the_band_is_where_the_sweep_separates(self):
        """0.90 is not a taste call: the 2026-08-29 sweep put ten cells inside
        +/-3% of 1.0, then 0.780 and 0.641, with nothing in between."""
        lo, hi = ledger_mod.COVERAGE_BAND
        assert 0.780 < lo < 0.939
        assert hi > 1.027, "cells legitimately read slightly OVER 1.0"

    def test_the_band_is_two_sided_not_a_floor(self):
        """A one-sided floor assumes the payload is always the correct side.
        `polymarket/basketball` is 43.44% phantom (CAL-P126) and it is not."""
        obj = copy.deepcopy(GOLF_SIGMA_JSON)
        obj["payload"]["n"] = 1000
        obj["exact"]["n"] = 5000  # rail wildly OVER the payload
        entry = ledger_mod.entry_from_sigma_json(obj, "t")
        led = {"schema": ledger_mod.SCHEMA, "entries": {"kalshi/golf": entry}}
        assert ledger_mod.lookup(led, "kalshi", "golf", "q268")[1] == (
            ledger_mod.STATUS_POPULATION_DIVERGENCE
        )


class TestStalenessIsAState:
    def test_a_matching_population_is_fresh(self):
        led = _ledger_with(0.5, pop="q268")
        _, status = ledger_mod.lookup(led, "kalshi", "golf", "q268")
        assert status == ledger_mod.STATUS_FRESH

    def test_a_different_population_is_stale(self):
        led = _ledger_with(0.5, pop="q268")
        entry, status = ledger_mod.lookup(led, "kalshi", "golf", "q999")
        assert status == ledger_mod.STATUS_STALE
        assert entry is not None, "the entry is returned WITH its status, not hidden"

    def test_an_absent_cell_is_absent_not_stale(self):
        led = _ledger_with(0.5)
        assert ledger_mod.lookup(led, "kalshi", "nope", "q268")[1] == (
            ledger_mod.STATUS_ABSENT
        )

    def test_a_stale_entry_contributes_no_sigma_to_the_board(self):
        """gotcha #53: the ledger returning a number is not the number applying.

        AMENDED CAL-P998, and the amendment is to the FIXTURE, not to the
        claim. This test used to hold the population version wrong and the
        cell's size RIGHT, which after the carry rule is the case the ledger
        now calls ``CARRIED``. The claim it exists to defend is about an entry
        that describes rows nobody is looking at, so the fixture now says that:
        11,000 rows against a measurement over 20,500 is a cell that moved by
        46%, well outside ``CELL_DRIFT_BAND``, and it contributes nothing.

        The carried case is pinned in ``test_calibration_sigma_carry_998.py``.
        Both must hold — this one is what stops the carry rule from becoming
        "apply everything", which is the failure it would be mistaken for.
        """
        led = _ledger_with(0.5, pop="q_OLD")
        cell = cs.score(_payload(11_000, 3.88, pop="q268"), led)["cells"][0]
        assert cell["sigma_ledger_status"] == ledger_mod.STATUS_STALE
        assert "sigma_measured" not in cell
        assert cell["sigma_basis"] == cs.SIGMA_BASIS_ROW

    def test_build_prefers_the_measurement_on_the_newer_population(self, tmp_path):
        old = copy.deepcopy(GOLF_SIGMA_JSON)
        old["payload"]["generated_at"] = "2026-08-01T00:00:00Z"
        old["payload"]["population_version"] = "q100"
        new = copy.deepcopy(GOLF_SIGMA_JSON)
        # Written FIRST so filename order cannot be what decides it.
        (tmp_path / "a-new.json").write_text(json.dumps(new))
        (tmp_path / "z-old.json").write_text(json.dumps(old))
        built = ledger_mod.build(sorted(tmp_path.glob("*.json")))
        assert built["entries"]["kalshi/golf"]["population_version"] == "q268"


class TestTheOverlayDecidesAndSaysSo:
    """Claim 4, INVERTED by Alex's D62 = A on 2026-09-04 — and the inversion is
    the whole content of CAL-P1002, so it is pinned here rather than in a new
    file with the old claim quietly deleted.

    The old claim was "the needle must not move because an instrument landed",
    and the reasoning behind it was never that the measurement is wrong: it was
    that a finding which shortens the queue deserves more suspicion than one
    that lengthens it, so the flip is Alex's call and not an instrument's side
    effect. Alex made the call. What survives of the old claim is everything
    except the veto — the needle may now move, and it may move ONLY where the
    ledger says a measurement is allowed to decide, and every move must be
    visible on the board with both numbers beside it. Those are the tests
    below, and they are strictly harder than the ones they replace.
    """

    #: A cell the row-grain estimate QUEUES and the measured SE REFUTES.
    #: n=20,500 at 3.88 pp is golf: excess +0.88, row sigma 2.5, and an SE of
    #: 0.593 pp puts it at 1.48 — under the ratified 2.0 gate.
    REFUTING_SE = 0.5929493304062452

    def _both(self):
        payload = _payload(20_500, 3.88)
        return (
            cs.score(payload, None),
            cs.score(payload, _ledger_with(self.REFUTING_SE)),
        )

    def test_the_fixture_really_does_disagree(self):
        """A no-op overlay would make every test below pass vacuously."""
        _, with_ledger = self._both()
        cell = with_ledger["cells"][0]
        assert cell["sigma_row"] >= cs.SIGMA_GATE
        assert cell["sigma_measured"] < cs.SIGMA_GATE
        assert cell["verdict_row_basis"] == cs.VERDICT_QUEUED

    def test_the_verdict_moves_and_the_measurement_is_what_moved_it(self):
        without, with_ledger = self._both()
        assert without["cells"][0]["verdict"] == cs.VERDICT_QUEUED
        cell = with_ledger["cells"][0]
        assert cell["verdict"] == cs.VERDICT_UNDER_SIGMA
        assert cell["sigma_basis"] == cs.SIGMA_BASIS_MEASURED
        assert cell["sigma"] == cell["sigma_measured"]

    def test_the_needle_moves_by_exactly_the_cells_the_measurement_took_off(self):
        without, with_ledger = self._both()
        assert with_ledger["counts"]["cells_queued"] == (
            without["counts"]["cells_queued"] - 1
        )
        assert with_ledger["counts"]["cells_at_bar"] == (
            without["counts"]["cells_at_bar"] + 1
        )

    def test_the_row_basis_needle_is_still_published_beside_it(self):
        """The counterfactual did not disappear when it stopped being the
        reading — it swapped places with the projection. A needle that changed
        basis without its old value beside it is a needle nobody can check."""
        without, with_ledger = self._both()
        assert with_ledger["counts"]["cells_at_bar_row_basis"] == (
            without["counts"]["cells_at_bar"]
        )
        ms = with_ledger["measured_sigma"]
        assert ms["cells_refuted"] == 1
        assert ms["refuted_cells"] == ["kalshi/golf"]
        assert ms["cells_at_bar_delta_vs_row_basis"] == 1

    def test_every_move_is_named_on_the_wire_with_both_sigmas(self):
        """``sigma_overlay.cells_moved`` is the receipt. Without it the flip is
        a number that changed and nothing that says which rows changed it."""
        _, with_ledger = self._both()
        moved = with_ledger["sigma_overlay"]["cells_moved"]
        assert [m["cell"] for m in moved] == ["kalshi/golf"]
        m = moved[0]
        assert m["from"] == cs.VERDICT_QUEUED
        assert m["to"] == cs.VERDICT_UNDER_SIGMA
        assert m["sigma_row"] >= cs.SIGMA_GATE > m["sigma_measured"]

    def test_it_can_ADD_a_cell_to_the_queue_not_only_remove_one(self):
        """A correction that can only ever shorten the board is one nobody
        should trust. cricket measures 8.05 against an estimate of 5.34 — the
        measured SE runs both ways and the counting has to as well.

        n=20,500 at 3.10 pp is +0.10 excess: row sigma 0.29, under the gate. An
        SE of 0.03 pp puts the measurement at 3.33, over it.
        """
        result = cs.score(_payload(20_500, 3.10), _ledger_with(0.03))
        cell = result["cells"][0]
        assert cell["verdict_row_basis"] == cs.VERDICT_UNDER_SIGMA
        assert cell["verdict"] == cs.VERDICT_QUEUED
        ms = result["measured_sigma"]
        assert ms["cells_added"] == 1
        assert ms["added_cells"] == ["kalshi/golf"]
        assert ms["cells_at_bar_delta_vs_row_basis"] == -1

    def test_an_established_cell_is_not_counted_as_refuted(self):
        """The overlay must be capable of CONFIRMING a cell, not only killing
        one. polymarket/baseball measured 4.91 and stayed on the queue."""
        result = cs.score(_payload(20_500, 3.88), _ledger_with(0.1))
        cell = result["cells"][0]
        assert cell["verdict"] == cs.VERDICT_QUEUED == cell["verdict_row_basis"]
        assert result["measured_sigma"]["cells_refuted"] == 0
        assert result["sigma_overlay"]["cells_moved"] == []

    def test_unmeasured_cells_are_counted_not_assumed(self):
        payload = {
            "buckets": [
                _bucket("kalshi", "golf", 5, 20_500, int(20_500 * (0.5 - 0.0388)), 0.50),
                _bucket("kalshi", "other", 5, 20_500, int(20_500 * (0.5 - 0.0388)), 0.50),
            ],
            "mce_closing_line": 1.0,
            "population_version": "q268",
        }
        ms = cs.score(payload, _ledger_with(self.REFUTING_SE))["measured_sigma"]
        assert ms["material_cells_measured"] == 1
        assert ms["material_cells_unmeasured"] == 1

    def test_scoring_without_a_ledger_still_gives_the_pre_d62_board(self):
        """The row basis is not deleted, it is the documented fallback — and it
        is what runs when the committed ledger cannot be read."""
        without, _ = self._both()
        assert without["measured_sigma"]["decides"] is False
        assert without["cells"][0]["sigma_basis"] == cs.SIGMA_BASIS_ROW
        assert without["counts"]["cells_at_bar_row_basis"] == (
            without["counts"]["cells_at_bar"]
        )


class TestProofAndEstimateNeverShareAColumn:
    """Claim 5 — CAL-P127 lesson 10, enforced on the render."""

    def test_an_unmeasured_cell_renders_an_em_dash_not_its_row_sigma(self):
        payload = _payload(20_500, 3.88)
        md = cs.render_markdown(cs.score(payload, None), [])
        row = [l for l in md.splitlines() if "kalshi/golf" in l][0]
        assert "| — |" in row
        assert row.count("2.5") <= 1, "the row-grain sigma must not be reprinted"

    def test_a_measured_cell_that_left_the_queue_is_still_on_the_board(self):
        """AMENDED CAL-P1002. Before D62 a refuted cell stayed in the queued
        table wearing a 🔴; now the measurement takes it OFF the queue, so the
        queued table is exactly where it is no longer. A board that drops the
        rows its own correction removed cannot be used to check the correction
        — so the render prints them in their own table, with both sigmas.
        """
        md = cs.render_markdown(
            cs.score(_payload(20_500, 3.88), _ledger_with(0.5929493304062452)), []
        )
        assert "What the measurement changed" in md
        row = [l for l in md.splitlines() if "kalshi/golf" in l][0]
        assert "1.48" in row, "the measured sigma that moved it"
        assert "2.5" in row, "and the estimate it replaced, on the same row"
        assert cs.VERDICT_QUEUED in row and cs.VERDICT_UNDER_SIGMA in row

    def test_every_cell_carries_the_basis_that_produced_its_sigma(self):
        cell = cs.score(_payload(20_500, 3.88), None)["cells"][0]
        assert cell["sigma_basis"] == cs.SIGMA_BASIS_ROW


class TestTheLedgerDoesNotDriftFromTheBoard:
    def test_the_gate_is_imported_not_restated(self):
        """CAL-P115's rule. An equal copy drifts on the next edit."""
        e = ledger_mod.entry_from_sigma_json(GOLF_SIGMA_JSON, "x")
        assert e["as_measured"]["sigma_gate"] == cs.SIGMA_GATE

    def test_the_ledger_imports_nothing_from_the_scorecard(self):
        """One-way on purpose: `calibration_cluster_sigma` already imports the
        scorecard, and the scorecard imports the ledger. A back-edge here would
        close the cycle and break both.

        AMENDED CAL-P1002: the ledger now imports its own reading half from
        `app.utils.calibration_sigma`, so "no `calibration_` import at all" is
        no longer the test. The CYCLE is what the claim is about, and the app
        module is a leaf that imports nothing — so the test names the two
        scripts that would actually close it.
        """
        src = (_SCRIPTS / "calibration_sigma_ledger.py").read_text()
        # Import STATEMENTS, not prose — the docstring names the scorecard
        # repeatedly and should be free to.
        imports = [
            l.strip()
            for l in src.splitlines()
            if l.startswith(("import ", "from ")) or l.strip().startswith("import ")
        ]
        back_edges = [
            l
            for l in imports
            if "calibration_scorecard" in l or "calibration_cluster_sigma" in l
        ]
        assert not back_edges, back_edges
