"""THE CHANGE CLASSIFIER MAY NEVER SKIP A BACKEND JOB THAT COULD HAVE GONE RED — #5007.

═══ WHAT THIS PROTECTS ═══

`.github/scripts/ci-change-scope.sh` decides whether a candidate is confined to
`frontend/`. When it says `frontend`, CI drops the four backend shards,
shard-completeness and search-recall — ~11.1m and ~8.3m of a 12.1m run.

That is only safe if the backend suite cannot see `frontend/`. **It can.** Twelve
backend test files are cross-tier parity guards that read client source off disk
and assert the client consumes what the backend serves — for example
`test_futures_serves_resolution_source_4788.py` reads
`frontend/components/futures/OutcomeRow.tsx`. A frontend-only edit to that file
can redden a backend shard, so the classifier must NOT skip it.

`.github/ci-cross-tier-paths.txt` lists those paths, and the classifier forces
`full` when a candidate touches one.

═══ WHY THE ROT GUARD IS THE LOAD-BEARING HALF ═══

A hand-maintained allowlist of "files the other tier reads" is a fail-open the
moment somebody adds a parity test and does not update it — and nothing about
adding a parity test suggests editing a CI manifest. So this file re-derives the
set from `backend/tests/` on every run. A new cross-tier read that the manifest
does not cover turns this suite red, which is the only reason the list can be
trusted.

Fail-closed in both directions: the classifier defaults to `full` on anything it
cannot prove, and this guard defaults to red on anything it cannot account for.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "ci-change-scope.sh"
MANIFEST = REPO / ".github" / "ci-cross-tier-paths.txt"
BACKEND_TESTS = REPO / "backend" / "tests"


def _manifest_paths() -> set[str]:
    """The manifest as the script itself parses it: comments and blanks dropped."""
    out: set[str] = set()
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


# A cross-tier read appears in TWO shapes, and a scanner that knows only one is
# itself a fail-open. CERT-2566 blocked the first cut of this file for exactly
# that: it saw only the component chain, so three whole-path literals were
# invisible, and a mutation of `tournamentReskin.test.tsx` alone severed
# `emit_comparison_specimen.py` while the classifier still said `frontend`.
#
#   1. COMPONENT CHAIN — `here / "frontend" / "lib" / "marketShape.ts"`.
#      Anchoring on the quoted "frontend" component (not the bare word) is what
#      keeps prose and comments out of the scan.
#   2. WHOLE PATH — `"frontend/lib/discoverInteractions.ts"` in one literal,
#      including a `./`-relative spelling.
_CHAIN = re.compile(r"""["']frontend["']((?:\s*/\s*["'][^"']+["'])+)""")
_COMPONENT = re.compile(r"""["']([^"']+)["']""")
_WHOLE_PATH = re.compile(r"""["']((?:\./)?frontend/[A-Za-z0-9_./\[\]-]+)["']""")


def _cross_tier_reads() -> dict[str, set[str]]:
    """{test filename -> {frontend paths it names}} derived from source."""
    found: dict[str, set[str]] = {}
    for path in sorted(BACKEND_TESTS.rglob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for chain in _CHAIN.findall(text):
            parts = _COMPONENT.findall(chain)
            if not parts:
                continue
            found.setdefault(path.name, set()).add("frontend/" + "/".join(parts))
        for whole in _WHOLE_PATH.findall(text):
            found.setdefault(path.name, set()).add(whole.removeprefix("./"))
    return found


class TestTheManifestDescribesReality:
    def test_every_listed_path_exists_on_disk(self):
        # A path that has been moved or deleted silently stops protecting
        # anything: the classifier compares whole lines, so a stale entry can
        # never match and the file it used to guard becomes skippable.
        missing = sorted(p for p in _manifest_paths() if not (REPO / p).exists())
        assert missing == [], f"manifest lists paths that no longer exist: {missing}"

    def test_the_manifest_is_not_empty(self):
        # A truncated or emptied manifest would make every frontend candidate
        # skippable while this suite still passed every other assertion.
        assert len(_manifest_paths()) >= 10

    def test_every_cross_tier_read_in_backend_tests_is_covered(self):
        # THE ROT GUARD. Add a backend test that reads a frontend file and this
        # goes red until the manifest covers it.
        listed = _manifest_paths()
        files = {p for p in listed if not p.endswith("/")}
        dirs = {p for p in listed if p.endswith("/")}

        def covered(p: str) -> bool:
            # A directory entry covers anything beneath it, and also covers the
            # bare directory itself — `test_playoff_degraded_contract` builds the
            # fixtures dir and joins filenames onto it later, so the scan sees
            # the directory, not the files.
            return (
                p in files
                or any(p.startswith(d) for d in dirs)
                or any(d.rstrip("/") == p for d in dirs)
            )

        uncovered: list[str] = []
        for test_name, paths in sorted(_cross_tier_reads().items()):
            for p in sorted(paths):
                if not covered(p):
                    uncovered.append(f"{test_name} reads {p}")
        assert uncovered == [], (
            "backend tests read frontend paths the CI cross-tier manifest does not "
            "list, so the change classifier would skip the shard that runs them. "
            "Add them to .github/ci-cross-tier-paths.txt:\n  " + "\n  ".join(uncovered)
        )

    def test_the_scan_actually_finds_the_known_parity_guards(self):
        # Guards the guard. If a regex stops matching, `_cross_tier_reads()`
        # returns less and the rot check above passes vacuously — the exact
        # shape that makes a scan-based test worthless.
        #
        # BOTH SHAPES are represented deliberately. The first cut of this test
        # listed only component-chain owners, so it stayed green while the
        # whole-path shape was entirely invisible (CERT-2566).
        names = set(_cross_tier_reads())
        expected = {
            # component chain
            "test_futures_serves_resolution_source_4788.py",
            "test_futures_serves_shape_field_q478.py",
            "test_tournament_hub_links.py",
            # whole-path literal
            "test_comparison_specimen.py",
            "test_discover_provenance.py",
        }
        missing = sorted(expected - names)
        assert missing == [], f"cross-tier scan no longer sees: {missing}"

    def test_the_scan_finds_both_read_shapes_by_path(self):
        # Named paths, not just owning modules: a scan could find the file for
        # one reason and still miss the path that matters.
        reads = {p for paths in _cross_tier_reads().values() for p in paths}
        for path in (
            "frontend/lib/marketShape.ts",  # component chain
            "frontend/lib/discoverInteractions.ts",  # whole-path literal
            "frontend/__tests__/components/tournamentReskin.test.tsx",
        ):
            assert path in reads, f"scan missed {path}"


@pytest.fixture
def repo(tmp_path: Path):
    """A throwaway git repo the classifier can be run against for real.

    The script's whole job is reading `git diff`, so fixtures that stub git out
    would prove nothing about the decision CI actually makes.
    """

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")

    def commit(files: dict[str, str], *, removing: tuple[str, ...] = ()) -> str:
        for rel, body in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            git("add", rel)
        for rel in removing:
            git("rm", "-q", rel)
        git("commit", "-q", "-m", "c", "--allow-empty")
        return git("rev-parse", "HEAD")

    def scope(base: str, head: str, manifest: Path | str = MANIFEST) -> str:
        proc = subprocess.run(
            ["bash", str(SCRIPT), base, head],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CI_CROSS_TIER_MANIFEST": str(manifest)},
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    return SimpleNamespace(path=tmp_path, git=git, commit=commit, scope=scope)


class TestTheClassifierFailsClosed:
    def test_frontend_only_change_untouched_by_backend_tests(self, repo):
        # The classifier must be ABLE to say "frontend", or it saves nothing and
        # every fail-closed assertion below is satisfied by a stuck answer.
        base = repo.commit({"frontend/app/page.tsx": "a"})
        head = repo.commit({"frontend/app/page.tsx": "b"})
        assert repo.scope(base, head) == "frontend"

    def test_a_frontend_change_to_a_cross_tier_path_runs_everything(self, repo):
        # THE FAIL-OPEN FIXTURE. Every path here is under frontend/, so a naive
        # "frontend-only" rule reduces scope — and skips the backend test that
        # reads this very file.
        cross = sorted(p for p in _manifest_paths() if not p.endswith("/"))[0]
        base = repo.commit({cross: "a"})
        head = repo.commit({cross: "b"})
        assert repo.scope(base, head) == "full"

    def test_a_change_under_a_cross_tier_DIRECTORY_runs_everything(self, repo):
        # The directory form of the same fail-open. A fixture the playoff parity
        # guard loads is not named individually anywhere.
        under = "frontend/__tests__/fixtures/uxp175_playoffs_nba_control.json"
        base = repo.commit({under: "a"})
        head = repo.commit({under: "b"})
        assert repo.scope(base, head) == "full"

    def test_a_shared_change_cannot_ride_behind_a_frontend_only_tip(self, repo):
        # "Classify the complete candidate, not the last commit." The tip commit
        # is frontend-only; the range is not.
        base = repo.commit({"README.md": "a"})
        repo.commit({"backend/app/routes/feed.py": "x"})
        tip = repo.commit({"frontend/app/page.tsx": "b"})
        assert repo.scope(base, tip) == "full"

    def test_a_backend_path_forces_full(self, repo):
        base = repo.commit({"frontend/app/page.tsx": "a"})
        head = repo.commit({"backend/app/main.py": "x", "frontend/app/page.tsx": "b"})
        assert repo.scope(base, head) == "full"

    def test_moving_a_backend_file_into_frontend_forces_full(self, repo):
        # Rename detection would print only the frontend destination and hide the
        # backend file that vanished. `--no-renames` is what stops that.
        base = repo.commit({"backend/app/served.py": "payload"})
        head = repo.commit({"frontend/served.py": "payload"}, removing=("backend/app/served.py",))
        assert repo.scope(base, head) == "full"

    @pytest.mark.parametrize(
        "path",
        ["ios/Bain Luck/Bain Luck/Views/FeedView.swift", "docs/rulings/001-x.md", "CLAUDE.md"],
        ids=["ios", "docs", "root-markdown"],
    )
    def test_buckets_that_look_inert_are_not_reduced(self, repo, path):
        # ios/ is read by test_cold_path_charter; CLAUDE.md is guarded by
        # test_claude_md_size; docs/rulings by the ledger gates. Deliberately
        # absent from the safe set, and pinned so a later "obvious" widening
        # has to argue with a test.
        base = repo.commit({path: "a"})
        head = repo.commit({path: "b"})
        assert repo.scope(base, head) == "full"

    def test_an_empty_diff_is_full(self, repo):
        base = repo.commit({"frontend/app/page.tsx": "a"})
        assert repo.scope(base, base) == "full"

    def test_a_missing_base_is_full(self, repo):
        head = repo.commit({"frontend/app/page.tsx": "a"})
        assert repo.scope("0" * 40, head) == "full"
        assert repo.scope("", head) == "full"

    def test_an_unknown_sha_is_full(self, repo):
        head = repo.commit({"frontend/app/page.tsx": "a"})
        assert repo.scope("deadbeef" * 5, head) == "full"

    def test_an_unreadable_manifest_is_full(self, repo, tmp_path):
        # If the safety list cannot be read, nothing can be proven safe. Without
        # this branch a deleted manifest would make every frontend candidate
        # skippable — the failure would look like a speed-up.
        base = repo.commit({"frontend/app/page.tsx": "a"})
        head = repo.commit({"frontend/app/page.tsx": "b"})
        assert repo.scope(base, head, manifest=tmp_path / "nope.txt") == "full"

    @pytest.mark.parametrize(
        "consumer",
        [
            "frontend/__tests__/components/tournamentReskin.test.tsx",
            "frontend/lib/discoverInteractions.ts",
            "frontend/lib/play/session.ts",
        ],
        ids=["tournament-reskin", "discover-interactions", "play-session"],
    )
    def test_whole_path_frontend_consumer_cannot_be_classified_frontend(self, repo, consumer):
        """CERT-2566's repair, proven per file.

        These three are named in `backend/tests/` as single whole-path string
        literals rather than `/`-joined components, so the first scanner could
        not see them and the manifest omitted all three. The grader mutated
        `tournamentReskin.test.tsx` alone, severed `emit_comparison_specimen.py`,
        and the classifier still answered `frontend` — it would have skipped the
        shard carrying the contract that had just broken.

        Each is under `frontend/`, so a naive rule reduces scope on every one.
        """
        base = repo.commit({consumer: "a"})
        head = repo.commit({consumer: "b"})
        assert repo.scope(base, head) == "full"

    def test_a_frontend_scope_always_implies_no_heroku_release(self, repo):
        """The subset invariant `ci.yml`'s change-scope comment relies on.

        `deploy` needs the shards, and a skipped need skips the dependent. That
        is only harmless because a `frontend` scope is a STRICT SUBSET of the
        no-release set — so `deploy` was already being skipped by
        `release-required` and this change removes no release that would
        otherwise have happened. Asserted rather than reasoned about, because if
        the two safe lists ever drift apart the symptom is a silently missed
        production deploy.
        """
        release_script = REPO / ".github" / "scripts" / "heroku-release-required.sh"
        cases = [
            {"frontend/app/page.tsx": "x"},
            {"frontend/lib/util.ts": "x", "frontend/app/page.tsx": "y"},
            {"frontend/components/Card.tsx": "x"},
        ]
        for files in cases:
            base = repo.commit({k: "a" for k in files})
            head = repo.commit(files)
            if repo.scope(base, head) != "frontend":
                continue
            required = subprocess.run(
                ["bash", str(release_script), base, head],
                cwd=repo.path,
                capture_output=True,
                text=True,
                env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
            ).stdout.strip()
            assert required == "false", (
                f"change-scope said 'frontend' but heroku-release-required said "
                f"'{required}' for {sorted(files)} — deploy would be skipped by a "
                f"skipped shard while a release was genuinely needed"
            )

    def test_a_manifest_entry_is_matched_whole_line_not_as_a_substring(self, repo):
        # `frontend/lib/marketShape.ts.bak` must NOT satisfy the manifest entry
        # `frontend/lib/marketShape.ts` — and must not be forced to full by it
        # either. It is an ordinary frontend file.
        base = repo.commit({"frontend/lib/marketShape.ts.bak": "a"})
        head = repo.commit({"frontend/lib/marketShape.ts.bak": "b"})
        assert repo.scope(base, head) == "frontend"
