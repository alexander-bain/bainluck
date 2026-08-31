"""The shared restore guard for every on-disk mutation harness.

WHAT HAPPENED, because the fix is shaped by the specific way it failed

`bcdcd95f` carried an edit nobody made: `"terminal": "complete" if head and
not ...` had lost its `head and`. That is byte-for-byte mutation **M3** of
`typeahead_warmer_mutations.py`. The corroborating artifact was still on disk
— `/tmp/lat_p056_backups/typeahead_warmer.py`, pristine, directory mtime
**3 m 54 s before the commit**. The harness backed the file up and never
reached its restore, and the window that ran it recorded **exit 143**.

The residue then looked *expected*, because that same window was legitimately
editing that same file for #2072. A mutant survived review by landing in a
file somebody had a reason to be changing.

WHY `try/finally` ALONE WOULD NOT HAVE SAVED IT

Exit 143 is **SIGTERM**, and Python's default SIGTERM disposition terminates
the process outright: no exception is raised, so `finally` blocks do **not**
run. A harness wrapped only in `try/finally` would have written exactly the
same mutant to disk and reported exactly the same nothing. The guard therefore
installs handlers that convert the catchable signals into an exception, which
is what gives `finally` something to run on.

Four cases, and the fourth is stated rather than papered over:

  * exception / assertion         -> `finally` restores
  * KeyboardInterrupt (SIGINT)    -> `finally` restores
  * SIGTERM, SIGHUP (the tool cap)-> handler raises, `finally` restores
  * **SIGKILL, or the power going** -> UNCATCHABLE. Nothing runs.

For the fourth there is a **breadcrumb**: before the first mutation the guard
writes a manifest naming every target and its backup, and deletes it only
after a verified restore. A manifest still on disk therefore means "a run died
mid-mutation", and the next run — or `python3 -m scripts.evals._mutation_guard
--recover` — restores from it and says so loudly. It cannot prevent the
residue; it makes the residue **announce itself** instead of looking like an
ordinary uncommitted edit, which is the whole distance between this incident
and a caught one (gotcha #53's discipline: make the silent case loud).

WHY THIS IS ONE MODULE AND NOT FIVE `try/finally` BLOCKS

Ruling 022's lesson from `claim_lane_lock.py`, applied: a second path that
still works is a second path that still gets used, by the harness whose author
did not know about this one. Five copies of a subtle signal-handling block
would drift, and the drift would be invisible until the next dead window.

The two in-memory harnesses (`admin_auth_gate_mutations.py`,
`duration_sample_window_mutations.py`) need none of this: they `exec` a
mutated source STRING and never write to disk. That is strictly the better
design, and new harnesses should prefer it. This module exists for the ones
that must mutate a real file because their oracle is a pytest run.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import sys
from pathlib import Path

#: 🔴 THE MANIFEST AND THE BACKUPS ARE WORKTREE-UNIQUE (#2330, CERT-563).
#:
#: `/tmp` is shared by every checkout of this repo on this machine, and this
#: guard's recovery is UNCONDITIONAL: `start()` calls `recover()`, which restores
#: every target named by every manifest it finds. So two batteries running in two
#: worktrees — a build lane and the cert window, which is the ordinary case, not a
#: rare one — did this to each other:
#:
#:   1. run A writes mutant M to A's source file and starts its oracle;
#:   2. run B starts, `recover()` reads A's live manifest, decides A is a dead run
#:      and copies A's backup back over A's file — un-applying M *mid-oracle*;
#:   3. A's suite passes, because the mutant is no longer there;
#:   4. A prints `SURVIVED` for M, and `0 harness failures`.
#:
#: A false SURVIVED is the expensive direction: it reads as a missing assertion,
#: so the next session goes and writes a guard for a defect that was already
#: guarded. CERT-563 blocked on exactly one of these (`M18c` in
#: `prop_families_cache_mutations.py`, killed 1/1 when re-run alone). Backups
#: collided the same way — both runs used one path per FILENAME, so A could
#: restore B's bytes into A's tree when the two trees were on different branches.
#:
#: Two changes close it. The paths below are derived from the repo root, so two
#: worktrees cannot share a manifest or a backup; and `recover()` refuses to
#: restore anything belonging to a LIVE pid or to a tree that is not this one, so
#: even a shared or hand-repointed directory cannot resurrect the collision.
#:
#: `futures_source_breakdown_loose_scan_mutations.py` fixed this for itself in
#: #2330 by repointing `MANIFEST_DIR`. One harness of twenty-odd — which is the
#: shape ruling 022 warns about and this module's own docstring quotes: a second
#: path that still works is a second path that still gets used. The default is
#: now correct, so no harness needs to know.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Short, stable, and derived — never a literal, so a new worktree is namespaced
#: the moment it exists rather than when somebody remembers.
TREE = hashlib.sha1(str(_REPO_ROOT).encode()).hexdigest()[:10]

_DEFAULT_MANIFEST_DIR = Path(f"/tmp/bainluck_mutation_guard_{TREE}")

#: Where manifests lived before this was namespaced. Swept by `recover()` — under
#: the same live-pid and same-tree refusals — so residue written by a run that
#: predates this change is still recovered instead of being stranded, and swept
#: ONLY while nobody has repointed `MANIFEST_DIR` (a test that redirects it must
#: not reach into the real `/tmp` and start restoring another lane's files).
LEGACY_MANIFEST_DIR = Path("/tmp/bainluck_mutation_guard")

MANIFEST_DIR = _DEFAULT_MANIFEST_DIR


def _tree_scoped(path: Path) -> Path:
    """`path`, namespaced to this worktree. Idempotent."""
    if TREE in path.name:
        return path
    if path.suffix:  # a single-FILE backup path
        return path.with_name(f"{path.stem}_{TREE}{path.suffix}")
    return path.with_name(f"{path.name}_{TREE}")


def _pid_is_alive(pid: object) -> bool:
    """True when `pid` names a process that still exists.

    Conservative in the safe direction on both edges. An unreadable pid reads as
    ALIVE, and pid reuse can only produce a false ALIVE — both of which mean "do
    not restore", which leaves residue for `--check` and the residue scanner to
    announce loudly. The opposite error would silently overwrite a live run's
    source file, which is the whole defect this is closing.
    """
    if not isinstance(pid, int):
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by somebody else
    except OSError:
        return True
    return True


class MutationAborted(BaseException):
    """Raised in place of a fatal signal so `finally` gets to run.

    Inherits `BaseException`, not `Exception`, for the same reason
    `KeyboardInterrupt` does: harness inner loops catch broad `Exception` to
    score a mutant as SURVIVED/KILLED, and a shutdown must not be swallowed
    and recorded as a test result.
    """


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(label: str) -> Path:
    return MANIFEST_DIR / f"{label}.json"


def recover(verbose: bool = True) -> int:
    """Restore anything a previously killed run left mutated on disk.

    Returns the number of files restored. Safe to call when nothing is
    pending, which is why every guarded run calls it on the way in.
    """
    # The legacy directory is swept only while nobody has repointed the manifest
    # dir: a caller that redirects `MANIFEST_DIR` (a test, or a harness with its
    # own namespace) is declaring where its manifests live, and must not have this
    # function reach into the shared `/tmp` on its behalf.
    dirs = [MANIFEST_DIR]
    if MANIFEST_DIR == _DEFAULT_MANIFEST_DIR:
        dirs.append(LEGACY_MANIFEST_DIR)

    restored = 0
    for manifest in sorted(m for d in dirs if d.exists() for m in d.glob("*.json")):
        try:
            data = json.loads(manifest.read_text())
        except Exception:
            if verbose:
                print(f"  guard: unreadable manifest {manifest} — leaving it in place")
            continue

        # 🔴 A LIVE PID IS A RUN IN FLIGHT, NOT A DEAD ONE (CERT-563). This
        # function exists to clean up after a SIGKILL, and it used to assume that
        # every manifest it could see belonged to a corpse. A concurrent battery
        # in another worktree is not a corpse, and restoring its targets
        # un-applies the mutant it is measuring — turning a killed mutant into a
        # reported SURVIVED with no harness failure to give it away.
        if _pid_is_alive(data.get("pid")):
            if verbose:
                print(
                    f"  guard: {manifest} belongs to LIVE pid {data.get('pid')} "
                    f"({data.get('label')}) — a run in flight, not residue. "
                    "Left alone."
                )
            continue

        # 🔴 AND NEVER RESTORE ANOTHER CHECKOUT'S RUN (CERT-563). Manifests name
        # ABSOLUTE paths, so one written in another worktree resolves perfectly
        # well — straight into that worktree's working files. The test is who
        # WROTE it, not where the files are: a harness may legitimately guard a
        # target outside its own tree (the guard's own suite does exactly that
        # with `tmp_path`), and a path test would refuse those too.
        #
        # A manifest with no `root` predates this field. It is still recovered —
        # the live-pid refusal above is what protects it — because stranding real
        # residue to close a narrower hole would be the worse trade.
        foreign = bool(data.get("root")) and data.get("root") != str(_REPO_ROOT)
        if foreign:
            if verbose:
                print(
                    f"  guard: {manifest} was written by the checkout at "
                    f"{data.get('root')}, not {_REPO_ROOT} — another worktree's "
                    "run. Left alone."
                )
            continue

        for target_s, entry in (data.get("targets") or {}).items():
            target, backup = Path(target_s), Path(entry["backup"])
            if not backup.exists():
                if verbose:
                    print(
                        f"  🔴 guard: {target} was mutated by a dead run "
                        f"({data.get('label')}) and its backup {backup} is GONE. "
                        "Restore from git before trusting this tree."
                    )
                continue
            if target.exists() and sha(target) == entry["sha"]:
                continue  # already clean
            shutil.copy2(backup, target)
            restored += 1
            if verbose:
                print(
                    f"  🔴 guard: RESTORED {target} — left mutated by a dead run "
                    f"({data.get('label')}). That run's verdicts are void."
                )
        # A manifest naming somebody else's files is NOT ours to retire: deleting
        # it would destroy the only breadcrumb its own tree has (gotcha #53 — the
        # silent case must stay loud for the reader who can act on it).
        if not foreign:
            manifest.unlink(missing_ok=True)

    return restored


class _Guard:
    def __init__(self, targets, backup_dir, label: str):
        # Every caller-supplied backup path is namespaced to this worktree —
        # harnesses pass `/tmp` literals and two checkouts otherwise share one
        # backup per FILENAME, so a crash in either could restore the other's
        # bytes into this tree. `_tree_scoped` is idempotent, so a harness that
        # already namespaced its own path (#2330) is left exactly as it is.
        self._backup_spec = (
            {Path(k): _tree_scoped(Path(v)) for k, v in backup_dir.items()}
            if isinstance(backup_dir, dict)
            else backup_dir
        )
        self.targets = [Path(t) for t in targets]
        self.backup_dir = (
            Path("/tmp")
            if isinstance(backup_dir, dict)
            else _tree_scoped(Path(backup_dir))
        )
        self.label = label
        self.backups: dict[Path, Path] = {}
        self.original: dict[Path, str] = {}
        self._prev_handlers: dict[int, object] = {}

    # -- signals -------------------------------------------------------
    def _install(self) -> None:
        def _die(signum, _frame):
            raise MutationAborted(f"received signal {signum} ({signal.Signals(signum).name})")

        for sig in (signal.SIGTERM, signal.SIGHUP):
            with contextlib.suppress(ValueError, OSError, AttributeError):
                self._prev_handlers[sig] = signal.signal(sig, _die)

    def _uninstall(self) -> None:
        for sig, handler in self._prev_handlers.items():
            with contextlib.suppress(ValueError, OSError, TypeError):
                signal.signal(sig, handler)

    # -- lifecycle -----------------------------------------------------
    def start(self) -> "_Guard":
        recover()
        if not isinstance(self._backup_spec, dict) and not self.backup_dir.suffix:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

        entries = {}
        for target in self.targets:
            if isinstance(self._backup_spec, dict):
                backup = Path(self._backup_spec[target])
            elif self.backup_dir.suffix:  # a single-file backup path
                backup = self.backup_dir
            else:
                backup = self.backup_dir / target.name
            shutil.copy2(target, backup)
            self.backups[target] = backup
            self.original[target] = sha(target)
            entries[str(target)] = {"backup": str(backup), "sha": self.original[target]}

        _manifest_path(self.label).write_text(
            json.dumps(
                {
                    "label": self.label,
                    "pid": os.getpid(),
                    # Which checkout wrote this. `recover()` refuses to restore
                    # from a manifest naming a different one (CERT-563).
                    "root": str(_REPO_ROOT),
                    "targets": entries,
                },
                indent=2,
            )
        )
        self._install()
        return self

    def restore_all(self, verbose: bool = True) -> bool:
        """Put every target back and PROVE it, byte for byte."""
        clean = True
        for target, backup in self.backups.items():
            try:
                shutil.copy2(backup, target)
            except Exception as exc:  # noqa: BLE001 — must not mask the reason
                clean = False
                print(f"  🔴 guard: could not restore {target}: {exc!r}")
                continue
            if sha(target) != self.original[target]:
                clean = False
                print(
                    f"  🔴 guard: restore of {target} did NOT reproduce the original bytes. "
                    f"Backup: {backup}. Do not commit this tree."
                )
        if clean:
            _manifest_path(self.label).unlink(missing_ok=True)
        elif verbose:
            print(f"  guard: manifest kept at {_manifest_path(self.label)} — the tree is dirty")
        return clean

    def finish(self) -> None:
        self._uninstall()


@contextlib.contextmanager
def guarded_targets(targets, backup_dir, label: str):
    """Back up `targets`, and restore them on ANY exit a process can observe.

    ``backup_dir`` may be a directory (one backup per target, by filename) or,
    for the single-target harnesses, the backup FILE path itself — both shapes
    already exist in this directory and neither is worth a migration.
    """
    guard = _Guard(targets, backup_dir, label).start()
    try:
        yield guard
    finally:
        guard.restore_all()
        guard.finish()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--recover" in argv:
        n = recover()
        print(f"guard: restored {n} file(s) left behind by dead runs")
        return 0
    if "--check" in argv:
        # The same two directories `recover()` sweeps, for the same reason: a
        # manifest this command cannot see is a mutation this command reports as
        # absent.
        _dirs = [MANIFEST_DIR]
        if MANIFEST_DIR == _DEFAULT_MANIFEST_DIR:
            _dirs.append(LEGACY_MANIFEST_DIR)
        pending = sorted(m for d in _dirs if d.exists() for m in d.glob("*.json"))
        if not pending:
            print("guard: no mutation in flight")
            return 0
        for p in pending:
            print(f"🔴 guard: mutation IN FLIGHT or abandoned — {p}")
        return 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
