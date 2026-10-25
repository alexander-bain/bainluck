"""Two mutant pairs whose replacement text was a PREFIX, not a statement (#847).

CI 39362206640 failed `scan_mutation_residue.py` Pass B on PR #11309: the new
cache reader/producer in `precompute_admin_health.py` was read as residue of

* `futures_detail_sources_cache_mutations:M-REDIS` — its replacement ended in a
  bare `raise`, which is a prefix of the reader's genuine
  `raise _CoverageCacheReadError("redis_unavailable") from None`; and
* `typeahead_outcome_arm_mutations:M2-NO-LIMIT` — its replacement was a call's
  closing paren plus a bare-`noqa` handler, the shape of the producer's
  unrelated `run_db_panel(...)` call.

Both pairs now carry enough of their own target to name it. Every case below runs
the REAL scanner (real Pass A, real Pass B, real exit code) over one pair and a
chosen file set, so it tests the shipped verdict rather than a copy of its rule:

* the shipped producer files scan CLEAN against the current pair;
* the same files scan RED against the pre-fix pair (the harvested pair minus
  its carried context) — the control that keeps the clean case from passing
  vacuously;
* the target with the actual mutant applied, copied anywhere, still scans RED;
* the re-anchored pair writes byte-for-byte the mutant the old pair wrote, so
  the fault each mutant injects is unchanged and still aimed exactly once.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
EVALS = BACKEND / "scripts" / "evals"
PRODUCER = BACKEND / "app" / "tasks" / "precompute_admin_health.py"

# What each re-anchored pair CARRIES beyond its pre-fix text, as (prefix,
# suffix). The pre-fix pair is the harvested pair with exactly this stripped, so
# the red control below states the claim directly: the carried context is the
# whole difference. (Deriving it rather than pasting the c8d1 literals keeps
# this file from holding mutant text — `M1-NO-ORDER-BY`'s replacement is a line
# of the old M2 needle, and Pass B rightly reads a pasted copy as residue.)
CASES = {
    "M-REDIS": {
        "harness": "futures_detail_sources_cache_mutations",
        "target": BACKEND / "app" / "routes" / "futures.py",
        "benign": [PRODUCER],
        "carried": (
            "",
            "\n\n    source_breakdown = await _get_source_breakdown(db, outcome_ids)",
        ),
        # c8d1's replacement ended on a BARE raise — the prefix of a typed one.
        "old_repl_shape": lambda r: r.endswith("\n        raise"),
    },
    "M2-NO-LIMIT": {
        "harness": "typeahead_outcome_arm_mutations",
        "target": BACKEND / "app" / "routes" / "events.py",
        "benign": [
            PRODUCER,
            # Two handlers here were given "load bearing" comments solely to dodge
            # the old replacement; they are benign source and must stay so.
            BACKEND / "scripts" / "repair_statpal_fixture_id_blanks.py",
        ],
        "carried": (
            "                FuturesMarket.volume.desc().nulls_last(),\n            )\n",
            "",
        ),
        # c8d1's replacement BEGAN at a bare closing paren — any call's end.
        "old_repl_shape": lambda r: r.startswith(
            "        )\n    except Exception as exc:"
        ),
    },
}


def _pair(mid: str) -> tuple[str, str]:
    """The pair as the scanner HARVESTS it — out of process, because importing
    the harnesses here would leave `_mutation_guard` cached for later tests."""
    probe = textwrap.dedent(
        f"""
        import json, sys
        sys.path.insert(0, {str(EVALS)!r})
        import scan_mutation_residue as s
        pairs, unknown = s.harvest()
        assert not unknown, unknown
        hit = [p for p in pairs if (p.harness, p.mid) == ({CASES[mid]["harness"]!r}, {mid!r})]
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
    assert out.returncode == 0, f"{mid}: harvest probe failed\n{out.stderr}"
    needle, repl = json.loads(out.stdout.strip().splitlines()[-1])
    return needle, repl


def _old_pair(mid: str) -> tuple[str, str]:
    """The pre-fix pair: the harvested pair minus exactly what it carries."""
    needle, repl = _pair(mid)
    pre, suf = CASES[mid]["carried"]
    for text in (needle, repl):
        assert text.startswith(pre) and text.endswith(suf), (
            f"{mid}: carried context moved"
        )
    old = tuple(t[len(pre) : len(t) - len(suf)] for t in (needle, repl))
    assert CASES[mid]["old_repl_shape"](old[1]), (
        f"{mid}: {old[1]!r} is not the c8d1 shape"
    )
    return old


def _scan(
    mid: str, files: list[Path], tmp_path: Path, *, old: bool
) -> subprocess.CompletedProcess:
    """The real scanner over ONE pair and an explicit Pass B file set."""
    case = CASES[mid]
    pick = (
        f"[s.Pair({case['harness']!r}, {mid!r}, *{_old_pair(mid)!r}, "
        f"pathlib.Path({str(case['target'])!r}))]"
        if old
        else f"[p for p in s.harvest()[0] if (p.harness, p.mid) == ({case['harness']!r}, {mid!r})]"
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


def _copy_in(paths: list[Path], tmp_path: Path) -> list[Path]:
    out = []
    for i, src in enumerate(paths):
        dst = tmp_path / f"benign_{i}_{src.name}"
        dst.write_text(src.read_text())
        out.append(dst)
    return out


@pytest.mark.parametrize("mid", sorted(CASES))
def test_the_shipped_benign_source_scans_clean_against_the_current_pair(mid, tmp_path):
    files = _copy_in(CASES[mid]["benign"], tmp_path)
    result = _scan(mid, files, tmp_path, old=False)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "✅ CLEAN" in result.stdout, result.stdout
    assert "RESIDUE" not in result.stdout, result.stdout


@pytest.mark.parametrize("mid", sorted(CASES))
def test_the_same_source_was_red_against_the_pre_fix_pair(mid, tmp_path):
    """The control: the benign files really carry the shape that tripped CI."""
    files = _copy_in(CASES[mid]["benign"], tmp_path)
    result = _scan(mid, files, tmp_path, old=True)
    assert result.returncode == 1, f"{result.stdout}\n{result.stderr}"
    assert "🔴 RESIDUE" in result.stdout, result.stdout
    assert f"{files[0].name}  <-  {CASES[mid]['harness']}:{mid}" in result.stdout, (
        result.stdout
    )


@pytest.mark.parametrize("mid", sorted(CASES))
def test_a_copied_actual_mutant_still_fails_the_scan(mid, tmp_path):
    needle, repl = _pair(mid)
    original = CASES[mid]["target"].read_text()
    copied = tmp_path / f"copied_{CASES[mid]['target'].name}"
    copied.write_text(original.replace(needle, repl, 1))
    result = _scan(mid, [copied], tmp_path, old=False)
    assert result.returncode == 1, f"{result.stdout}\n{result.stderr}"
    assert "🔴 RESIDUE: 1 candidate" in result.stdout, result.stdout
    assert f"{copied.name}  <-  {CASES[mid]['harness']}:{mid}" in result.stdout, (
        result.stdout
    )


@pytest.mark.parametrize("mid", sorted(CASES))
def test_the_re_anchored_pair_injects_the_same_fault_exactly_once(mid):
    needle, repl = _pair(mid)
    old_needle, old_repl = _old_pair(mid)
    original = CASES[mid]["target"].read_text()
    assert original.count(needle) == 1, f"{mid}: needle not unique in its target"
    assert original.count(old_needle) == 1
    assert repl not in original, f"{mid}: the mutant is already in its target"
    # Byte-identical mutants: the extra context is carried, never changed.
    assert original.replace(needle, repl, 1) == original.replace(
        old_needle, old_repl, 1
    )
    assert original.replace(needle, repl, 1) != original
