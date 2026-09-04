"""CAL-P998 — guards for CARRIED: a measured SE survives a republish.

WHAT WENT WRONG, MEASURED BEFORE THIS FILE WAS WRITTEN
------------------------------------------------------
On 2026-09-03 the live board read **0 of 14 queued cells measured** while
``artifacts/calibration-scorecard/measured-sigma.json`` held **14 committed
entries**. Every entry was banked against population ``q268``; production
served ``q269``; :func:`calibration_sigma_ledger.lookup` tested the two version
strings for identity and returned ``STALE`` for all fourteen. So the overlay —
the whole apparatus CAL-P128 built to stop the board feeding a row-grain
estimate into a standard-error gate — covered nothing at all, and the queue Alex
is steered by ran entirely on the estimate the overlay exists to correct.

The fix is a NARROWING, not a loosening, and the difference is the whole point
of this file. ``population_version`` is a proxy for "did this cell's rows
change"; the payload answers that question directly with ``n``. On the q268 ->
q269 board the two facts the proxy conflates separate cleanly:

    kalshi/golf          20,500 -> 21,085   +2.9%     same cell
    kalshi/tech           1,203 ->  1,246   +3.6%     same cell
    kalshi/entertainment  8,355 ->  8,922   +6.8%     same cell
    polymarket/cricket    3,252 ->  2,944    -9.5%    same cell (near the edge)
    polymarket/hockey     2,281 ->  1,730   -24.2%    NOT the same cell
    polymarket/economics 12,882 ->  9,656   -25.0%    NOT the same cell
    polymarket/golf       6,463 ->  4,339   -32.9%    NOT the same cell
    polymarket/basketball 13,135 -> 7,591   -42.2%    NOT the same cell

THE FIVE CLAIMS PINNED HERE
---------------------------
1. **A carried entry is not a fresh one.** ``CARRIED`` is its own status, its
   own count and its own projection, and it prints its measured population on
   the row. If it could be read as ``FRESH`` anywhere, the narrowing would have
   become "apply everything".
2. **A cell that MOVED is still refused.** The half of the old rule that was
   doing real work keeps working, and the polymarket cells above are the proof
   that this is not hypothetical.
3. **An untestable drift is refused.** No ``n`` on the payload side or none
   stored on the entry means the claim cannot be checked, and an unchecked
   claim fails closed (gotcha #53).
4. **The needle does not move.** ``cells_at_bar``, ``cells_queued``, ``done``
   and every cell ``verdict`` are identical with and without the carry rule.
   Claim 4 of CAL-P128 is unchanged: the flip is Alex's call, and a status
   landing must not make it for him.
5. **The projection splits back into its two halves.** ``_if_applied`` (fresh
   only) and ``_if_applied_with_carried`` are separate numbers, because the two
   halves are not equally strong evidence and a reader must be able to see
   which one is doing the work.
"""

from __future__ import annotations

import copy
import importlib.util
import pathlib

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ledger_mod = _load("calibration_sigma_ledger")
cs = _load("calibration_scorecard")


# --------------------------------------------------------------------------
# The real kalshi/golf measurement (CAL-P127, q268) against the real q269
# payload. Real numbers because the cell this file changes the reading of IS
# rank 3 on the live board: 21,085 rows, ECE 4.10, 23,194 excess-outcomes.
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

#: The live q269 reading of the same cell. +2.9% on n — the drift the rule is
#: about.
N_Q269 = 21085
ECE_Q269 = 4.10


def _entry(pop="q268", n_measured=20500, coverage_n_exact=20666):
    obj = copy.deepcopy(GOLF_SIGMA_JSON)
    obj["payload"]["population_version"] = pop
    obj["payload"]["n"] = n_measured
    obj["exact"]["n"] = coverage_n_exact
    return ledger_mod.entry_from_sigma_json(obj, "test")


def _ledger(**kw):
    e = _entry(**kw)
    return {"schema": ledger_mod.SCHEMA, "entries": {"kalshi/golf": e}}


def _bucket(source, category, idx, n, winners, avg_prob):
    return {
        "bucket_idx": idx,
        "source": source,
        "category": category,
        "price_moved": False,
        "n": n,
        "winners": winners,
        "avg_prob": avg_prob,
        "sum_prob": n * avg_prob,
    }


def _payload(n, ece_pp, source="kalshi", category="golf", pop="q269"):
    winners = int(round(n * (0.5 - ece_pp / 100)))
    return {
        "buckets": [_bucket(source, category, 5, n, winners, 0.50)],
        "mce_closing_line": 1.0,
        "population_version": pop,
        "total_outcomes": n,
    }


# --------------------------------------------------------------------------
# Claim 1 — a carried entry is not a fresh one
# --------------------------------------------------------------------------


class TestCarriedIsItsOwnStatus:
    def test_an_unmoved_cell_on_a_new_population_is_carried(self):
        entry, status = ledger_mod.lookup(
            _ledger(), "kalshi", "golf", "q269", N_Q269
        )
        assert status == ledger_mod.STATUS_CARRIED
        assert entry["se_bootstrap_pp"] == GOLF_SIGMA_JSON["se"]["bootstrap"]

    def test_carried_is_not_the_same_value_as_fresh(self):
        """If these ever collapse, every consumer's split silently merges."""
        assert ledger_mod.STATUS_CARRIED != ledger_mod.STATUS_FRESH

    def test_a_matching_population_is_still_fresh_not_carried(self):
        """The control. The pre-existing path must not have moved."""
        _, status = ledger_mod.lookup(_ledger(), "kalshi", "golf", "q268", 20500)
        assert status == ledger_mod.STATUS_FRESH

    def test_the_board_marks_the_carried_cell_with_its_population(self):
        cell = cs.score(_payload(N_Q269, ECE_Q269), _ledger())["cells"][0]
        assert cell["sigma_ledger_status"] == ledger_mod.STATUS_CARRIED
        assert cell["measured_carried"] is True
        assert cell["measured_at_population"] == "q268"
        assert cell["measured_generated_at"] == GOLF_SIGMA_JSON["payload"]["generated_at"]
        assert cell["carried_drift"] == round(N_Q269 / 20500, 4)

    def test_the_rendered_row_says_which_population_it_came_from(self):
        """Claim 5 of CAL-P128 is about the COLUMN, not about the summary line.

        A reader scanning the sigma-meas column must not have to remember a
        bullet three lines up to know that 1.86 was measured somewhere else.
        """
        md = cs.render_markdown(cs.score(_payload(N_Q269, ECE_Q269), _ledger()), [])
        assert "↩q268" in md

    def test_a_carried_cell_is_counted_apart_from_a_measured_one(self):
        """AMENDED CAL-P1002 — the claim survives the flip and is the reason
        ``CARRIED`` was not folded into ``FRESH`` when it started deciding.
        Both decide; only one was measured on the population being scored, and
        a count that cannot be split back into those halves is a count nobody
        can audit. The buckets are now over MATERIAL cells, because a cell the
        overlay takes OFF the queue is no longer a queued cell — counting the
        overlay's coverage over the queue would make it shrink as it succeeds.
        """
        ms = cs.score(_payload(N_Q269, ECE_Q269), _ledger())["measured_sigma"]
        assert ms["material_cells_carried"] == 1
        assert ms["carried_cells"] == ["kalshi/golf"]
        assert ms["carried_from_populations"] == ["q268"]
        # ...and specifically NOT here:
        assert ms["material_cells_measured"] == 0
        assert ms["refuted_cells"] == []

    def test_a_carried_cell_is_not_counted_as_unmeasured_either(self):
        """The four buckets partition the material cells. A cell that fell into
        two of them, or into none, would make the summary line add up to a
        different board than the table under it."""
        r = cs.score(_payload(N_Q269, ECE_Q269), _ledger())
        ms = r["measured_sigma"]
        assert (
            ms["material_cells_measured"]
            + ms["material_cells_carried"]
            + ms["material_cells_low_coverage"]
            + ms["material_cells_unmeasured"]
            == ms["material_cells"]
            == r["counts"]["cells_material"]
        )


# --------------------------------------------------------------------------
# Claim 2 / 3 — the refusals that must survive
# --------------------------------------------------------------------------


class TestTheRefusalsSurvive:
    def test_a_cell_that_shrank_past_the_band_is_stale(self):
        """`polymarket/basketball` 13,135 -> 7,591 is CAL-P126's phantom
        duplication being removed: the population really did change, and no
        version string is needed to see it."""
        _, status = ledger_mod.lookup(
            _ledger(n_measured=13135), "kalshi", "golf", "q269", 7591
        )
        assert status == ledger_mod.STATUS_STALE

    def test_a_cell_that_grew_past_the_band_is_stale(self):
        """Two-sided. A cell that doubled is no more the measured cell than one
        that halved, and a one-sided band would carry it."""
        _, status = ledger_mod.lookup(
            _ledger(n_measured=10000), "kalshi", "golf", "q269", 20000
        )
        assert status == ledger_mod.STATUS_STALE

    def test_an_uncomputable_drift_is_stale_not_carried(self):
        """gotcha #53 — an untestable claim fails closed."""
        assert (
            ledger_mod.lookup(_ledger(), "kalshi", "golf", "q269", None)[1]
            == ledger_mod.STATUS_STALE
        )
        entry_without_n = _entry()
        entry_without_n["as_measured"]["n"] = None
        led = {"schema": ledger_mod.SCHEMA, "entries": {"kalshi/golf": entry_without_n}}
        assert (
            ledger_mod.lookup(led, "kalshi", "golf", "q269", N_Q269)[1]
            == ledger_mod.STATUS_STALE
        )

    def test_a_caller_that_does_not_pass_n_gets_the_pre_amendment_behaviour(self):
        """The new argument is opt-in. A default that silently carried would
        make the status reachable by callers that never asked for it."""
        assert (
            ledger_mod.lookup(_ledger(), "kalshi", "golf", "q269")[1]
            == ledger_mod.STATUS_STALE
        )

    def test_population_divergence_outranks_carrying(self):
        """A cell whose rail and payload describe different populations has no
        sigma to offer, and that is true whether the entry is fresh or carried.
        Ordering matters: carried-then-diverged must not report a verdict."""
        led = _ledger(coverage_n_exact=5000)  # coverage 0.24, far outside the band
        entry, status = ledger_mod.lookup(led, "kalshi", "golf", "q269", N_Q269)
        assert status == ledger_mod.STATUS_POPULATION_DIVERGENCE
        cell = cs.score(_payload(N_Q269, ECE_Q269), led)["cells"][0]
        assert "measured_verdict" not in cell
        assert cell.get("measured_carried") is None

    def test_the_two_bands_are_the_same_question_and_the_same_width(self):
        """Not an equality for its own sake: if these ever diverge, one axis of
        'is this the same cell' is being asked at a different strictness from
        the other, and the reason had better be written down."""
        assert ledger_mod.CELL_DRIFT_BAND == ledger_mod.COVERAGE_BAND

    def test_the_band_admits_the_live_kalshi_drifts_and_refuses_the_poly_ones(self):
        """The empirical warrant, executable. These eight are the live q268 ->
        q269 board; the rule must split them the way the amendment says."""
        lo, hi = ledger_mod.CELL_DRIFT_BAND
        carried = {"golf": (20500, 21085), "tech": (1203, 1246),
                   "entertainment": (8355, 8922), "cricket": (3252, 2944)}
        stale = {"hockey": (2281, 1730), "economics": (12882, 9656),
                 "poly_golf": (6463, 4339), "basketball": (13135, 7591)}
        for name, (was, now) in carried.items():
            assert lo <= now / was <= hi, f"{name} should carry"
        for name, (was, now) in stale.items():
            assert not (lo <= now / was <= hi), f"{name} should NOT carry"


# --------------------------------------------------------------------------
# Claim 4 — the needle does not move
# --------------------------------------------------------------------------


class TestACarriedEntryDecides:
    """CAL-P128 claim 4 as Alex left it on 2026-09-04 (D62 = A).

    The class was ``TestTheNeedleDoesNotMove`` and it said: a status landing
    must not decide anything Alex has not flipped. He flipped it. The half that
    survives — and it is the load-bearing half — is that the needle moves for
    exactly one reason and names the rows it moved for. This class is the
    CARRIED half of that, and it is the half that matters on the live board:
    all four measured queued cells on 2026-09-04 are carried from ``q268`` and
    not one is fresh, so an overlay that decided only on ``FRESH`` would have
    been a no-op on the board D62 was ruled for.
    """

    def _both(self):
        payload = _payload(N_Q269, ECE_Q269)
        return cs.score(payload, None), cs.score(payload, _ledger())

    def test_cells_at_bar_moves_by_one_and_the_row_basis_records_where_from(self):
        without, with_carry = self._both()
        assert with_carry["counts"]["cells_at_bar"] == (
            without["counts"]["cells_at_bar"] + 1
        )
        assert with_carry["counts"]["cells_at_bar_row_basis"] == (
            without["counts"]["cells_at_bar"]
        )

    def test_the_cell_verdict_moves_on_the_carried_measurement(self):
        without, with_carry = self._both()
        assert without["cells"][0]["verdict"] == cs.VERDICT_QUEUED
        cell = with_carry["cells"][0]
        assert cell["verdict"] == cs.VERDICT_UNDER_SIGMA
        assert cell["sigma_basis"] == cs.SIGMA_BASIS_MEASURED
        assert cell["measured_carried"] is True

    def test_the_move_names_the_population_it_was_measured_on(self):
        """The residual a size test cannot cover is a question about AGE, so
        the answer rides on the moved row rather than in a docstring."""
        _, with_carry = self._both()
        moved = with_carry["sigma_overlay"]["cells_moved"]
        assert [m["cell"] for m in moved] == ["kalshi/golf"]
        assert moved[0]["ledger_status"] == ledger_mod.STATUS_CARRIED
        assert moved[0]["measured_at_population"] == "q268"

    def test_the_carried_cell_is_refuted_at_the_gate_and_leaves_the_queue(self):
        """The substance: rank 3 reads 3.2 sigma on rows and 1.86 measured —
        under the ratified gate — and is STILL queued, because the overlay
        reports and does not decide."""
        cell = cs.score(_payload(N_Q269, ECE_Q269), _ledger())["cells"][0]
        assert cell["sigma_row"] > cs.SIGMA_GATE
        assert cell["sigma_measured"] < cs.SIGMA_GATE
        assert cell["verdict_row_basis"] == cs.VERDICT_QUEUED
        assert cell["verdict"] == cs.VERDICT_UNDER_SIGMA


# --------------------------------------------------------------------------
# Claim 5 — the projection splits back into its halves
# --------------------------------------------------------------------------


class TestTheTwoHalvesStayApartEvenThoughBothDecide:
    """AMENDED CAL-P1002. The class was ``TestTheProjectionKeepsItsHalvesApart``
    and it guarded two projections, ``_if_applied`` and
    ``_if_applied_with_carried``, which existed because the flip was Alex's
    call and the two halves of the evidence are not equally strong. He took the
    weaker one too, so there is one reading and one counterfactual (the row
    basis) — but the SPLIT is still owed, because it is the re-measure backlog
    and because a reader must be able to see how much of the needle rests on
    measurements taken against a population that is no longer served.
    """

    def test_a_carried_refutation_moves_the_needle_and_stays_labelled_carried(self):
        r = cs.score(_payload(N_Q269, ECE_Q269), _ledger())
        ms, counts = r["measured_sigma"], r["counts"]
        assert ms["refuted_cells_carried"] == ["kalshi/golf"]
        assert ms["refuted_cells"] == [], "not pooled into the fresh bucket"
        assert ms["cells_refuted"] == 1, "but counted in the total"
        assert counts["cells_at_bar"] == counts["cells_at_bar_row_basis"] + 1

    def test_a_fresh_refutation_lands_in_the_other_bucket_and_moves_it_the_same(self):
        """The control: a FRESH entry moves the needle identically, so the
        split is about PROVENANCE and never about how much a cell counts."""
        led = _ledger(pop="q269", n_measured=N_Q269)
        r = cs.score(_payload(N_Q269, ECE_Q269), led)
        ms = r["measured_sigma"]
        assert ms["material_cells_measured"] == 1 and ms["material_cells_carried"] == 0
        assert ms["refuted_cells"] == ["kalshi/golf"]
        assert ms["refuted_cells_carried"] == []
        assert r["counts"]["cells_at_bar"] == (
            r["counts"]["cells_at_bar_row_basis"] + 1
        )

    def test_an_established_carried_cell_moves_nothing(self):
        """A carried SE that CONFIRMS the queue must not shorten the board. The
        correction runs in both directions (CAL-P128 claim 2) and cricket is
        the live cell where it raises the sigma."""
        led = _ledger(n_measured=3252, coverage_n_exact=3252)
        led["entries"]["kalshi/golf"]["se_bootstrap_pp"] = 0.6113365041126125
        r = cs.score(_payload(2944, 7.92), led)
        ms = r["measured_sigma"]
        assert ms["material_cells_carried"] == 1
        assert ms["cells_refuted"] == 0 and ms["cells_added"] == 0
        assert r["counts"]["cells_at_bar"] == r["counts"]["cells_at_bar_row_basis"]
        assert r["sigma_overlay"]["cells_moved"] == []
