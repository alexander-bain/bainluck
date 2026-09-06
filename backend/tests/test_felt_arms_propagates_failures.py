"""LAT-P238-PROPAGATE-ARM-FAILURES — `tools/felt-arms.sh` must not exit 0 on a dead arm.

CERT-1964 granted the boot-rail A/B seed rig and attached this follow-up. The wrapper captured each
child arm's exit code, stamped it into the JSON, and then threw it away: the last command was always
`echo done`, so the wrapper exited 0 whatever happened.

Measured on the pre-fix script, all three arms exiting 3 with NOT ONE output file written:

    WRAPPER EXIT CODE: 0
    [..] load1=7.42  discover  A-first  rep 1
    [..] load1=7.39  discover  B-returning  rep 1
    [..] load1=6.88  discover  C-auth  rep 1
    done -> /tmp/lat176-red

A total wipe-out was byte-identical to a healthy run. That is what these tests pin.

🔴 THE LOAD-BEARING TEST IS `test_healthy_run_exits_zero`. Every other test here would also pass
against a wrapper that simply exited 1 unconditionally, which would be worse than the defect — it
would make the rig unusable rather than merely untrustworthy. The suite is only meaningful as a
pair: silent on a good grid, loud and specific on every bad one.

No network and no browser: `node` is replaced on PATH by a stub, so each case is deterministic and
the whole grid runs at FELT_SLEEP_S=0.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "tools" / "felt-arms.sh"

# Written by the stub for an arm that produced a real, usable measurement.
VALID_ROW = '{"summary":{},"results":[{"run":1,"valid":true,"throttled":false,"first":812}]}'

STUBS = {
    # exits nonzero and writes nothing — the crash case that motivated the follow-up
    "crash": '#!/bin/bash\nexit 3\n',
    # exits 0 and writes a usable row — the converse; the wrapper must stay silent
    "healthy": f'#!/bin/bash\nprintf \'{VALID_ROW}\' > "$4"\nexit 0\n',
    # exits 0 but no card ever rendered / the seed did not apply
    "invalid": '#!/bin/bash\nprintf \'{"summary":{},"results":'
               '[{"run":1,"valid":false,"throttled":false}]}\' > "$4"\nexit 0\n',
    # exits 0 but every run was self-throttled by 429s — re-run it, do not re-code it
    "throttled": '#!/bin/bash\nprintf \'{"summary":{},"results":'
                 '[{"run":1,"valid":false,"throttled":true,"api429":9}]}\' > "$4"\nexit 0\n',
    # exits 0 and writes no file at all
    "nofile": '#!/bin/bash\nexit 0\n',
    # exits 0 and writes something that is not JSON
    "corrupt": '#!/bin/bash\nprintf \'not json {{{\' > "$4"\nexit 0\n',
    # only the B arm dies; A and C are healthy
    "mixed": '#!/bin/bash\nif [[ "$4" == *B-returning* ]]; then exit 3; fi\n'
             f'printf \'{VALID_ROW}\' > "$4"\nexit 0\n',
}


def run_arms(tmp_path, stub, reps=1):
    """Run the wrapper with `node` stubbed out. Returns (exit_code, combined_output, outdir)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node = bin_dir / "node"
    node.write_text(STUBS[stub])
    node.chmod(0o755)

    out_dir = tmp_path / "out"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FELT_SLEEP_S"] = "0"  # the grid, with no settle pauses

    proc = subprocess.run(
        ["bash", str(WRAPPER), "discover", str(reps), str(out_dir)],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr, out_dir


def test_wrapper_is_syntactically_valid():
    assert subprocess.run(["bash", "-n", str(WRAPPER)]).returncode == 0


def test_healthy_run_exits_zero(tmp_path):
    """The converse, and the one that stops this suite passing against a wrapper that always fails."""
    code, out, _ = run_arms(tmp_path, "healthy")
    assert code == 0, f"a healthy grid must exit 0, got {code}:\n{out}"
    assert "NO USABLE MEASUREMENT" not in out
    assert "3/3 arm-runs valid" in out


def test_healthy_multi_rep_counts_every_arm_run(tmp_path):
    code, out, _ = run_arms(tmp_path, "healthy", reps=2)
    assert code == 0
    assert "6/6 arm-runs valid" in out  # 2 reps x 3 arms, none miscounted


@pytest.mark.parametrize(
    "stub,reason",
    [
        ("crash", "CHILD EXITED 3"),
        ("invalid", "NO VALID RUN"),
        ("throttled", "SELF-THROTTLED"),
        ("nofile", "NO OUTPUT FILE"),
        ("corrupt", "unreadable or unwritable"),
    ],
)
def test_each_failure_class_exits_nonzero_with_its_own_reason(tmp_path, stub, reason):
    """Distinct reasons, because 'crashed' and 'throttled' need opposite responses from the operator."""
    code, out, _ = run_arms(tmp_path, stub)
    assert code != 0, f"{stub}: wrapper exited 0 on a dead grid:\n{out}"
    assert "3 of 3 arm-runs produced NO USABLE MEASUREMENT" in out
    assert reason in out, f"{stub}: expected reason {reason!r} in:\n{out}"


def test_one_dead_arm_fails_the_run_but_does_not_abort_the_grid(tmp_path):
    """The arms are INTERLEAVED, so bailing at B would bias the surviving comparison.

    Run the whole grid, then fail. C-auth comes after the dead B arm and must still have run.
    """
    code, out, out_dir = run_arms(tmp_path, "mixed")

    assert code != 0
    assert "1 of 3 arm-runs produced NO USABLE MEASUREMENT" in out
    assert "B-returning rep1" in out
    # the healthy arms are not accused
    assert "A-first rep1 —" not in out
    assert "C-auth rep1 —" not in out
    # and the loop genuinely continued past the failure
    assert (out_dir / "discover-C-auth-r1.json").exists(), "grid aborted at the dead arm"
    assert (out_dir / "discover-A-first-r1.json").exists()


def test_load_stamping_still_happens(tmp_path):
    """The validator shares a pass with the original load-stamp; the stamp must survive it."""
    _, _, out_dir = run_arms(tmp_path, "healthy")
    row = json.loads((out_dir / "discover-A-first-r1.json").read_text())["results"][0]
    assert "load1" in row and isinstance(row["load1"], float)
    assert row["exit"] == 0
