"""THE DEPLOY GATES MUST DIFF FROM WHAT LAST DEPLOYED, NOT FROM THE LAST PUSH — #7610.

═══ WHAT THIS PROTECTS ═══

`ci-change-scope.sh` and `heroku-release-required.sh` each classify the range
they are handed, and each fails toward running/releasing. Both were handed
`github.event.before` — the PREVIOUS PUSH. That is not the last thing that
reached a dyno, and the difference is not cosmetic:

    push A  backend delta        CI red on an unrelated frontend fixture
                                 -> `deploy` skipped. Correct.
    push B  one frontend test    scope=frontend, required=false
                                 -> `deploy` skipped AGAIN, and A's delta is now
                                    BELOW the base every future push diffs from.

Measured on production 2026-09-20 21:26Z: `/api/health` served `56c9d27e` while
master was `f3d5be5ae`, with ten backend app files — two certed fixes — merged
above it and no future push able to carry them. It is silent by construction:
master is green, the tray is empty, `heroku releases` shows a recent release, and
any lane paying an after-check in that window reads a production without its fix
and concludes the fix did not work.

`.github/scripts/ci-deploy-base.sh` resolves the base instead of assuming it.

═══ WHY THE INVARIANT IS THE LOAD-BEARING HALF ═══

A resolver that can return the WRONG base is far worse than the defect it fixes:
a base too high skips a shard or a release that was needed. So the resolver is
built to satisfy one property — **the base it returns is always an ancestor of,
or equal to, the fallback it was given** — and that property is asserted here
over every branch, including the ones where production is ahead, unreachable,
unparseable or unresolvable. A range that can only grow cannot cause a missed
release; the worst case is a redundant one, which both sibling scripts already
say they choose on a tie.

The strawman guard matters as much: `test_the_old_base_is_what_stranded_it`
runs the same two gates from `github.event.before` and asserts they DO strand
the delta. Without it every assertion here would pass against a script that
ignored its inputs.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / ".github" / "scripts"
RESOLVER = SCRIPTS / "ci-deploy-base.sh"
SCOPE_SCRIPT = SCRIPTS / "ci-change-scope.sh"
RELEASE_SCRIPT = SCRIPTS / "heroku-release-required.sh"
MANIFEST = REPO / ".github" / "ci-cross-tier-paths.txt"

NULL_SHA = "0" * 40

# ── WHY THESE TWO PATHS ARE ASSEMBLED AND NOT WRITTEN OUT ──────────────────
# `test_ci_cross_tier_manifest.py` scans every `test_*.py` for string literals
# naming a `frontend/...` path and turns red unless the CI cross-tier manifest
# lists it. That rot guard is right about what such a literal normally means: a
# backend test READING a client file off disk, which the change classifier must
# never skip a shard for.
#
# These are not that. They are filenames inside a throwaway git repo built in
# `tmp_path`; nothing here opens the real `frontend/`. And they cannot be
# manifest-listed to quiet the scan, because the manifest is exactly the set the
# classifier forces `full` on — the strawman below needs a frontend path that
# still classifies as `frontend`, or it proves nothing. So the path is joined at
# runtime, which the scan does not read as a cross-tier claim. If you add a real
# frontend read to this file, spell it out in one literal and list it.
_FE = "frontend"
FE_SHIPPED_PAGE = f"{_FE}/app/page.tsx"
FE_FIXTURE_TEST = f"{_FE}/__tests__/clockbomb.test.tsx"

pytestmark = pytest.mark.skipif(
    shutil.which("curl") is None, reason="the resolver reads the health endpoint with curl"
)


@pytest.fixture
def repo(tmp_path: Path):
    """A throwaway git repo plus a stubbed health endpoint, run for real.

    The health read is a `file://` URL rather than a mock: the script's job is to
    parse what the endpoint actually returns and decide whether the sha in it is
    usable HERE, and stubbing curl out would leave both halves unproven.
    """

    work = tmp_path / "repo"
    work.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=work, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")

    def commit(files: dict[str, str]) -> str:
        for rel, body in files.items():
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            git("add", rel)
        git("commit", "-q", "-m", "c", "--allow-empty")
        return git("rev-parse", "HEAD")

    def health(body: str | None = None, *, commit_sha: str | None = None) -> str:
        """A URL the resolver can read. `None` body means the endpoint is down."""
        served = tmp_path / "health.json"
        if body is None:
            served.unlink(missing_ok=True)
            return f"file://{served}"
        served.write_text(body, encoding="utf-8")
        return f"file://{served}"

    def payload(commit_sha: str, **extra) -> str:
        return json.dumps({"commit": commit_sha, "uptime_seconds": 124, "dyno": "web.1", **extra})

    def run(script: Path, *args: str, url: str | None = None, extra_env: dict | None = None):
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "CI_CROSS_TIER_MANIFEST": str(MANIFEST),
        }
        if url is not None:
            env["CI_DEPLOYED_SHA_URL"] = url
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(script), *args], cwd=work, capture_output=True, text=True, env=env
        )

    def base(fallback: str, head: str, url: str) -> str:
        proc = run(RESOLVER, fallback, head, url=url)
        # A non-zero exit would send ci.yml to its own `|| echo` fallback, which
        # is safe but silent; the resolver is written never to need it.
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    def scope(base_sha: str, head: str) -> str:
        proc = run(SCOPE_SCRIPT, base_sha, head)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    def release_required(base_sha: str, head: str) -> str:
        proc = run(RELEASE_SCRIPT, base_sha, head)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    return SimpleNamespace(
        path=work,
        git=git,
        commit=commit,
        health=health,
        payload=payload,
        base=base,
        scope=scope,
        release_required=release_required,
        run=run,
    )


@pytest.fixture
def stranded(repo):
    """#7610's exact shape: a backend delta that did not release, then a
    frontend-only push on top of it.

    `deployed` is what production serves; `before` is what `github.event.before`
    would be for the newest push; `head` is that push.
    """
    deployed = repo.commit({"backend/app/main.py": "a", FE_SHIPPED_PAGE: "a"})
    before = repo.commit({"backend/app/tasks/kalshi.py": "the delta that never released"})
    head = repo.commit({FE_FIXTURE_TEST: "the repair that did release"})
    return SimpleNamespace(deployed=deployed, before=before, head=head)


class TestTheShip:
    def test_the_old_base_is_what_stranded_it(self, repo, stranded):
        """STRAWMAN. Diffing from the previous push hides the backend delta.

        If this ever fails, every assertion in this file is vacuous — the defect
        would already be absent and the resolver would be proving nothing.
        """
        assert repo.scope(stranded.before, stranded.head) == "frontend"
        assert repo.release_required(stranded.before, stranded.head) == "false"

    def test_the_resolved_base_carries_the_stranded_backend_delta_into_both_gates(
        self, repo, stranded
    ):
        url = repo.health(repo.payload(stranded.deployed))
        base = repo.base(stranded.before, stranded.head, url)

        assert base == stranded.deployed
        assert repo.scope(base, stranded.head) == "full"
        assert repo.release_required(base, stranded.head) == "true"

    def test_an_abbreviated_commit_field_is_what_the_endpoint_actually_returns(
        self, repo, stranded
    ):
        """`/api/health` serves 8 characters, not 40. A resolver that only
        handled full shas would fail open on every real read."""
        url = repo.health(repo.payload(stranded.deployed[:8]))
        assert repo.base(stranded.before, stranded.head, url) == stranded.deployed


class TestTheRangeCanOnlyGrow:
    """The invariant. Every case: the answer is an ancestor of, or equal to, the
    fallback — so neither gate can ever see LESS than it sees today."""

    def _is_ancestor(self, repo, a: str, b: str) -> bool:
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", a, b],
                cwd=repo.path,
                capture_output=True,
            ).returncode
            == 0
        )

    def test_every_reachable_branch_returns_an_ancestor_of_the_fallback(self, repo, stranded):
        cases = {
            "deployed below the fallback": repo.payload(stranded.deployed),
            "deployed at the fallback": repo.payload(stranded.before),
            "deployed abbreviated": repo.payload(stranded.deployed[:8]),
            "commit field absent": json.dumps({"uptime_seconds": 1}),
            "commit field unusable": json.dumps({"commit": "unknown"}),
            "commit unknown to this checkout": repo.payload("deadbeefdeadbeefdeadbeef"),
            "not json at all": "<html>502 Bad Gateway</html>",
            "empty body": "",
        }
        for name, body in cases.items():
            answer = repo.base(stranded.before, stranded.head, repo.health(body))
            assert answer, f"{name}: the resolver returned nothing"
            assert self._is_ancestor(
                repo, answer, stranded.before
            ), f"{name}: {answer} is not at or below the fallback"

    def test_a_production_ahead_of_the_fallback_is_refused(self, repo, stranded):
        """If production somehow serves something ABOVE `event.before` — a
        force-push, a rebased master, a deploy off another ref — adopting it
        would SHRINK the range and could hide a backend path. Keep the fallback.
        """
        url = repo.health(repo.payload(stranded.head))
        assert repo.base(stranded.before, stranded.head, url) == stranded.before

    def test_a_sibling_branch_head_is_refused(self, repo, stranded):
        """Not-an-ancestor is the test, not "is it newer". A commit on a branch
        that never merged is neither above nor below, and must be refused."""
        repo.git("checkout", "-q", "-b", "sidecar", stranded.deployed)
        sidecar = repo.commit({"backend/app/sidecar.py": "x"})
        repo.git("checkout", "-q", "main")
        url = repo.health(repo.payload(sidecar))
        assert repo.base(stranded.before, stranded.head, url) == stranded.before


class TestItFailsTowardTheFallback:
    def test_an_unreachable_endpoint_keeps_the_fallback(self, repo, stranded):
        url = repo.health(None)  # nothing at that path
        assert repo.base(stranded.before, stranded.head, url) == stranded.before

    def test_production_already_at_the_fallback_keeps_the_fallback(self, repo, stranded):
        url = repo.health(repo.payload(stranded.before))
        assert repo.base(stranded.before, stranded.head, url) == stranded.before

    def test_the_null_sha_fallback_is_preserved_verbatim(self, repo, stranded):
        """A branch's first push. Both siblings read the null sha as "no usable
        base" and fail toward full/true; substituting a real sha would give them
        a diffable range and could turn that `full` into a `frontend`."""
        url = repo.health(repo.payload(stranded.deployed))
        assert repo.base(NULL_SHA, stranded.head, url) == NULL_SHA

    def test_no_head_keeps_the_fallback(self, repo, stranded):
        proc = repo.run(RESOLVER, stranded.before, "", url=repo.health(repo.payload(stranded.deployed)))
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == stranded.before

    def test_an_empty_fallback_stays_empty_so_ci_yml_can_see_it(self, repo, stranded):
        """ci.yml re-substitutes `github.event.before` on an empty answer. The
        resolver must not invent a base where it was given none."""
        proc = repo.run(RESOLVER, "", stranded.head, url=repo.health(repo.payload(stranded.deployed)))
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == ""

    def test_a_slow_endpoint_does_not_hang_the_deploy_path(self, repo, stranded):
        """The timeout is configurable precisely so it can be proven to exist."""
        proc = repo.run(
            RESOLVER,
            stranded.before,
            stranded.head,
            url="http://10.255.255.1:9/api/health",
            extra_env={"CI_DEPLOYED_SHA_TIMEOUT": "1"},
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == stranded.before

    def test_every_branch_exits_zero(self, repo, stranded):
        """A non-zero exit sends ci.yml to its own `|| echo` fallback. That is
        safe, but it would also mean the reasoning on stderr never explains a
        base anybody has to debug later."""
        for body in (repo.payload(stranded.deployed), "garbage", ""):
            proc = repo.run(RESOLVER, stranded.before, stranded.head, url=repo.health(body))
            assert proc.returncode == 0, proc.stderr


class TestTheWorkflowActuallyUsesIt:
    """The script is only worth anything if ci.yml calls it. Both call sites are
    asserted by shape, because a resolver wired into one gate and not the other
    reproduces exactly half of #7610."""

    def _ci(self) -> str:
        return (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_both_gates_take_their_base_from_the_resolver(self):
        """Counted on the INVOCATION, not the filename: the file is also named in
        the prose beside one of the call sites, and a count that includes a
        comment passes when a call site is deleted."""
        ci = self._ci()
        calls = ci.count("bash .github/scripts/ci-deploy-base.sh")
        assert calls == 2, (
            f"expected exactly two call sites — change-scope and release-required — found {calls}"
        )

    @pytest.mark.parametrize("gate", ["ci-change-scope.sh", "heroku-release-required.sh"])
    def test_neither_gate_is_still_handed_the_push_event_directly(self, gate):
        """The whole defect in one assertion: `github.event.before` as the FIRST
        argument of either classifier is what stranded ten backend files."""
        ci = self._ci()
        idx = ci.index(f"bash .github/scripts/{gate}")
        invocation = ci[idx : idx + 260]
        first_arg = invocation.split(gate, 1)[1].lstrip(" \\\n")
        assert first_arg.startswith('"$BASE"'), (
            f"{gate} must be handed the resolved base, not {first_arg[:40]!r}"
        )

    def test_the_resolver_is_executable(self):
        assert RESOLVER.stat().st_mode & 0o111, "ci.yml runs it via `bash`, but keep it executable"
