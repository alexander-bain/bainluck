#!/usr/bin/env bash
# #10708 INACTIVE roster preparation. Run from backend/.
# Validate the entire roster before emitting one normalized pytest-path line.
# Workflow adoption, transitive reach and exact residue range remain unpaid.
set -uo pipefail
ROSTER="${CI_NATIVE_BACKEND_READERS:-$(dirname "$0")/../ci-native-backend-readers.txt}"
python3 - "$ROSTER" <<'PY'
import pathlib
import re
import sys

try:
    roster = pathlib.Path(sys.argv[1])
    if roster.stat().st_size > 65536:
        raise ValueError("roster exceeds 64 KiB bound")
    paths = []
    for raw in roster.read_text(encoding="utf-8").splitlines():
        value = raw.split("#", 1)[0].strip()
        if not value:
            continue
        if not re.fullmatch(r"tests/(?:[A-Za-z0-9_-]+/)*test_[A-Za-z0-9_.-]+\.py", value):
            raise ValueError(f"invalid backend-relative test path: {value!r}")
        if value in paths:
            raise ValueError(f"duplicate roster entry: {value}")
        if not pathlib.Path(value).is_file():
            raise ValueError(f"listed test does not exist: {value}")
        paths.append(value)
    if not paths:
        raise ValueError("empty roster")
except (OSError, UnicodeError, ValueError) as error:
    print(f"::error::native roster refused: {error}", file=sys.stderr)
    sys.exit(1)
print(" ".join(paths))
PY
