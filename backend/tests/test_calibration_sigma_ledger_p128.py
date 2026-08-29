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
   set of rows. When the producer restages, the entry describes a population
   nobody is looking at, and reporting it anyway is gotcha #53 in ledger form.
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

    def test_a_missing_ledger_is_empty_not_an_error(self, tmp_path):
        assert ledger_mod.load(tmp_path / "nope.json")["entries"] == {}


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
        be able to make a cell MORE established, or it is not a measurement."""
        led = _ledger_with(0.6113)
        cell = cs.score(_payload(3252, 8.11), led)["cells"][0]
        assert cell["sigma_measured"] > cell["sigma"]

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

    def test_but_it_carries_no_verdict_at_all(self):
        """Not a hedged verdict — NO verdict. A field that sometimes means
        'probably' is how a caveat gets counted as a result two sessions on."""
        cell = cs.score(_payload(13135, 4.24), self._low_cov_ledger())["cells"][0]
        assert cell.get("measured_verdict") is None

    def test_it_is_counted_in_its_own_bucket_never_as_refuted(self):
        ms = cs.score(_payload(13135, 4.24), self._low_cov_ledger())["measured_sigma"]
        assert ms["queued_cells_low_coverage"] == 1
        assert ms["queued_cells_refuted"] == 0
        assert ms["queued_cells_measured"] == 0

    def test_a_low_coverage_cell_does_not_move_the_projection(self):
        r = cs.score(_payload(13135, 4.24), self._low_cov_ledger())
        assert (
            r["measured_sigma"]["cells_at_bar_if_applied"]
            == r["counts"]["cells_at_bar"]
        )

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
        """gotcha #53: the ledger returning a number is not the number applying."""
        led = _ledger_with(0.5, pop="q_OLD")
        cell = cs.score(_payload(20_500, 3.88, pop="q268"), led)["cells"][0]
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


class TestTheOverlayReportsAndDoesNotDecide:
    """Claim 4. The needle must not move because an instrument landed."""

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
        assert cell["sigma"] >= cs.SIGMA_GATE
        assert cell["sigma_measured"] < cs.SIGMA_GATE
        assert cell["verdict"] == cs.VERDICT_QUEUED
        assert cell["measured_verdict"] == cs.VERDICT_UNDER_SIGMA

    def test_the_verdict_does_not_move(self):
        without, with_ledger = self._both()
        assert with_ledger["cells"][0]["verdict"] == without["cells"][0]["verdict"]

    def test_the_needle_does_not_move(self):
        without, with_ledger = self._both()
        for k in ("cells_at_bar", "cells_queued", "cells_unestablished"):
            assert with_ledger["counts"][k] == without["counts"][k], k
        assert with_ledger["done"] == without["done"]

    def test_the_projection_is_reported_and_labelled_as_one(self):
        _, with_ledger = self._both()
        ms = with_ledger["measured_sigma"]
        assert ms["queued_cells_refuted"] == 1
        assert ms["refuted_cells"] == ["kalshi/golf"]
        # The projection differs from the reading — that IS the finding.
        assert ms["cells_at_bar_if_applied"] == with_ledger["counts"]["cells_at_bar"] + 1

    def test_an_established_cell_is_not_counted_as_refuted(self):
        """The overlay must be capable of CONFIRMING a cell, not only killing
        one. polymarket/baseball measured 4.91 and stayed on the queue."""
        _, _ = self._both()
        result = cs.score(_payload(20_500, 3.88), _ledger_with(0.1))
        assert result["cells"][0]["measured_verdict"] == cs.VERDICT_QUEUED
        assert result["measured_sigma"]["queued_cells_refuted"] == 0

    def test_unmeasured_queued_cells_are_counted_not_assumed(self):
        payload = {
            "buckets": [
                _bucket("kalshi", "golf", 5, 20_500, int(20_500 * (0.5 - 0.0388)), 0.50),
                _bucket("kalshi", "other", 5, 20_500, int(20_500 * (0.5 - 0.0388)), 0.50),
            ],
            "mce_closing_line": 1.0,
            "population_version": "q268",
        }
        ms = cs.score(payload, _ledger_with(self.REFUTING_SE))["measured_sigma"]
        assert ms["queued_cells_measured"] == 1
        assert ms["queued_cells_unmeasured"] == 1


class TestProofAndEstimateNeverShareAColumn:
    """Claim 5 — CAL-P127 lesson 10, enforced on the render."""

    def test_an_unmeasured_cell_renders_an_em_dash_not_its_row_sigma(self):
        payload = _payload(20_500, 3.88)
        md = cs.render_markdown(cs.score(payload, None), [])
        row = [l for l in md.splitlines() if "kalshi/golf" in l][0]
        assert "| — |" in row
        assert row.count("2.5") <= 1, "the row-grain sigma must not be reprinted"

    def test_a_measured_cell_renders_its_measured_sigma_and_flags_a_refusal(self):
        md = cs.render_markdown(
            cs.score(_payload(20_500, 3.88), _ledger_with(0.5929493304062452)), []
        )
        row = [l for l in md.splitlines() if "kalshi/golf" in l][0]
        assert "1.48" in row
        assert "🔴" in row, "a cell under the ratified gate must be visibly flagged"

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
        scorecard, and the scorecard now imports the ledger. A back-edge here
        would close the cycle and break both."""
        src = (_SCRIPTS / "calibration_sigma_ledger.py").read_text()
        # Import STATEMENTS, not prose — the docstring names the scorecard
        # repeatedly and should be free to.
        imports = [
            l.strip()
            for l in src.splitlines()
            if l.startswith(("import ", "from ")) or l.strip().startswith("import ")
        ]
        assert not [l for l in imports if "calibration_" in l], imports
