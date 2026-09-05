"""CAL-P1002 / D62 = A — the measured sigma decides, IN THE APP, and says so.

Alex ruled on 2026-09-04: the measured cluster-bootstrap standard error decides
which cells are on the calibration repair queue, and — D46's rule — it moves
into the app in the same change, so there is one honest figure rather than a
served needle and a script needle that disagree from day one.

``test_calibration_sigma_ledger_p128.py`` and ``test_calibration_sigma_carry_998.py``
hold the SEMANTICS of the flip (which statuses decide, what moves, what does
not). This file holds the four things that are specific to the overlay having
crossed into the app, each of which is a way the flip could be nominally shipped
and actually inert:

1. **The served block and the script agree, cell for cell.** The whole point of
   moving it. Two implementations agreeing today is exactly the state D46
   removed, so the test asserts the app's function is the one the script calls.
2. **The ledger is where the dyno can read it.** ``PROJECT_PATH=backend``: the
   repo-root ``artifacts/`` tree is not in the slug. A ledger outside
   ``backend/`` reads perfectly in CI and is absent on every production request
   — CAL-P129's defect in the one environment that serves readers, and the
   reason this file exists at all rather than a two-line diff.
3. **A ledger that cannot be read is LOUD.** It degrades to the row estimate,
   which is a defensible number, and it publishes the reason. The two bases
   differ by a whole cell on the live board; a reader must never be unable to
   tell which one they have.
4. **The receipt is on the wire.** ``cells_moved`` names every cell whose
   verdict the measurement changed, with both sigmas. A needle that moves
   because an instrument landed is how a board flatters itself; a needle that
   moves with its receipt attached is a measurement.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from app.utils import calibration_scoring as scoring
from app.utils import calibration_sigma as sigma

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS = _BACKEND / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = _load("calibration_scorecard")


# --------------------------------------------------------------------------
# Fixture — kalshi/golf, the cell D62 actually moves on the live board.
#
# Real numbers: 21,085 rows at 4.10 pp ECE against the 3.0 class-B bar is
# +1.10 excess, 3.19 sigma on `50/sqrt(n)` and 1.86 on the measured SE of
# 0.5929 pp. That is rank 3 of 14 by excess-outcomes, 23,194 of them, and it is
# the one cell that came off the queue when Alex flipped this.
# --------------------------------------------------------------------------

GOLF_N = 21_085
GOLF_ECE = 4.10
GOLF_SE_MEASURED = 0.5929
POP = "q269"


def _bucket(source, category, idx, n, winners, sum_prob_each):
    return {
        "source": source,
        "category": category,
        "bucket_idx": idx,
        "n": n,
        "winners": winners,
        "sum_prob": sum_prob_each * n,
    }


def _payload(n=GOLF_N, ece=GOLF_ECE, pop=POP):
    """One cell whose 10-bin ECE is ``ece`` pp, by construction."""
    return {
        "buckets": [
            _bucket("kalshi", "golf", 5, n, int(round(n * (0.50 - ece / 100))), 0.50)
        ],
        "mce_closing_line": 1.0,
        "population_version": pop,
        "generated_at": "2026-09-03T18:16:07+00:00",
    }


def _ledger(se=GOLF_SE_MEASURED, *, pop="q268", n_measured=20_500):
    """A ledger whose single entry reproduces its own sigma (``validate``)."""
    excess = round(GOLF_ECE - 3.0, 6)
    return {
        "schema": sigma.SCHEMA,
        "entries": {
            "kalshi/golf": {
                "source": "kalshi",
                "category": "golf",
                "population_version": pop,
                "generated_at": "2026-08-29T00:00:00Z",
                "se_bootstrap_pp": se,
                "se_row_pp": 0.3478,
                "variance_ratio_vs_board": 2.907,
                "effective_n": 7_053,
                "exact_coverage": 1.0081,
                "as_measured": {
                    "n": n_measured,
                    "excess": excess,
                    "sigma_bootstrap": excess / se,
                },
            }
        },
    }


# --------------------------------------------------------------------------
# 1. One definition — the served block and the script are the same code
# --------------------------------------------------------------------------


class TestTheServedNeedleAndTheScriptNeedleAreOneNumber:
    def test_the_script_calls_the_app_overlay_it_does_not_own_one(self):
        """IDENTITY, not equality (CAL-P115's rule, CAL-P998's direction).

        Two functions that agree today are precisely the state D46 removed; the
        app cannot import ``scripts/``, so a copy left in the script would be
        the second implementation of the gate.
        """
        assert cs.attach_measured_sigma is scoring.attach_measured_sigma
        assert cs.deciding_sigma is scoring.deciding_sigma
        assert cs.sigma_overlay is scoring.sigma_overlay
        assert cs.score_cells is scoring.score_cells

    def test_the_script_keeps_no_private_overlay(self):
        """The pre-D62 ``_attach_measured_sigma`` must be GONE, not shadowed."""
        assert not hasattr(cs, "_attach_measured_sigma")

    def test_the_two_needles_agree_on_the_same_payload(self):
        payload, led = _payload(), _ledger()
        served = scoring.scorecard(payload, ledger=led)
        script = cs.score(payload, led)
        # NON-VACUITY FIRST (CAL-P105): two boards where the overlay decided
        # nothing would agree perfectly and prove nothing. This fixture's whole
        # point is that the measurement moves the needle.
        assert served["cells_at_bar"] != served["cells_at_bar_row_basis"]
        assert served["cells_at_bar"] == script["counts"]["cells_at_bar"]
        assert served["cells_total"] == script["counts"]["cells_material"]
        assert served["cells_at_bar_row_basis"] == (
            script["counts"]["cells_at_bar_row_basis"]
        )
        assert served["sigma_overlay"] == script["sigma_overlay"]

    def test_the_needle_line_names_its_basis_and_carries_the_other_reading(self):
        """The NEEDLE-SPEC series changes DEFINITION on 2026-09-04 the way it
        did at the 2026-08-28 bar ratification. A point that cannot say which
        definition produced it makes the trend line lie about its units."""
        line = scoring.needle(scoring.scorecard(_payload(), ledger=_ledger()))
        assert scoring.SIGMA_BASIS_PER_CELL in line
        assert "row-basis" in line


class TestTheHistorySeriesCanTellTheTwoBasesApart:
    def test_the_same_curve_on_two_bases_banks_two_points(self, tmp_path):
        """The bars are in the history key because a re-score at a different
        finish line is a different reading. D62 makes the same true of the
        basis, and without it the first post-D62 point is silently refused as a
        duplicate — which is exactly what happened to the first ratified point
        before the bars were added.
        """
        path = tmp_path / "history.jsonl"
        payload = _payload()
        assert cs.record(cs.score(payload, None), path) == "recorded"
        assert cs.record(cs.score(payload, _ledger()), path) == "recorded"
        assert cs.record(cs.score(payload, _ledger()), path) == (
            "duplicate_curve_generated_at"
        ), "same curve, same bars, same basis is still a duplicate"

    def test_a_pre_d62_point_is_keyed_as_the_estimate_it_was_scored_against(self):
        """Never as "unknown": the pre-D62 history must not collide with a
        re-score, and it must not be re-labelled either."""
        legacy = {"generated_at": "2026-08-30T00:00:00Z", "thresholds": {}}
        assert cs._point_key(legacy)[2] == scoring.SIGMA_BASIS_ROW


# --------------------------------------------------------------------------
# 2. The ledger is somewhere the dyno can actually read it
# --------------------------------------------------------------------------


class TestTheLedgerIsInTheSlug:
    def test_it_lives_under_backend(self):
        """``PROJECT_PATH=backend`` with ``subdir-heroku-buildpack``: the
        buildpack promotes ``backend/`` to the slug root and discards
        everything beside it. A ledger at the repo root is not deployed."""
        assert _BACKEND in sigma.LEDGER_PATH.parents

    def test_it_is_inside_the_app_package_not_merely_inside_backend(self):
        """``backend/artifacts/`` is gitignored (it is a CWD accident, CERT-863)
        and ``backend/scripts/`` is not data. ``app/data/`` is where the app's
        other committed JSON lives, so "is it deployed" has the same answer as
        "is the app deployed"."""
        assert sigma.LEDGER_PATH.parent == _BACKEND / "app" / "data"

    def test_the_committed_ledger_is_there_and_coherent(self):
        led = sigma.load(sigma.LEDGER_PATH)
        assert led["schema"] == sigma.SCHEMA
        assert len(led["entries"]) >= 14, (
            "the ledger the SERVED needle now reads must be the real one"
        )
        assert sigma.validate(led) == []

    def test_the_old_repo_root_path_is_gone(self):
        """A leftover copy is worse than none: the builder would write one and
        the app would read the other, and they would drift silently."""
        stale = _BACKEND.parent / "artifacts" / "calibration-scorecard" / "measured-sigma.json"
        assert not stale.exists()

    def test_the_path_does_not_move_with_the_cwd(self, tmp_path, monkeypatch):
        """CAL-P129's claim, re-asserted at the new location."""
        before = sigma.LEDGER_PATH
        monkeypatch.chdir(tmp_path)
        import importlib

        assert importlib.reload(sigma).LEDGER_PATH == before


# --------------------------------------------------------------------------
# 3. A ledger that cannot be read is LOUD, and the fallback is named
# --------------------------------------------------------------------------


class TestAnUnreadableLedgerDegradesLoudly:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        sigma.load_default(refresh=True)
        yield
        sigma.load_default(refresh=True)

    def test_a_missing_ledger_gives_the_row_basis_and_a_reason(self, monkeypatch):
        monkeypatch.setattr(sigma, "LEDGER_PATH", _BACKEND / "nope" / "gone.json")
        led, reason = sigma.load_default(refresh=True)
        assert led is None
        assert reason.startswith(sigma.REASON_ABSENT)

        block = scoring.scorecard(_payload(), ledger=None, ledger_reason=reason)
        assert block["sigma_overlay"]["status"] == scoring.OVERLAY_UNAVAILABLE
        assert block["sigma_overlay"]["reason"] == reason
        assert block["sigma_overlay"]["decides"] is False
        assert block["bar"]["sigma_gate_basis"] == scoring.SIGMA_BASIS_ROW
        # And the number it fell back to is the pre-D62 one, not zero.
        assert block["cells_at_bar"] == block["cells_at_bar_row_basis"]

    def test_an_incoherent_ledger_is_refused_not_partially_applied(
        self, tmp_path, monkeypatch
    ):
        """A silently-wrong SE now moves cells across the ratified gate, in the
        direction that makes the board look shorter. Refusing beats degrading."""
        bad = _ledger()
        bad["entries"]["kalshi/golf"]["as_measured"]["sigma_bootstrap"] = 99.0
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(bad))
        monkeypatch.setattr(sigma, "LEDGER_PATH", p)
        led, reason = sigma.load_default(refresh=True)
        assert led is None
        assert reason.startswith(sigma.REASON_INCOHERENT)

    def test_bad_bytes_and_a_bad_measurement_are_different_reasons(
        self, tmp_path, monkeypatch
    ):
        """``json.JSONDecodeError`` IS a ``ValueError``, so one catch would file
        a truncated file as "an entry cannot reproduce its own sigma" — a claim
        about the measurement, when the truth is a claim about the file. The
        reasons are published, so a reader acts on the difference."""
        p = tmp_path / "truncated.json"
        p.write_text('{"schema": 1, "entries": {"kalshi/gol')
        monkeypatch.setattr(sigma, "LEDGER_PATH", p)
        led, reason = sigma.load_default(refresh=True)
        assert led is None
        assert reason.startswith(sigma.REASON_MALFORMED)
        assert not reason.startswith(sigma.REASON_INCOHERENT)

    def test_the_route_never_loses_the_curve_over_a_ledger(self, monkeypatch):
        """Ruling CAL-P017 is standing: a score never costs the reader the
        curve. The ledger is read inside the scorecard, so a raise there would
        take out the block on the very fallback tiers that exist so the page
        does not go dark."""

        def _boom(**kwargs):
            raise OSError("disk gone")

        monkeypatch.setattr(sigma, "load", _boom)
        led, reason = sigma.load_default(refresh=True)
        assert led is None and reason.startswith(sigma.REASON_UNREADABLE)
        block = scoring.scorecard(_payload())
        assert block["status"] == scoring.STATUS_MEASURED
        assert block["cells_at_bar"] is not None

    def test_asking_for_no_ledger_is_distinguishable_from_failing_to_get_one(self):
        """"No ledger because you asked" and "no ledger because it is missing"
        are different facts and only one of them is a problem."""
        block = scoring.scorecard(_payload(), load_ledger=False)
        assert block["sigma_overlay"]["reason"] == "ledger_not_requested"
        assert not block["sigma_overlay"]["reason"].startswith(sigma.REASON_ABSENT)

    def test_the_default_read_is_memoised_per_process(self, monkeypatch):
        """The committed ledger changes on deploy. Re-reading it per request
        would put a filesystem call on ``/api/calibration``'s tier-1 path — the
        one that answers from process memory with no database work at all."""
        sigma.load_default(refresh=True)
        calls = {"n": 0}
        real = sigma.load

        def _counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(sigma, "load", _counting)
        sigma.load_default(refresh=True)
        sigma.load_default()
        sigma.load_default()
        assert calls["n"] == 1


# --------------------------------------------------------------------------
# 4. The receipt — the flip is auditable from the served payload alone
# --------------------------------------------------------------------------


class TestTheServedBlockCarriesItsOwnReceipt:
    def test_the_moved_cell_is_named_with_both_sigmas(self):
        block = scoring.scorecard(_payload(), ledger=_ledger())
        moved = block["sigma_overlay"]["cells_moved"]
        assert [m["cell"] for m in moved] == ["kalshi/golf"]
        m = moved[0]
        assert m["sigma_row"] == pytest.approx(3.19, abs=0.02)
        assert m["sigma_measured"] == pytest.approx(1.86, abs=0.02)
        assert m["from"] == scoring.VERDICT_QUEUED
        assert m["to"] == scoring.VERDICT_UNDER_SIGMA

    def test_a_queued_row_never_prints_one_sigma_without_saying_which(self):
        """CAL-P127 lesson 10 on the wire: a bare ``sigma`` was unambiguous
        while only one quantity existed. Since D62 it is not."""
        block = scoring.scorecard(_payload(2_000, 9.0), ledger=_ledger())
        assert block["queued_cells"], "fixture must queue something"
        for row in block["queued_cells"]:
            assert row["sigma_basis"] in (
                scoring.SIGMA_BASIS_ROW,
                scoring.SIGMA_BASIS_MEASURED,
            )
            assert row["sigma_row"] is not None
            if row["sigma_basis"] == scoring.SIGMA_BASIS_MEASURED:
                assert row["sigma"] == row["sigma_measured"]
            else:
                assert row["sigma"] == row["sigma_row"]

    def test_the_authority_is_on_the_wire(self):
        """A served field that changed what it means names the decision that
        changed it, so a consumer reading an old cached shape can tell."""
        block = scoring.scorecard(_payload(), ledger=_ledger())
        assert "D62" in block["sigma_overlay"]["authority"]

    def test_the_remeasure_backlog_is_published_not_described(self):
        """Every carried entry is a standing request to re-measure. The
        measurement lane reads it off the wire instead of a handoff note."""
        block = scoring.scorecard(_payload(), ledger=_ledger())
        assert block["sigma_overlay"]["remeasure_backlog"] == ["kalshi/golf"]
        assert block["sigma_overlay"]["carried_from_populations"] == ["q268"]

    def test_an_exempt_cell_can_never_appear_as_moved(self):
        """The floor is checked before the sigma, so an exempt cell's verdict is
        identical on both bases by construction. 277 rows that cannot move would
        bury the ones that did."""
        block = scoring.scorecard(_payload(500, 40.0), ledger=_ledger())
        assert block["cells_exempt"] >= 1
        assert block["sigma_overlay"]["cells_moved"] == []

    def test_the_delta_matches_the_receipt(self):
        """The published delta and the named list must be the same fact. A
        delta of +1 with an empty ``cells_moved`` is the shape of a number that
        moved for a reason nobody recorded."""
        block = scoring.scorecard(_payload(), ledger=_ledger())
        moved = block["sigma_overlay"]["cells_moved"]
        # `0 == 0 - 0` on a board where nothing moved is not evidence of
        # anything, and it is exactly what an inert overlay produces.
        assert moved, "fixture must move a cell or this test is vacuous"
        off = sum(1 for m in moved if m["to"] != scoring.VERDICT_QUEUED)
        on = sum(1 for m in moved if m["to"] == scoring.VERDICT_QUEUED)
        assert block["cells_at_bar_delta_vs_row_basis"] == off - on != 0
