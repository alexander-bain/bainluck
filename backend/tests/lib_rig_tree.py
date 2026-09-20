"""Copy a rig script into a synthetic tree together with whatever it sources.

WHY THIS EXISTS (native/261, from discover/241's find, 2026-09-20)
------------------------------------------------------------------
Several guard tests drive a COPY of a `tools/*.sh` rig script inside a tmp tree
they fully control, because the scripts resolve paths from their own location
and running the repo's copy would grade the lane's working tree instead of the
fixture. Each fixture therefore hand-listed the files it copied.

A hand-listed copy is a snapshot of the script's dependencies on the day it was
written, and the script keeps moving. `tools/reserved-sim-guard.sh` was factored
out on 2026-09-18 (`f933cc097`) and sourced by `native-shoot.sh` at line 86; the
fixture's list was one file behind, so all ten tests in
`test_native_shoot_binary_resolution.py` died on

    tools/native-shoot.sh: line 86: <tree>/tools/reserved-sim-guard.sh: No such file
    tools/native-shoot.sh: line 90: bl_default_shoot_sim: command not found

for two days. Nothing caught it: the band is macOS-only (BSD `stat`/`date`,
`simctl`), so CI skips it and only a Mac lane running the file sees red — and a
red it reads as "somebody else's stale tree".

So the list is DERIVED, not written. `copy_rig_script` reads the script, finds
the siblings it sources, copies those too, and recurses. A new `. "$(dirname
"$0")/x.sh"` in any rig script is picked up by every fixture on the next run
with no fixture edit — there is no list left to go stale.

AND AN UNRECOGNISED `source` LINE IS AN ERROR, NOT A SKIP. Silently copying too
little is precisely the failure above; a sourcing form this helper cannot read
raises here, in the fixture, naming the line — which is a fixable red, not a
mysterious one inside a subshell.
"""

import re
from pathlib import Path

# `. "$(dirname "$0")/name.sh"` — the one form every tools/ rig script uses.
_SIBLING_SOURCE = re.compile(r'^\s*(?:\.|source)\s+"\$\(dirname "\$0"\)/([^"/]+)"\s*$')
# Any line that sources anything at all, so an unreadable form cannot pass quietly.
_ANY_SOURCE = re.compile(r"^\s*(?:\.|source)\s+\S")


def rig_script_deps(script: Path) -> list[Path]:
    """Every sibling `script` sources, transitively, nearest-first.

    Raises on a source line this helper cannot parse, and on a dependency that
    is named but absent from the repo (which is a real broken script, not a
    fixture problem).
    """
    out: list[Path] = []
    seen = {script.resolve()}
    pending = [script]
    while pending:
        cur = pending.pop(0)
        for line in cur.read_text().splitlines():
            if not _ANY_SOURCE.match(line):
                continue
            m = _SIBLING_SOURCE.match(line)
            if not m:
                raise AssertionError(
                    f"{cur}: source line this fixture cannot follow — {line.strip()!r}. "
                    "Teach lib_rig_tree.py the form, or the copied tree will be incomplete."
                )
            dep = cur.parent / m.group(1)
            if dep.resolve() in seen:
                continue
            if not dep.is_file():
                raise AssertionError(f"{cur} sources {dep}, which does not exist in this checkout")
            seen.add(dep.resolve())
            out.append(dep)
            pending.append(dep)
    return out


def copy_rig_script(script: Path, dest_tools: Path) -> Path:
    """Write `script` and everything it sources into `dest_tools`; return the copy."""
    dest_tools.mkdir(parents=True, exist_ok=True)
    for f in [script, *rig_script_deps(script)]:
        (dest_tools / f.name).write_text(f.read_text())
    return dest_tools / script.name
