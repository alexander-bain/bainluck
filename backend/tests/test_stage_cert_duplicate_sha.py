"""`tools/stage-cert.sh` must not hand out a fresh id for a sha that is already
being graded.

CERT-2020 and CERT-2021 (lane1b/054, sha 1ff738bc) are the same commit staged
twice: the tool guarantees an unused *id* and never looked at the *sha*, so
re-running it after CI turned green produced a second block, and two bus
sessions claimed the two ids in the same minute. Two verdicts on one commit is
the state standing notices 12/17 exist to prevent.

The guard is deliberately narrow — it fires only when the existing block is
still LIVE — because this tool sits on every lane's critical path and must
never wedge the bus for a legitimate re-stage.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "stage-cert.sh"

STAGED_SHA = "1ff738bce62df2b9eef6f685061f0235a1ffbd81"
DONE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FRESH_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _block(cert_id, status, sha):
    return (
        f"\n# CERT-{cert_id} -- SOME-SUBJECT-{cert_id}\n\n"
        f"queue_id: SOME-SUBJECT-{cert_id}\n"
        f"status: {status}\n"
        f"lane: lane1b\n"
        f"issue: #1\n"
        f"pr: https://example.invalid/pr\n"
        f"branch: lane1b/whatever\n"
        f"sha: {sha}\n\n"
        f"## Ship\nprose\n\nmore prose after a blank line\n"
    )


@pytest.fixture
def queue(tmp_path):
    q = tmp_path / "CERT-QUEUE.md"
    log = tmp_path / "CODEX-CERT-LOG.md"
    q.write_text(
        "# CERT QUEUE\n"
        + _block(100, "running", STAGED_SHA)
        + _block(101, "done", DONE_SHA)
    )
    log.write_text("# LEDGER\n")
    return q, log


def _stage(queue, sha, body="body\n", **env_extra):
    q, log = queue
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(q.parent),
        "CERT_QUEUE": str(q),
        "CERT_LOG": str(log),
    }
    env.update(env_extra)
    return subprocess.run(
        [
            "bash", str(SCRIPT), "SUBJ", "lane1b", "lane1b/br", sha,
            "https://example.invalid/pr", "#1",
        ],
        input=body, capture_output=True, text=True, env=env,
    )


class TestRefusesALiveDuplicate:
    def test_a_sha_already_being_graded_is_refused(self, queue):
        r = _stage(queue, STAGED_SHA)
        assert r.returncode == 2, r.stdout + r.stderr
        assert "REFUSING" in r.stderr
        assert "CERT-100" in r.stderr, "the refusal must name the block it found"

    def test_the_refusal_appends_nothing(self, queue):
        """The property that actually matters: a refused stage leaves no
        half-written block and burns no id."""
        q, _ = queue
        before = q.read_text()
        _stage(queue, STAGED_SHA)
        assert q.read_text() == before

    def test_a_short_sha_still_collides_with_the_full_one(self, queue):
        r = _stage(queue, STAGED_SHA[:12])
        assert r.returncode == 2, "a 12-char sha names the same commit"
        assert "CERT-100" in r.stderr


class TestDoesNotWedgeTheBus:
    """Every one of these staged fine before the guard and must still."""

    def test_a_fresh_sha_is_staged(self, queue):
        q, _ = queue
        r = _stage(queue, FRESH_SHA)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"
        assert FRESH_SHA in q.read_text()

    def test_a_sha_whose_block_is_done_is_a_legitimate_restage(self, queue):
        """A second opinion or a re-arm on an already-graded sha is real work,
        and the guard must not be the thing that stops it."""
        r = _stage(queue, DONE_SHA)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"

    def test_the_override_is_honoured(self, queue):
        r = _stage(queue, STAGED_SHA, ALLOW_DUPLICATE_SHA="1")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "CERT-102"

    def test_the_id_is_still_max_plus_one(self, queue):
        """Regression: the guard runs after the id scan and must not disturb
        it — CERT-1853 is what happens when that scan drifts."""
        q, _ = queue
        _stage(queue, FRESH_SHA)
        assert "# CERT-102 -- SUBJ" in q.read_text()

    def test_the_body_is_still_written_verbatim(self, queue):
        q, _ = queue
        _stage(queue, FRESH_SHA, body="## MY PRESENTATION\nline two\n")
        assert "## MY PRESENTATION\nline two\n" in q.read_text()


class TestGuardIsNotVacuous:
    def test_without_the_guard_the_duplicate_would_have_been_staged(
        self, queue, tmp_path
    ):
        """Falsification: strip the refusal from a copy of the script and the
        same call succeeds. Without this, a guard that never fires and a guard
        that always passes look identical from the tests above.
        """
        stripped = tmp_path / "stage-cert-noguard.sh"
        src = SCRIPT.read_text()
        start = src.index('if [ "${ALLOW_DUPLICATE_SHA:-0}" != "1" ]; then')
        end = src.index("\nfi\n", start) + len("\nfi\n")
        stripped.write_text(src[:start] + src[end:])

        q, log = queue
        r = subprocess.run(
            [
                "bash", str(stripped), "SUBJ", "lane1b", "lane1b/br", STAGED_SHA,
                "https://example.invalid/pr", "#1",
            ],
            input="body\n", capture_output=True, text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": str(tmp_path),
                "CERT_QUEUE": str(q),
                "CERT_LOG": str(log),
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == "CERT-102", (
            "the pre-guard tool stages a second block on a sha already being "
            "graded — which is exactly CERT-2020/CERT-2021"
        )
