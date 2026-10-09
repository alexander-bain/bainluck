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

import ast
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "ci-change-scope.sh"
MANIFEST = REPO / ".github" / "ci-cross-tier-paths.txt"
BACKEND_TESTS = REPO / "backend" / "tests"
ROSTER = REPO / ".github" / "ci-native-backend-readers.txt"
ROSTER_SCRIPT = REPO / ".github" / "scripts" / "ci-native-backend-readers.sh"

# #10708 is INACTIVE: workflow normalization retains full backend/DB coverage.
# Direct text signals are an aid, not a complete reader/dependency boundary.
NATIVE_ACTIVATION_HOLDS = (
    "transitive test/helper/conftest/script and unresolved dynamic readers",
    "indirect database target dependencies",
    "residue Pass B origin/master...HEAD differs from classifier BASE HEAD",
)
_NATIVE_PATTERNS = {
    "chain": re.compile(r"[\"']ios[\"']\s*/"),
    "whole": re.compile(r"[\"'](?:\./)?ios/"),
    "token": re.compile(
        r"[\"'][^\"'\n]*\.(?:swift|pbxproj|xcodeproj|plist|entitlements)[\"']"
    ),
    "scanner": re.compile(r"scan_mutation_residue"),
}


def _roster_paths() -> list[str]:
    return [
        value
        for raw in ROSTER.read_text(encoding="utf-8").splitlines()
        if (value := raw.split("#", 1)[0].strip())
    ]


def _native_signal_tags(text: str) -> list[str]:
    return [name for name, pattern in _NATIVE_PATTERNS.items() if pattern.search(text)]


def _native_reader_signals(root: Path = BACKEND_TESTS) -> dict[str, list[str]]:
    """Only direct test-body signals; no inference of transitive completeness."""
    found = {}
    for path in sorted(root.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")  # decode failure must fail the guard
        ast.parse(text, filename=str(path))  # syntax failure must not reduce it
        tags = _native_signal_tags(text)
        if tags:
            found[str(path.relative_to(root.parent))] = tags
    return found


_REQUIRED_NATIVE_INPUTS = tuple(
    "ios/Bain Luck/" + path
    for path in (
        "Bain Luck/Views/LeaguesView.swift",
        "Bain Luck/Views/MyStuffView.swift",
        "Bain Luck/ViewModels/DiscoverViewModel.swift",
        "Bain Luck/ViewModels/FeedViewModel.swift",
        "Bain Luck/Services/APIClient.swift",
        "Bain Luck.xcodeproj/project.pbxproj",
        "BainLuckWidget/WidgetAPIClient.swift",
        "BainLuckWidget/WidgetFeedDecoding.swift",
        "Bain Luck/Models/CommonTypes.swift",
        "Bain Luck/Services/DiscoverFeedCache.swift",
        "Bain Luck/Views/DiscoverView.swift",
        "BainLuckTests/NumericSuffixDecodeTests.swift",
        "Bain Luck/ViewModels/FuturesListViewModel.swift",
        "Bain Luck/Views/PreferencesView.swift",
        "Bain Luck/Components/RelatedFuturesView.swift",
        "Bain Luck/Utilities/FormattingUtilities.swift",
        "Bain Luck/Components/PlayerPropsCardView.swift",
        "Bain Luck/Utilities/EventState.swift",
        "BainLuckTests/Fixtures/event-ufc-26sep19.served6816.SYNTHETIC.json",
        "BainLuckWatch Watch App/WatchTabView.swift",
        "BainLuckWatchUITests/ComplicationContentJourneyTests.swift",
        "BainLuckWatchUITests/WatchDiscoverJourneyTests.swift",
        "Bain Luck/Utilities/RenderedPercent.swift",
        "Bain Luck/Components/DiscoverEventCard.swift",
        "Bain Luck/Components/RelatedByTagView.swift",
        "Bain Luck/Views/MenuBarView.swift",
    )
)
_REQUIRED_NATIVE_GLOBS = ("ios/Bain Luck/BainLuckWatchUITests/*.swift",)


def _missing_native_inputs(
    root: Path = REPO,
    inputs: tuple[str, ...] = _REQUIRED_NATIVE_INPUTS,
    globs: tuple[str, ...] = _REQUIRED_NATIVE_GLOBS,
) -> list[str]:
    """Bounded reviewed inputs, not inferred coverage of every native reader."""
    missing = []
    for name in inputs:
        try:
            with (root / name).open("rb") as handle:
                if not handle.read(1):
                    missing.append(name)
        except OSError:
            missing.append(name)
    for pattern in globs:
        if not any(path.is_file() for path in root.glob(pattern)):
            missing.append(pattern)
    return missing


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
            ["git", "-C", str(tmp_path), *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
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
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "CI_CROSS_TIER_MANIFEST": str(manifest),
            },
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
        head = repo.commit(
            {"frontend/served.py": "payload"}, removing=("backend/app/served.py",)
        )
        assert repo.scope(base, head) == "full"

    @pytest.mark.parametrize(
        "path",
        ["docs/rulings/001-x.md", "CLAUDE.md"],
        ids=["docs", "root-markdown"],
    )
    def test_buckets_that_look_inert_are_not_reduced(self, repo, path):
        # CLAUDE.md is guarded by test_claude_md_size; docs/rulings by the ledger gates. Deliberately
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
    def test_whole_path_frontend_consumer_cannot_be_classified_frontend(
        self, repo, consumer
    ):
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
        asserted = 0
        for files in cases:
            base = repo.commit({k: "a" for k in files})
            head = repo.commit(files)
            if repo.scope(base, head) != "frontend":
                continue
            asserted += 1
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

        # 🔴 #5250: THE `continue` ABOVE IS SILENT, SO THE LOOP CAN EMPTY.
        #
        # Every case that stops being classified `frontend` skips its assertion
        # without a word. If change-scope ever stops matching these three paths,
        # zero assertions run and this test still passes green — the subset
        # invariant would be unguarded while reading as guarded, and the symptom
        # is a silently missed production deploy. Measured latent, not live:
        # instrumented 2026-09-11, all three cases assert today.
        assert asserted == len(cases), (
            f"only {asserted} of {len(cases)} cases reached the assertion — change-scope "
            f"no longer classifies these frontend paths as 'frontend', so this guard is "
            f"not guarding"
        )

    def test_a_manifest_entry_is_matched_whole_line_not_as_a_substring(self, repo):
        # `frontend/lib/marketShape.ts.bak` must NOT satisfy the manifest entry
        # `frontend/lib/marketShape.ts` — and must not be forced to full by it
        # either. It is an ordinary frontend file.
        base = repo.commit({"frontend/lib/marketShape.ts.bak": "a"})
        head = repo.commit({"frontend/lib/marketShape.ts.bak": "b"})
        assert repo.scope(base, head) == "frontend"


class TestNativeInactivePreparation:
    def resolve(self, roster, cwd):
        return subprocess.run(
            ["bash", str(ROSTER_SCRIPT)],
            cwd=cwd,
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "CI_NATIVE_BACKEND_READERS": str(roster),
            },
        )

    def test_known_direct_signals_are_rostered_without_completeness_claim(self):
        found = _native_reader_signals()
        assert not (set(found) - set(_roster_paths()))
        for name, tag in (
            ("cold_path_charter", "chain"),
            ("discover_provenance", "whole"),
            ("ios_codable_nonisolated_1775", "token"),
            ("mutation_guard", "scanner"),
        ):
            assert tag in found["tests/test_" + name + ".py"]
        assert "tests/test_ci_cross_tier_manifest.py" in _roster_paths()
        assert len(NATIVE_ACTIVATION_HOLDS) == 3

    def test_workflow_still_normalizes_native_to_full(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text()
        assert "full|frontend) ;;" in workflow
        assert "unparseable scope" in workflow and "SCOPE=full ;;" in workflow

    def test_required_reviewed_native_inputs_and_glob_are_present(self):
        assert _missing_native_inputs() == []

    def test_skip_bearing_reader_deletion_is_refused_by_preflight(self, tmp_path):
        # Execute the actual source guard on a missing scratch input: it SKIPS.
        # Our explicit preflight must independently make the omission red.
        source = ast.parse((BACKEND_TESTS / "test_cold_path_charter.py").read_text())
        guard = next(
            node
            for node in source.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "test_browse_issues_no_network_request_on_appear"
        )
        namespace = {"IOS": tmp_path / "ios/Bain Luck/Bain Luck", "pytest": pytest}
        exec(
            compile(
                ast.Module(body=[guard], type_ignores=[]), "actual-skip-reader", "exec"
            ),
            namespace,
        )
        with pytest.raises(pytest.skip.Exception):
            namespace[guard.name]()
        required = "ios/Bain Luck/Bain Luck/Views/LeaguesView.swift"
        assert _missing_native_inputs(tmp_path, inputs=(required,), globs=()) == [
            required
        ]

    @pytest.mark.parametrize(
        "path",
        [
            "ios/Bain Luck/BainLuckWatchUITests/ComplicationContentJourneyTests.swift",
            "ios/Bain Luck/BainLuckTests/Fixtures/event-ufc-26sep19.served6816.SYNTHETIC.json",
        ],
    )
    def test_watch_deletion_and_moved_fixture_are_refused(self, tmp_path, path):
        original = tmp_path / path
        original.parent.mkdir(parents=True)
        original.write_text("fixture")
        assert _missing_native_inputs(tmp_path, inputs=(path,), globs=()) == []
        original.rename(original.with_suffix(".moved"))
        assert _missing_native_inputs(tmp_path, inputs=(path,), globs=()) == [path]

    def test_empty_native_glob_is_refused(self, tmp_path):
        pattern = _REQUIRED_NATIVE_GLOBS[0]
        assert _missing_native_inputs(tmp_path, inputs=(), globs=(pattern,)) == [
            pattern
        ]

    def test_empty_required_native_input_is_refused(self, tmp_path):
        name = "ios/empty.swift"
        target = tmp_path / name
        target.parent.mkdir()
        target.write_text("")
        assert _missing_native_inputs(tmp_path, inputs=(name,), globs=()) == [name]

    def test_resolver_actual_roster_and_normalization(self, tmp_path):
        result = self.resolve(ROSTER, REPO / "backend")
        assert (
            result.returncode == 0 and result.stdout == " ".join(_roster_paths()) + "\n"
        )
        roster = tmp_path / "roster"
        roster.write_text(
            "  tests/test_mutation_guard.py # comment\n\n tests/test_ci_cross_tier_manifest.py  \n"
        )
        result = self.resolve(roster, REPO / "backend")
        assert result.returncode == 0
        assert (
            result.stdout
            == "tests/test_mutation_guard.py tests/test_ci_cross_tier_manifest.py\n"
        )

    @pytest.mark.parametrize(
        "entry",
        [
            "",
            "# comment",
            "tests/test_no_such_file.py",
            "/tests/test_x.py",
            "../tests/test_x.py",
            "tests/../test_x.py",
            "-q",
            "tests/test_*.py",
            "tests/test_x.py tests/test_y.py",
            "tests/test_mutation_guard.py",
        ],
    )
    def test_resolver_invalid_missing_empty_or_duplicate_has_no_partial_output(
        self, tmp_path, entry
    ):
        roster = tmp_path / "roster"
        # Leading valid selection followed by each invalid row must emit nothing.
        prefix = "" if entry in ("", "# comment") else "tests/test_mutation_guard.py\n"
        roster.write_text(prefix + entry + "\n")
        result = self.resolve(roster, REPO / "backend")
        assert result.returncode == 1 and result.stdout == ""

    def test_resolver_unreadable_or_decode_failure_has_no_partial_output(
        self, tmp_path
    ):
        missing = self.resolve(tmp_path / "missing", REPO / "backend")
        assert missing.returncode == 1 and missing.stdout == ""
        roster = tmp_path / "invalid-utf8"
        roster.write_bytes(b"tests/test_mutation_guard.py\n\xff")
        result = self.resolve(roster, REPO / "backend")
        assert result.returncode == 1 and result.stdout == ""

    @pytest.mark.parametrize("body", [b"\xff", b"if ):\n"])
    def test_signal_scan_refuses_read_or_parse_failure(self, tmp_path, body):
        root = tmp_path / "tests"
        root.mkdir()
        (root / "test_reader.py").write_bytes(body)
        with pytest.raises((UnicodeError, SyntaxError)):
            _native_reader_signals(root)

    @pytest.mark.parametrize(
        "source",
        [
            'p = root.joinpath("ios", "Bain Luck", "event.json")',
            'p = root / ("i" + "os") / ("View." + "swi" + "ft")',
            "from reader_helper import read; read()",
            'subprocess.run(["python", "reader_helper.py"])',
            'p = inherited_root.glob("*.swift*")',
        ],
    )
    def test_missed_shapes_are_explicit_activation_holds(self, source):
        assert _native_signal_tags(source) == []  # never promote this to irrelevance


class TestNativeWholeRangeClassifier:
    PATH = "ios/Bain Luck/Bain Luck/Views/DiscoverView.swift"

    @pytest.mark.parametrize(
        "native",
        [PATH, "ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj", "ios/fixture.json"],
    )
    def test_native_only_is_prepared_native(self, repo, native):
        base = repo.commit({native: "a"})
        head = repo.commit({native: "b"})
        assert repo.scope(base, head) == "native"

    @pytest.mark.parametrize(
        "other",
        [
            "frontend/app/page.tsx",
            "backend/app/main.py",
            ".github/workflows/ci.yml",
            ".github/ci-native-backend-readers.txt",
            "backend/requirements.txt",
            "tools/native-gates.sh",
            "docs/rulings/001-x.md",
            "CLAUDE.md",
        ],
    )
    def test_mixed_range_is_full(self, repo, other):
        base = repo.commit({self.PATH: "a", other: "a"})
        head = repo.commit({self.PATH: "b", other: "b"})
        assert repo.scope(base, head) == "full"

    def test_shared_change_behind_native_tip_is_full(self, repo):
        base = repo.commit({"README.md": "a"})
        repo.commit({"backend/app/main.py": "x"})
        head = repo.commit({self.PATH: "a"})
        assert repo.scope(base, head) == "full"

    @pytest.mark.parametrize(
        "origin,destination",
        [
            ("backend/app/served.py", "ios/served.py"),
            ("ios/served.py", "frontend/served.py"),
        ],
    )
    def test_both_halves_of_moves_are_seen(self, repo, origin, destination):
        base = repo.commit({origin: "same"})
        head = repo.commit({destination: "same"}, removing=(origin,))
        assert repo.scope(base, head) == "full"

    def test_native_deletion_classifies_but_does_not_claim_reader_failure(self, repo):
        base = repo.commit({self.PATH: "a"})
        head = repo.commit({}, removing=(self.PATH,))
        assert repo.scope(base, head) == "native"

    @pytest.mark.parametrize("path", [PATH, "frontend/app/page.tsx"])
    @pytest.mark.parametrize("body", ["", "# comments only\n"])
    def test_empty_manifest_falls_back_full(self, repo, tmp_path, body, path):
        manifest = tmp_path / "empty-manifest"
        manifest.write_text(body)
        base = repo.commit({path: "a"})
        head = repo.commit({path: "b"})
        assert repo.scope(base, head, manifest) == "full"

    def test_manifest_parsing_error_falls_back_full(self, repo, tmp_path):
        manifest = tmp_path / "not-a-manifest"
        manifest.mkdir()
        base = repo.commit({self.PATH: "a"})
        head = repo.commit({self.PATH: "b"})
        assert repo.scope(base, head, manifest) == "full"

    def test_native_unknown_missing_head_and_empty_range_are_full(self, repo):
        base = repo.commit({self.PATH: "a"})
        for first, last in [
            (base, ""),
            (base, "deadbeef" * 5),
            (base, base),
            ("", base),
        ]:
            assert repo.scope(first, last) == "full"

    def test_native_preparation_preserves_no_release_subset(self, repo):
        release = REPO / ".github/scripts/heroku-release-required.sh"
        for path in (self.PATH, "ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj"):
            base = repo.commit({path: "a"})
            head = repo.commit({path: "b"})
            assert repo.scope(base, head) == "native"
            result = subprocess.run(
                ["bash", str(release), base, head],
                cwd=repo.path,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0 and result.stdout.strip() == "false"
