#!/usr/bin/env bash
# UX-P119 item 3 — every post-drain proof, one command.
#
# The point of this file is the WINDOW, not the convenience: the drain is four
# branches deep, and the evidence owed against it has been accumulating for five
# cycles. Running the proofs one at a time, each with its own deploy check and
# its own remembering of what the pre-fix numbers were, is what turns a ten-minute
# verification into an afternoon. Each proof below carries its own gate, so this
# can be run the moment the deploy lands and it will honestly say NOT DEPLOYED
# for anything not yet in.
#
# Nothing here writes. `verify-2094-backfill.sh --apply` is the one write in the
# set and is deliberately NOT invoked from here.
#
#   tools/postdeploy/run-all.sh
#
# Verdicts: PASS(0) FAIL(1) UNKNOWN(3) NOT_DEPLOYED(4) TRANSPORT(5).
# Per gotcha #54's amendment: 1 is a result; anything else is a story about the
# harness, and is reported as such rather than folded into "not green".

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"

declare -a NAMES=() CODES=()

run_one() {
  local name="$1"; shift
  "$@" > "/tmp/postdeploy-$name.log" 2>&1
  local rc=$?
  cat "/tmp/postdeploy-$name.log"
  NAMES+=("$name"); CODES+=("$rc")
}

say "=============================================================="
say " UX post-drain proof harness"
say " api: $BAINLUCK_API"
say " deployed: $(deployed_sha)"
say " origin/master: $(git -C "$REPO_ROOT" rev-parse --short origin/master 2>/dev/null)"
say "=============================================================="

run_one 2065 "$HERE/proof-2065-feed-funnel.sh"
run_one 2084 "$HERE/proof-2084-duel-sum.sh"
run_one 2086 "$HERE/proof-2086-settled-markets.sh"
run_one 2094 "$HERE/verify-2094-backfill.sh"
run_one calibration "$HERE/compare-calibration-baseline.sh"

hdr "SUMMARY"
worst=0
for i in "${!NAMES[@]}"; do
  rc="${CODES[$i]}"
  case "$rc" in
    0) label="PASS" ;;
    1) label="FAIL" ;;
    3) label="UNKNOWN" ;;
    4) label="NOT DEPLOYED" ;;
    5) label="TRANSPORT" ;;
    *) label="rc=$rc" ;;
  esac
  printf '  %-14s %s\n' "${NAMES[$i]}" "$label"
  [ "$rc" -gt "$worst" ] && worst="$rc"
done
say ""
say "  logs: /tmp/postdeploy-*.log"
say "  the #2094 APPLY is deliberately not run from here:"
say "    tools/postdeploy/verify-2094-backfill.sh --apply"
say ""
say "  STILL OWED BY A HUMAN, and no harness can discharge it:"
say "    Alex's 5-shot capture + the 60s force-quit check (READY-ux-105.md)."
say "    That is what closes #1929 / #1937 — code shipped is not closure."
exit "$worst"
