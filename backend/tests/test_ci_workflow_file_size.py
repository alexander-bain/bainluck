"""GitHub refuses a workflow file over ~512,000 bytes, silently.

Measured twice: #11305's ci.yml at 512,135 bytes and #10090 attempt190's at
513,260 each got a "workflow file issue" run with zero jobs and NO CI run on
the pull request at all, while 511,542 ran. Nothing reddens; the CI row is
simply absent, which notice 28 reads as a STOP only if someone looks. This
guard makes the overflow a local red before the push.
"""

from pathlib import Path

CI_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
GITHUB_REFUSES_ABOVE = 512_000


def test_ci_workflow_stays_under_githubs_file_size_limit():
    size = CI_YML.stat().st_size
    assert size < GITHUB_REFUSES_ABOVE, (
        f"ci.yml is {size:,} bytes; GitHub refuses a workflow over ~512,000 "
        "and runs no CI at all. Share a step or trim comments."
    )
