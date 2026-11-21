#!/usr/bin/env bash
# Shared runner for real-Postgres JUnit-verified CI acceptance gates.
#
# Extracted from inline `run:` blocks in `.github/workflows/ci.yml` so the
# workflow file stays comfortably below GitHub Actions' 512,000-byte parser
# ceiling while keeping every gate's exact refusals intact:
#   - missing/unparseable JUnit report -> fail
#   - 0 tests collected -> fail
#   - any skipped test -> fail (a skip is never green evidence)
#   - exact count mismatch (`--expected N`) or floor (`--min-tests N`) -> fail
#   - per-file nonzero check (`--require-file <stem>`, repeatable) -> fail
#   - required output line check (`--require-grep <regex>`) -> fail
#   - pytest exit code outside (0, 1) -> fail as harness error (gotcha #54)
#   - any failures, errors, or nonzero exit code -> fail

set -euo pipefail

LABEL=""
PASS_LABEL=""
JUNIT_PATH=""
LOG_PATH=""
EXPECTED=""
MIN_TESTS=""
REQUIRE_GREP=""
REQUIRE_GREP_MSG=""
REQUIRE_FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      LABEL="$2"
      shift 2
      ;;
    --pass-label)
      PASS_LABEL="$2"
      shift 2
      ;;
    --junit)
      JUNIT_PATH="$2"
      shift 2
      ;;
    --log)
      LOG_PATH="$2"
      shift 2
      ;;
    --expected)
      EXPECTED="$2"
      shift 2
      ;;
    --min-tests)
      MIN_TESTS="$2"
      shift 2
      ;;
    --require-grep)
      REQUIRE_GREP="$2"
      shift 2
      ;;
    --require-grep-msg)
      REQUIRE_GREP_MSG="$2"
      shift 2
      ;;
    --require-file)
      REQUIRE_FILES+=("$2")
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "::error::run-pg-junit-gate.sh: unknown option $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$LABEL" || -z "$JUNIT_PATH" || -z "$LOG_PATH" || $# -eq 0 ]]; then
  echo "::error::run-pg-junit-gate.sh: --label, --junit, --log, and pytest args after -- are required" >&2
  exit 2
fi

if [[ -z "$PASS_LABEL" ]]; then
  PASS_LABEL="$LABEL"
fi

PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3)}"

# `set +e` around pytest on purpose: a red suite must still reach the count,
# skip, and exit-code refusals below.
set +e
"$PYTHON_BIN" -m pytest "$@" --junitxml="$JUNIT_PATH" 2>&1 | tee "$LOG_PATH"
RC=${PIPESTATUS[0]}
set -e
echo "PYTEST EXIT CODE: $RC"

if [[ -n "$REQUIRE_GREP" ]]; then
  grep -E "$REQUIRE_GREP" "$LOG_PATH" || {
    echo "::error::${REQUIRE_GREP_MSG:-missing required line matching $REQUIRE_GREP}"
    exit 1
  }
fi

"$PYTHON_BIN" - "$RC" "$JUNIT_PATH" "$LABEL" "$PASS_LABEL" "$EXPECTED" "$MIN_TESTS" ${REQUIRE_FILES[@]+"${REQUIRE_FILES[@]}"} <<'PY'
import sys
import xml.etree.ElementTree as ET

rc = int(sys.argv[1])
junit_path = sys.argv[2]
label = sys.argv[3]
pass_label = sys.argv[4]
expected_raw = sys.argv[5]
min_tests_raw = sys.argv[6]
require_files = tuple(sys.argv[7:])

try:
    root = ET.parse(junit_path).getroot()
except Exception as exc:
    sys.exit(f"::error::{label} produced no junit report ({exc}) — NOT a pass")

s = root if root.tag == "testsuite" else root.find("testsuite")
t, f, e, k = (int(s.get(a, 0)) for a in ("tests", "failures", "errors", "skipped"))
print(f"tests={t} passed={t - f - e - k} failed={f} errors={e} skipped={k}")

if t == 0:
    sys.exit(f"::error::{label} collected ZERO tests — NOT a pass")
if k:
    sys.exit(f"::error::{label} SKIPPED {k} test(s) — a skip is never green evidence")
if expected_raw:
    expected = int(expected_raw)
    if t != expected:
        sys.exit(
            f"::error::{label} ran {t} tests, expected {expected} — tests were deselected or removed"
        )
if require_files:
    counts = {
        name: sum(name in case.get("classname", "").split(".") for case in s.iter("testcase"))
        for name in require_files
    }
    print(f"{label} cases by file: {counts}")
    min_tests = int(min_tests_raw) if min_tests_raw else 1
    if t < min_tests or not all(counts.values()):
        sys.exit(
            f"::error::{label} requires at least {min_tests} cases and nonzero cases "
            f"from all required files; got {t}, {counts}"
        )
elif min_tests_raw:
    min_tests = int(min_tests_raw)
    if t < min_tests:
        sys.exit(f"::error::{label} ran {t} tests, expected at least {min_tests}")
if rc not in (0, 1):
    sys.exit(f"::error::pytest exit {rc} is a harness story, not a result")
if f or e or rc:
    sys.exit(f"::error::{label} RED: {f} failed, {e} errors")
print(f"{pass_label} GREEN on all {t} tests")
PY
