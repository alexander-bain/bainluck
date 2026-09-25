"""#8530 step 3 — the history repair's gates, without a database.

The round trip itself runs against real Postgres in
`tests/integration/test_repair_8530_ufc_history_roundtrip_real_postgres.py`.
These pin what decides whether that write may happen at all.
"""
import importlib.util
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "repair_8530_ufc_flipped_history.py"
_spec = importlib.util.spec_from_file_location("repair_8530", SCRIPT)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


def test_only_the_heavy_app_may_write():
    assert repair.app_is_permitted("bainluck-heavy")[0] is True
    for other in ("bainluck", None, "", "bainluck-heavy-staging"):
        assert repair.app_is_permitted(other)[0] is False


def test_the_writer_gate_passes_on_an_image_carrying_8534():
    ok, why = repair.writer_is_corrected()
    assert ok, why


def test_kalshi_verdict_reads_both_arms_of_the_recorded_outcome():
    v = repair.kalshi_row_verdict
    # outcome names the HOME fighter: correct home = yes
    assert v("Montel Jackson", "Ricky Simon", 0.655, "Montel Jackson", 0.655) == "OK"
    assert v("Montel Jackson", "Ricky Simon", 0.345, "Montel Jackson", "0.655") == "FLIP"
    # outcome names the AWAY fighter: correct home = 1 - yes
    assert v("Vanessa Demopoulos", "Yazmin Jauregui", 0.125, "Yazmin Jauregui", 0.875) == "OK"
    assert v("Vanessa Demopoulos", "Yazmin Jauregui", 0.875, "Yazmin Jauregui", 0.875) == "FLIP"
    # neither the right value nor its complement: left alone
    assert v("Montel Jackson", "Ricky Simon", 0.5, "Montel Jackson", 0.655) == "UNEXPLAINED"


def test_kalshi_verdict_fails_open_on_absent_or_foreign_evidence():
    v = repair.kalshi_row_verdict
    assert v("Montel Jackson", "Ricky Simon", 0.345, None, 0.655) == "NO_EVIDENCE"
    assert v("Montel Jackson", "Ricky Simon", 0.345, "Montel Jackson", None) == "NO_EVIDENCE"
    assert v("Montel Jackson", "Ricky Simon", 0.345, "Somebody Else", 0.655) == "NO_EVIDENCE"
    assert v("Montel Jackson", "Ricky Simon", 0.345, "Montel Jackson", "n/a") == "NO_EVIDENCE"


def test_odds_verdict_checks_the_window_against_the_corrected_favourite():
    v = repair.odds_row_verdict
    assert v(15314293, 0.4066) == "FLIP"          # Vieira is the favourite; row says 41%
    assert v(15314293, 0.5934) == "UNEXPLAINED"   # already right: the window is wrong
    assert v(15314294, 0.8677) == "FLIP"          # Jauregui is the favourite
    assert v(15314294, 0.1323) == "UNEXPLAINED"
    assert v(15314293, None) == "NO_PROB"
    assert v(15314293, 0.5) == "EVEN"


def test_apply_refuses_while_any_window_row_contradicts_the_flip():
    assert repair.apply_refusal({"odds": {"FLIP": [1]}}) is None
    assert repair.apply_refusal({"odds": {"FLIP": [1], "UNEXPLAINED": [2]}})
    assert repair.apply_refusal({"odds": {"EVEN": [3]}})


def test_the_swap_is_an_involution_over_every_sided_column():
    for swap in (repair.ODDS_SWAP, repair.WP_SWAP):
        cols = {c for c, _ in swap}
        for col, expr in swap:
            src = expr.replace("-", "").replace("b.", "")
            assert src in cols, (col, expr)
            back = dict(swap)[src]
            assert back.replace("-", "").replace("b.", "") == col
    assert not any("over" in c or "under" in c for c, _ in repair.ODDS_SWAP)


def test_dry_run_opens_no_connection_and_exits_zero():
    out = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"],
                         capture_output=True, text=True, cwd=SCRIPT.parents[1], timeout=120)
    assert out.returncode == 0, out.stderr
    assert "dry run, no database connection opened" in out.stdout
    assert "app gate     : REFUSE" in out.stdout
