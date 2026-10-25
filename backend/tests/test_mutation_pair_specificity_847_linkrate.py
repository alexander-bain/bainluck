"""The M-REDIS mutant pair names its target instead of matching a prefix (#847).

CI 39362750752 failed `scan_mutation_residue.py` Pass B on PR #11313: the
saved-only link-rate reader in `admin_matching.py` was read as residue of
`futures_detail_sources_cache_mutations:M-REDIS` — the pair's replacement ended
in a bare `raise`, which is a prefix of the reader's genuine
`raise _LinkRateCacheReadError("redis_unavailable") from None`.

The pair now carries its target's next statement in both halves (the definition
reviewed on the cache branch at cebb13f442, byte-identical here). Every case
below runs the REAL scanner (real Pass A, real Pass B, real exit code) over that
one pair and a chosen file set, so it tests the shipped verdict rather than a
copy of its rule:

* the shipped link-rate reader scans CLEAN against the current pair;
* the same file scans RED against the pre-fix pair (the harvested pair minus
  its carried context) — the control that keeps the clean case from passing
  vacuously;
* the target with the actual mutant applied, copied anywhere, still scans RED;
* the re-anchored pair writes byte-for-byte the mutant the old pair wrote, so
  the fault it injects is unchanged and still aimed exactly once.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EVALS = BACKEND / "scripts" / "evals"
HARNESS = "futures_detail_sources_cache_mutations"
MID = "M-REDIS"
TARGET = BACKEND / "app" / "routes" / "futures.py"
READER = BACKEND / "app" / "routes" / "admin_matching.py"
TYPED_RAISE = 'raise _LinkRateCacheReadError("redis_unavailable") from None'

# What the re-anchored pair CARRIES beyond its pre-fix text, as (prefix,
# suffix). The pre-fix pair is the harvested pair with exactly this stripped,
# so the red control states the claim directly: the carried context is the
# whole difference. (Derived rather than pasted, so this file holds no mutant
# text for Pass B to read as residue.)
CARRIED = (
    "",
    "\n\n    source_breakdown = await _get_source_breakdown(db, outcome_ids)",
)


def _pair() -> tuple[str, str]:
    """The pair as the scanner HARVESTS it — out of process, because importing
    the harnesses here would leave `_mutation_guard` cached for later tests."""
    probe = textwrap.dedent(
        f"""
        import json, sys
        sys.path.insert(0, {str(EVALS)!r})
        import scan_mutation_residue as s
        pairs, unknown = s.harvest()
        assert not unknown, unknown
        hit = [p for p in pairs if (p.harness, p.mid) == ({HARNESS!r}, {MID!r})]
        assert len(hit) == 1, len(hit)
        print(json.dumps([hit[0].needle, hit[0].repl]))
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(BACKEND),
    )
    assert out.returncode == 0, f"harvest probe failed\n{out.stderr}"
    needle, repl = json.loads(out.stdout.strip().splitlines()[-1])
    return needle, repl


def _old_pair() -> tuple[str, str]:
    """The pre-fix pair: the harvested pair minus exactly what it carries."""
    needle, repl = _pair()
    pre, suf = CARRIED
    for text in (needle, repl):
        assert text.startswith(pre) and text.endswith(suf), "carried context moved"
    old_needle, old_repl = (t[len(pre) : len(t) - len(suf)] for t in (needle, repl))
    # The pre-fix replacement ended on a BARE raise — the prefix of a typed one.
    assert old_repl.endswith("\n        raise"), f"{old_repl!r} is not the old shape"
    return old_needle, old_repl


def _scan(
    files: list[Path], tmp_path: Path, *, old: bool
) -> subprocess.CompletedProcess:
    """The real scanner over ONE pair and an explicit Pass B file set."""
    pick = (
        f"[s.Pair({HARNESS!r}, {MID!r}, *{_old_pair()!r}, pathlib.Path({str(TARGET)!r}))]"
        if old
        else f"[p for p in s.harvest()[0] if (p.harness, p.mid) == ({HARNESS!r}, {MID!r})]"
    )
    probe = textwrap.dedent(
        f"""
        import sys, pathlib
        sys.path.insert(0, {str(EVALS)!r})
        import scan_mutation_residue as s
        pick = {pick}
        assert len(pick) == 1, pick
        s.harvest = lambda: (pick, [])
        s.REPO = pathlib.Path({str(tmp_path)!r})
        files = [pathlib.Path(f) for f in {[str(f) for f in files]!r}]
        s._files = lambda base, all_tracked, suffixes: files
        # Every probe file is new to the base, so nothing is excused as
        # pre-existing — the verdict is the pair's alone.
        s._base_already_has = lambda base, rel, literal: False
        sys.argv = ["scan"]
        sys.exit(s.main())
        """
    )
    return subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(BACKEND),
    )


def _copy_reader(tmp_path: Path) -> Path:
    source = READER.read_text()
    # The benign shape the old pair tripped on is really in the shipped reader.
    assert source.count(TYPED_RAISE) == 1, "the reader's typed raise moved"
    dst = tmp_path / f"benign_{READER.name}"
    dst.write_text(source)
    return dst


def test_the_shipped_link_rate_reader_scans_clean_against_the_current_pair(tmp_path):
    result = _scan([_copy_reader(tmp_path)], tmp_path, old=False)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "✅ CLEAN" in result.stdout, result.stdout
    assert "RESIDUE" not in result.stdout, result.stdout


def test_the_same_reader_was_red_against_the_pre_fix_pair(tmp_path):
    """The control: the reader really carries the shape that tripped CI."""
    copied = _copy_reader(tmp_path)
    result = _scan([copied], tmp_path, old=True)
    assert result.returncode == 1, f"{result.stdout}\n{result.stderr}"
    assert "🔴 RESIDUE" in result.stdout, result.stdout
    assert f"{copied.name}  <-  {HARNESS}:{MID}" in result.stdout, result.stdout


def test_a_copied_actual_mutant_still_fails_the_scan(tmp_path):
    needle, repl = _pair()
    copied = tmp_path / f"copied_{TARGET.name}"
    copied.write_text(TARGET.read_text().replace(needle, repl, 1))
    result = _scan([copied], tmp_path, old=False)
    assert result.returncode == 1, f"{result.stdout}\n{result.stderr}"
    assert "🔴 RESIDUE: 1 candidate" in result.stdout, result.stdout
    assert f"{copied.name}  <-  {HARNESS}:{MID}" in result.stdout, result.stdout


def test_the_re_anchored_pair_injects_the_same_fault_exactly_once():
    needle, repl = _pair()
    old_needle, old_repl = _old_pair()
    original = TARGET.read_text()
    assert original.count(needle) == 1, "needle not unique in its target"
    assert original.count(old_needle) == 1
    assert repl not in original, "the mutant is already in its target"
    # Byte-identical mutants: the extra context is carried, never changed.
    assert original.replace(needle, repl, 1) == original.replace(
        old_needle, old_repl, 1
    )
    assert original.replace(needle, repl, 1) != original
