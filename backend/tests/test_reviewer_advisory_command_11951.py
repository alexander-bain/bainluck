"""Run the native command's guard and approval compatibility checks in CI."""

from pathlib import Path
import subprocess


def test_the_capped_advisory_command_cannot_authorize_a_product_merge():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "node",
            "--test",
            "tests/release/reviewer_eval_comment.test.cjs",
            "tests/release/tier_b.test.cjs",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
