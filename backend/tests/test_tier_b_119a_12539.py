"""#12539 (119-A): run the Tier-B policy's `Fable:` line tests in the backend suite.

The policy is JavaScript (`tools/release/tier_b.cjs`), tested with `node --test`
in `tests/release/`. CI runs those through Python, as
`test_eval_candidate_workflow_12235.py` does for the older policy tests.
"""

from pathlib import Path
import subprocess


def test_the_fable_line_policy_tests_pass():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["node", "--test", "tests/release/tier_b_119a.test.cjs"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
