#!/usr/bin/env bash
# #10708 (Alex 77: A) — the backend tests a pure-`ios/` candidate can reach.
#
# Usage (run from backend/):  bash ../.github/scripts/ci-native-tests.sh
# Prints ONE line: the sorted, de-duplicated backend-relative test paths.
#
#   native_tests = the validated roster (.github/ci-native-backend-readers.txt)
#                ∪ every tests/**/test_*.py whose text names a native path:
#                  `ios/`, a quoted `"ios"` path segment, or a quoted
#                  `.swift`/`.pbxproj`/`.xcodeproj`/`.plist`/`.entitlements` name.
#
# ── IT FAILS TOWARD "full". ─────────────────────────────────────────────────
# Any failure — roster refused, scan unreadable, nothing found — exits non-zero
# with NO output, and the workflow's caller turns that into scope `full`. A
# partial list is never printed: a reader left off it is a test that would not
# run on the candidate that can break it.
#
# The text scan is a superset of the spec's "contains ios/" (the quoted segment
# and file-name shapes are the guard's own signals in
# test_ci_cross_tier_manifest.py), so it errs toward running more tests.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

ROSTER_LINE="$(bash "$HERE/ci-native-backend-readers.sh")" || {
  echo "::error::native roster refused — scope falls back to full" >&2
  exit 1
}

python3 - "$ROSTER_LINE" <<'PY'
import pathlib
import re
import sys

PATTERNS = (
    re.compile(r"ios/"),
    re.compile(r"[\"']ios[\"']"),
    re.compile(r"[\"'][^\"'\n]*\.(?:swift|pbxproj|xcodeproj|plist|entitlements)[\"']"),
)

try:
    selected = set(sys.argv[1].split())
    if not selected:
        raise ValueError("empty roster line")
    root = pathlib.Path("tests")
    if not root.is_dir():
        raise ValueError("tests/ not found — run from backend/")
    scanned = 0
    for path in sorted(root.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")  # a decode failure refuses
        scanned += 1
        if any(p.search(text) for p in PATTERNS):
            selected.add(path.as_posix())
    if scanned == 0:
        raise ValueError("scanned no test files")
    missing = sorted(p for p in selected if not pathlib.Path(p).is_file())
    if missing:
        raise ValueError(f"selected test does not exist: {missing[0]}")
except (OSError, UnicodeError, ValueError) as error:
    print(f"::error::native test set refused: {error}", file=sys.stderr)
    sys.exit(1)
print(f"native test set: {len(selected)} files ({scanned} scanned)", file=sys.stderr)
print(" ".join(sorted(selected)))
PY
