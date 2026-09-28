"""Exercise real runner selectors on scratch receipts, never the live loops."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Retained stale presentation, including the long metadata gap before status.
STALE = """queue_id: C-LIVE-034-SSE-WEB-PUSH-2
cert_id: CERT-742
staged_by: live (036)
staged_at: 2026-09-02 ~04:5x PT
branch: live/034-sse-live-push-web
sha: 8de141ad4929ca67fa45b9d77346ca47562f8ab4
base: origin/master b95c8087 (38 behind / 10 ahead)
merge_tree: exit 0, 0 conflicts, tree a058c8ea
pr: 2632
ci: GREEN at 8de141ad — run 33624931416 (backend-tests 1/2/3/4, shard-completeness,
    frontend-build, search-recall, Browser-audit contract fixtures), CodeQL +
    Analyze python/js 33624931635, gitleaks 33624925477 + 33624931604; deploy
    skipping; ZERO non-passing, jobs read individually not from the rollup
files: 3, frontend only — backend/ and ios/ diff is EMPTY
status: staged

# CERT-742 -- C-LIVE-034-SSE-WEB-PUSH-2

**THE REPAIR OF CERT-717. Strike two in that chain.**
"""
BANKED = "| CERT-742 -- C-LIVE-034-SSE-WEB-PUSH-2 | 2026-09-02 11:56Z | live (036; CERT-717 repair) | **GREEN -- TOKEN GRANTED** | Token granted for `8de141ad`. |\n"


def pending(tmp_path, queue, ledger=""):
    (tmp_path / "queue").write_text(queue)
    (tmp_path / "ledger").write_text(ledger)
    script = (ROOT / "lane4-runner.sh").read_text()
    selector = script.split("pending () {", 1)[1].split("\nverdicts ()", 1)[0]
    # Isolate the actual selector; stale-claim reset is a separate existing
    # mutation and must never touch the real queue during this regression test.
    code = '''Q="$1/queue"; CERTLOG="$1/ledger"
TERMINAL="done superseded withdrawn withdrawn-by-author parked-mismatch"
reset_stale () { :; }
pending () {''' + selector + "\npending\n"
    result = subprocess.run(
        ["bash", "-c", code, "test", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "queue").read_text() == queue
    assert (tmp_path / "ledger").read_text() == ledger
    return result.stdout.strip(), result.stderr


def test_exact_banked_stale_fragment_drains(tmp_path):
    assert pending(tmp_path, STALE, BANKED) == ("", "")


def test_banked_fragment_does_not_hide_following_unterminated_repair(tmp_path):
    queue = STALE + 'queue_id: "C-LIVE-NEW-REPAIR"\ncert_id: CERT-9397\nrepairs: CERT-742\nstatus: staged'
    assert pending(tmp_path, queue, BANKED)[0] == "C-LIVE-NEW-REPAIR"


def test_new_cert_presentation_can_reuse_queue_slug(tmp_path):
    queue = STALE.replace("cert_id: CERT-742", "cert_id: CERT-9397")
    assert pending(tmp_path, queue, BANKED)[0] == "C-LIVE-034-SSE-WEB-PUSH-2"


@pytest.mark.parametrize("verdict", ["GREEN", "BLOCK"])
def test_queue_identity_banks_when_cert_id_is_absent(tmp_path, verdict):
    queue = STALE.replace("cert_id: CERT-742\n", "")
    assert pending(tmp_path, queue, BANKED.replace("GREEN", verdict))[0] == ""


@pytest.mark.parametrize("ledger", [
    "| CERT-BUS-STATUS | now | bus | **DRAINED** | CERT-742 -- C-LIVE-034-SSE-WEB-PUSH-2 |",
    "| CERT-9397 -- C-OTHER | now | bus | **GREEN** | Repairs CERT-742 -- C-LIVE-034-SSE-WEB-PUSH-2 |",
    "| CERT-742 -- C-LIVE-034-SSE-WEB-PUSH-2 | now | bus | **DRAINED** | no merits verdict |",
    "| CERT-7420 -- C-LIVE-034-SSE-WEB-PUSH-20 | now | bus | **GREEN** | distinct |",
])
def test_mentions_and_partial_identity_do_not_bank_subject(tmp_path, ledger):
    assert pending(tmp_path, STALE, ledger)[0] == "C-LIVE-034-SSE-WEB-PUSH-2"


@pytest.mark.parametrize("status", ["done", "superseded", "withdrawn", "withdrawn-by-author", "parked-mismatch", "running"])
def test_terminal_or_claimed_subject_remains_quiet(tmp_path, status):
    assert pending(tmp_path, STALE.replace("status: staged", "status: " + status))[0] == ""


def test_malformed_adjacent_and_eof_blocks_are_reported(tmp_path):
    queue = "queue_id: C-BAD\nqueue_id: C-GOOD\nstatus: staged\n"
    out, err = pending(tmp_path, queue)
    assert out == "C-GOOD"
    assert "MALFORMED C-BAD" in err
    assert pending(tmp_path, "status: staged\nqueue_id: C-TAIL")[1].strip() == "MALFORMED C-TAIL"


def bus(tmp_path, expression):
    script = (ROOT / "bus-runner.sh").read_text()
    # No startup commands, actual runner loop, drift probe, or live directories.
    definitions = script.split('MAX_TRIES=', 1)[1].split('\necho "[bus] measurement bus up.', 1)[0]
    result = subprocess.run(
        ["bash", "-c", 'H="$1"; MAX_TRIES=' + definitions + "\n" + expression, "test", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_only_launch_week_missions_are_due_and_can_drain(tmp_path):
    assert bus(tmp_path, 'missing 20260928-16').splitlines() == ["FRESH", "CLAIMS", "THRU-BASELINE"]
    for mission in ("FRESH", "CLAIMS", "THRU-BASELINE"):
        (tmp_path / f"ARTIFACT-M-R-{mission}-20260928-16.md").write_text("done")
    # No daily authority ledger or suspended mission receipts: still drained.
    assert bus(tmp_path, 'missing 20260928-16') == ""
    assert bus(tmp_path, 'missing 20260928-17').splitlines() == ["FRESH", "CLAIMS", "THRU-BASELINE"]


def test_bus_prompt_carries_amended_scope_and_exact_bucket(tmp_path):
    prompt = bus(tmp_path, 'prompt_for 20260928-16 "THRU-BASELINE"')
    assert "health + curve generated_at + heavy app commit" in prompt
    assert "discover_marquee_final" in prompt
    assert "ARTIFACT-M-R-<NAME>-20260928-16.md" in prompt
    assert "M-R-AUTHORITY is the exception" not in prompt


def test_non_c_queue_slug_uses_exact_ledger_identity(tmp_path):
    queue = "queue_id: D106-FIXTURE-IDENTITY\nstatus: staged\n"
    ledger = "| CERT-2418 -- D106-FIXTURE-IDENTITY | now | lane | **GREEN** | proof |"
    assert pending(tmp_path, queue, ledger)[0] == ""


@pytest.mark.parametrize("position", ["before", "after"])
def test_new_heading_presentation_does_not_inherit_predecessor_verdict(tmp_path, position):
    queue = 'queue_id: C-LIVE-034-SSE-WEB-PUSH-2\nstatus: staged\nrepairs: CERT-742\n'
    heading = '# CERT-9397 -- C-LIVE-034-SSE-WEB-PUSH-2\n'
    queue = heading + queue if position == "before" else queue + heading
    assert pending(tmp_path, queue, BANKED)[0] == "C-LIVE-034-SSE-WEB-PUSH-2"
