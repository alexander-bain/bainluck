"""Small local preflight for #11076: existing guards, exact checkout, known count.

Run after committing, before branch publication or review. No fetch, install,
database fixture, browser or Apple operation. Required hosted and pre-push
composed CI remain unchanged. This is deliberately not a dependency selector.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
GUARDS = (
    "tests/test_startup.py",
    "tests/test_ci_postgres_groups.py",
    "tests/test_ci_warning_free_counts_10708.py",
    "tests/test_ci_cross_tier_manifest.py",
    "tests/test_ci_matrix_required_contexts.py",
    "tests/test_ci_shard.py",
    "tests/test_pre_offer_gate.py",
)
WORKFLOW = ".github/workflows/ci.yml"
# One demonstrated failure, one explicitly supported invocation. Extend only
# with a concrete specimen; do not infer arbitrary shell/pytest semantics.
COUNT_FILE = "tests/integration/test_pm_stamp_release_wake_10090_pg.py"
COUNT_LOG = "/tmp/release-wake10090.txt"
# Specimen 2 (#10090 PR #11797): the same step also names whole PM skip-locked
# files after COUNT_FILE, and its pin counts every case of every named file.
EXTRA_FILE = re.compile(r"tests/integration/[A-Za-z0-9_]+\.py")
COLLECT = """
import json, sys, pytest
class Receipt:
    def pytest_collection_finish(self, session):
        print('PREFLIGHT_NODE_IDS=' + json.dumps([item.nodeid for item in session.items]))
raise SystemExit(pytest.main([*sys.argv[1:], '--collect-only', '-q', '-p', 'no:cacheprovider'], plugins=[Receipt()]))
"""


class Refusal(Exception):
    """Known failure or unavailable proof; never a successful skipped gate."""


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20
    )
    if proc.returncode:
        raise Refusal(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def checkout(root: Path, base: str, head: str) -> tuple[str, str, set[str]]:
    base_sha = git(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}")
    head_sha = git(root, "rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}")
    if git(root, "rev-parse", "HEAD") != head_sha:
        raise Refusal("requested head is not this checkout's HEAD")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise Refusal("checkout has uncommitted/untracked files; commit or isolate the candidate")
    git(root, "merge-base", "--is-ancestor", base_sha, head_sha)
    paths = git(root, "diff", "--name-only", "--no-renames", base_sha, head_sha)
    return base_sha, head_sha, set(paths.splitlines())


def offline_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        DATABASE_URL="postgresql+asyncpg://preflight:preflight@127.0.0.1:1/preflight",
        REDIS_URL="redis://127.0.0.1:1/0",
        SENTRY_DSN="",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_ADDOPTS="",
    )
    env.pop("SEARCH_TEST_DATABASE_URL", None)
    return env


def execute(command: list[str], cwd: Path, timeout: float = 600) -> str:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            command, cwd=cwd, env=offline_env(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    except OSError as exc:
        raise Refusal(f"cannot execute {command[0]}: {exc}") from exc
    try:
        output, _ = proc.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        # The group was created by this invocation; never touch another gate.
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise Refusal(f"own child interrupted/timed out: {shlex.join(command)}") from exc
    if proc.returncode:
        raise Refusal(
            f"exit {proc.returncode}: {shlex.join(command)}\n{output[-10000:]}"
        )
    print(f"PASS {shlex.join(command)} ({time.monotonic() - started:.1f}s)", flush=True)
    return output


def release_wake_pin(workflow: dict) -> int:
    """Read this known step's literal pin; never maintain a second numeric pin."""
    return release_wake_selection(workflow)[0]


def release_wake_selection(workflow: dict) -> tuple[int, list[str]]:
    """The step's literal pin and the whole test files its one pytest names."""
    steps = workflow["jobs"]["database-integration"]["steps"]
    matches = [s for s in steps if COUNT_FILE in s.get("run", "")]
    if len(matches) != 1:
        raise Refusal(f"{COUNT_FILE}: expected exactly one supported CI step")
    run = matches[0]["run"].replace("\\\n", " ")
    commands = re.findall(r"(?m)^\s*(?:if )?python(?:3)? -m pytest (.+)$", run)
    if len(commands) != 1:
        raise Refusal(f"{COUNT_FILE}: unsupported pytest invocation; no count proof")
    args = shlex.split(commands[0])
    files = args[:args.index("-v")] if "-v" in args else args
    rest = args[len(files):]
    # COUNT_FILE first, then only distinct whole files: a node id, -k, -m or
    # any other selector narrows the count and is not qualified.
    if (files[:1] != [COUNT_FILE] or len(set(files)) != len(files)
            or not all(EXTRA_FILE.fullmatch(f) for f in files[1:])
            or rest[:4] != ["-v", "-rs", ">", COUNT_LOG]):
        raise Refusal(f"{COUNT_FILE}: selection changed; qualify the invocation first")
    # Reject an additional selector after redirection rather than truncating it.
    if rest[4:] != ["2>&1;", "then"]:
        raise Refusal(f"{COUNT_FILE}: unsupported shell tail; no count proof")
    pins = re.findall(r'grep -qE "([^"]+)" ' + re.escape(COUNT_LOG), run)
    prefix, suffix = "[^0-9]", " passed[,[:space:]]"
    if len(pins) != 1 or not pins[0].startswith(prefix) or not pins[0].endswith(suffix):
        raise Refusal(f"{COUNT_FILE}: unsupported/missing exact summary pin")
    value = pins[0][len(prefix):-len(suffix)]
    if not value.isdecimal() or int(value) < 1:
        raise Refusal(f"{COUNT_FILE}: invalid count pin")
    return int(value), files


def check_release_wake(root: Path, paths: set[str]) -> None:
    config_names = {"pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py"}
    collection_changed = any(Path(path).name in config_names for path in paths)
    unchanged = "Count binding: known #10090 input unchanged; no collection needed"
    if not collection_changed and not any(
        path == WORKFLOW or path.startswith("backend/tests/integration/") for path in paths
    ):
        print(unchanged)
        return
    try:
        import yaml
        pin, files = release_wake_selection(yaml.safe_load((root / WORKFLOW).read_text()))
    except (ImportError, OSError, KeyError, TypeError, ValueError) as exc:
        raise Refusal(f"{COUNT_FILE}: cannot read authoritative workflow: {exc}") from exc
    if not collection_changed and not ({WORKFLOW, *("backend/" + f for f in files)} & paths):
        print(unchanged)
        return
    output = execute(
        [sys.executable, "-c", COLLECT, *files], root / "backend",
    )
    receipts = [line.removeprefix("PREFLIGHT_NODE_IDS=") for line in output.splitlines()
                if line.startswith("PREFLIGHT_NODE_IDS=")]
    if len(receipts) != 1:
        raise Refusal("collection did not return exactly one selected-node receipt")
    try:
        nodes = json.loads(receipts[0])
    except json.JSONDecodeError as exc:
        raise Refusal("invalid collection receipt") from exc
    if not isinstance(nodes, list) or not all(isinstance(n, str) and n.startswith(tuple(f + "::" for f in files)) for n in nodes):
        raise Refusal("collection returned unsupported node identities")
    if len(nodes) != pin:
        raise Refusal(f"{COUNT_FILE}: CI expects {pin} passed; actual collection selects {len(nodes)}")
    print(f"Count binding: {' + '.join(files)} selects {pin}; matches actual CI pin")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?", default="origin/master")
    parser.add_argument("head", nargs="?", default="HEAD")
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        base, head, paths = checkout(ROOT, args.base, args.head)
        print(f"Early preflight base={base} head={head}", flush=True)
        execute(
            [sys.executable, "-m", "pytest", *GUARDS, "-q", "-p", "no:cacheprovider"],
            ROOT / "backend",
        )
        execute(
            [sys.executable, "scripts/evals/scan_mutation_residue.py", "--base", base, "--head", head],
            ROOT / "backend",
        )
        check_release_wake(ROOT, paths)
        # Same unconditional, dependency-free contract command as hosted CI.
        execute(["npm", "run", "contract"], ROOT / "frontend/e2e")
        after = checkout(ROOT, base, head)
        if after[:2] != (base, head):
            raise Refusal("candidate changed while checks ran")
    except (Refusal, subprocess.TimeoutExpired) as exc:
        print(f"PREFLIGHT REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"early_preflight": "PASS", "base": base, "head": head,
                      "seconds": round(time.monotonic() - started, 2),
                      "scope": "named offline guards, Node contracts, known #10090 count binding only"}))
    print("Required hosted CI, independent review and full pre-push composed CI remain required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
