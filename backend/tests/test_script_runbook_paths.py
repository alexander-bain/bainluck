"""A `heroku run` runbook line in a script must name the path the dyno has.

The slug root is `backend/` — that is where the Procfile lives, so `/app` on the
dyno IS `backend/`. A runbook that says `python3 backend/scripts/foo.py` fails
with

    python3: can't open file '/app/backend/scripts/foo.py': [Errno 2] ...

and exits 2. That is not a loud failure in practice: the operator runs it
`:detached` (gotcha #48), reads an empty stdout, and the natural next move is to
re-run rather than to re-read the path. It cost a real repair session on #7188,
where the applying lane burned three detached runs and two log windows before
noticing.

Ten scripts carried the wrong form against 69 with the right one, so this is a
convention that already existed and was drifting, not a new rule.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"

#: `heroku run …  python3 <path>` in any of its flag spellings (`-a app`,
#: `--app app`, `run:detached`), capturing the script path the dyno is handed.
RUNBOOK = re.compile(
    r"heroku\s+run(?::detached)?\s+"
    r"(?:-a|--app)\s+[\w-]+\s+(?:--\s+)?"
    r"python3?\s+(\S+\.py)"
)


def _runbook_lines():
    """(file, lineno, path) for every heroku-run invocation in backend/scripts."""
    for path in sorted(SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in RUNBOOK.finditer(line):
                yield path, lineno, match.group(1)


def test_the_slug_root_is_backend():
    """The premise. If the Procfile moves, this test's rule is wrong, not the scripts."""
    assert (BACKEND / "Procfile").is_file(), (
        "backend/Procfile is what makes `backend/` the slug root; if it moved, "
        "re-derive the rule below before editing any runbook."
    )


def test_the_corpus_is_not_empty():
    """Guard against the whole suite passing because the regex matched nothing."""
    found = list(_runbook_lines())
    assert len(found) >= 40, (
        f"only {len(found)} heroku-run runbook lines matched under {SCRIPTS}; "
        "the regex has drifted away from how these runbooks are written"
    )


def test_no_runbook_points_at_a_path_the_dyno_does_not_have():
    offenders = [
        f"{path.relative_to(BACKEND)}:{lineno}  ->  {script_path}"
        for path, lineno, script_path in _runbook_lines()
        if script_path.startswith("backend/")
    ]
    assert not offenders, (
        "the slug root is `backend/`, so a runbook path must be relative to it "
        "(`scripts/foo.py`, not `backend/scripts/foo.py`). Offenders:\n  "
        + "\n  ".join(offenders)
    )
