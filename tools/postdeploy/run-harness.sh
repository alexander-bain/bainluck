#!/usr/bin/env bash
# UX-P122 — the post-deploy harness, wired by DISCOVERY instead of by a list.
#
# ## Why a second runner exists, and why it is not a fork
#
# `run-all.sh` names its five proofs in a hard-coded list. That list is how the
# harness came to print a clean summary while covering four of the five deployed
# branches: `program/ux-104` merged, deployed, and had **no proof at all**, and
# nothing in the output said so. The omission was invisible precisely because
# every row that WAS listed was green — which is the exact failure the harness
# was built to prevent, reproduced one level up. A registry that must be edited
# to add a check is a registry that will be forgotten.
#
# So this runner takes no list. It globs, and **a check is registered by
# existing**:
#
#     tools/postdeploy/{proof,verify,compare,gate}-*.sh   the original five
#     tools/postdeploy/checks/*.sh                        everything added since
#
# `run-all.sh` is deliberately left untouched and still works. This is not a
# fork of it: it discovers the same five scripts from disk rather than from a
# literal, so the two cannot disagree about what the harness contains. When the
# drain lands, `run-all.sh` should become a two-line shim onto this file.
#
# ## It also fixes #2120 from the CALLER side
#
# Three tools USED TO default to `/tmp/cal.json` — one treated it as a frozen baseline
# and two `curl -o` into it. UX-P121 watched that collision produce
# `calibration: FAIL — keys DISAPPEARED` against a payload that had not changed:
# the "baseline" was five seconds NEWER than the fresh fetch it was compared to.
# The tools themselves live in the barred set and are not edited here. But every
# one of them honours an env override, so this runner exports a private path per
# tool and the collision cannot occur under it. That is a mitigation, not the
# fix — #2120 still owns making the defaults safe and stamping serve mode into
# the baseline.
#
#   tools/postdeploy/run-harness.sh              # everything, read-only
#   tools/postdeploy/run-harness.sh --list       # what would run, and nothing else
#
# Verdicts: PASS(0) FAIL(1) UNKNOWN(3) NOT_DEPLOYED(4) TRANSPORT(5).
# Per gotcha #54's amendment: 1 is a result; anything else is a story about the
# harness, and is reported as such rather than folded into "not green".

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib.sh"

# ── #2120 mitigation: a private path per tool, never a shared one ────────────
#
# Only set when the caller has not. A caller that deliberately points two tools
# at one file is doing something this runner should not silently undo.
RUN_DIR="${HARNESS_DIR:-/tmp/postdeploy-run}"
mkdir -p "$RUN_DIR"
: "${CAL_BASELINE:=$RUN_DIR/cal-baseline.json}"
: "${CAL_FRESH:=$RUN_DIR/cal-fresh.json}"
: "${CAL_PAYLOAD:=$RUN_DIR/cal-payload.json}"
export CAL_BASELINE CAL_FRESH CAL_PAYLOAD

# ── discovery ────────────────────────────────────────────────────────────────
#
# `lib.sh` is executable and lives here too, so the globs are prefix-scoped
# rather than "every .sh in the directory". Adding a check means adding a file
# with one of these prefixes; adding shared plumbing means anything else.
declare -a SCRIPTS=()
for f in "$HERE"/proof-*.sh "$HERE"/verify-*.sh "$HERE"/compare-*.sh "$HERE"/gate-*.sh \
         "$HERE"/checks/*.sh; do
  [ -f "$f" ] || continue
  [ -x "$f" ] || { say "   ⚠️ not executable, SKIPPED: ${f#"$REPO_ROOT/"}"; continue; }
  SCRIPTS+=("$f")
done

if [ "${1:-}" = "--list" ]; then
  printf '%s\n' "${SCRIPTS[@]#"$REPO_ROOT/"}"
  exit 0
fi

if [ "${#SCRIPTS[@]}" -eq 0 ]; then
  say "no checks discovered under $HERE — that is a harness defect, not a green run"
  exit 3
fi

declare -a NAMES=() CODES=()

run_one() {
  local path="$1"
  local name; name="$(basename "$path" .sh)"
  "$path" > "$RUN_DIR/$name.log" 2>&1
  local rc=$?
  cat "$RUN_DIR/$name.log"
  NAMES+=("$name"); CODES+=("$rc")
}

say "=============================================================="
say " UX post-deploy proof harness (discovery runner)"
say " api: $BAINLUCK_API"
say " deployed: $(deployed_sha)"
say " origin/master: $(git -C "$REPO_ROOT" rev-parse --short origin/master 2>/dev/null)"
say " checks discovered: ${#SCRIPTS[@]}"
say " logs + payloads: $RUN_DIR"
say "=============================================================="

for f in "${SCRIPTS[@]}"; do
  run_one "$f"
done

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
    *) label="rc=$rc — NOT a test result. A non-1 non-zero means the check could not RUN (gotcha #54)." ;;
  esac
  printf '  %-32s %s\n' "${NAMES[$i]}" "$label"
  [ "$rc" -gt "$worst" ] && worst="$rc"
done

# ── coverage, stated rather than implied ─────────────────────────────────────
#
# The summary above is a list of verdicts. What sank #2060 was the list being
# read as a list of BRANCHES. So the runner says outright which unmerged
# branches nothing here covers — a green harness over an uncovered branch is the
# specific lie this section prevents.
#
# UX-P123: coverage is read from each check's DECLARATION, not from its file
# body. The first version grepped the whole file for the branch name, which this
# header already described as "declares … via its own REF" — the text was right
# and the implementation was not. Two live false positives resulted:
#
#   * `run-harness.sh`'s OWN header names `program/ux-104` while explaining the
#     ux-104 coverage gap, so the runner marked that branch covered by talking
#     about it. Delete `proof-2060-defect-routes.sh` and the row stayed green.
#   * `checks/gate-branch-surface.sh` names ux-100 and ux-105 in the prose
#     explaining why it does NOT cover them, which marked both covered.
#
# Prose that mentions a branch is the opposite of a proof of it, so a mechanism
# that reads the two as the same thing fails in the direction that hides work.
# A check now declares coverage on ONE line and only that line is read:
#
#     REF="${REF:-program/ux-104}"          one branch (the existing convention)
#     COVERS="program/ux-106 program/ux-107"   several
#
# `COVERS` wins when both are present. A check with neither declares nothing and
# covers nothing — which is correct for shared plumbing like
# `compare-calibration-baseline.sh`.

# declared_refs <script> — the branch refs a check DECLARES it gates on.
# Reads the declaration line only; the body is never consulted.
declared_refs() {
  local f="$1" line
  line="$(grep -m1 -E '^[[:space:]]*COVERS=' "$f" 2>/dev/null)"
  [ -z "$line" ] && line="$(grep -m1 -E '^[[:space:]]*REF=' "$f" 2>/dev/null)"
  [ -z "$line" ] && return 0
  printf '%s\n' "$line" | grep -oE 'program/ux-[0-9]+' | sort -u
}

hdr "BRANCH COVERAGE"
say "  Each check declares the branch it gates on via its own REF/COVERS line."
say "  Branches in the local stack that no check DECLARES are UNCOVERED. A check"
say "  merely mentioning a branch in prose does not cover it (UX-P123)."
uncovered=0
for br in $(git -C "$REPO_ROOT" branch --list 'program/ux-1[0-9][0-9]' --format='%(refname:short)' | sort); do
  namers=""
  for f in "${SCRIPTS[@]}"; do
    if declared_refs "$f" | grep -qx -- "$br"; then
      namers="$namers $(basename "$f")"
    fi
  done
  if [ -n "$namers" ]; then
    covered="covered by:$namers"
  else
    covered="UNCOVERED — no check declares it"
    uncovered=$(( uncovered + 1 ))
  fi
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$br" origin/master 2>/dev/null; then
    state="merged"
  else
    state="unmerged"
  fi
  printf '  %-22s %-10s %s\n' "$br" "$state" "$covered"
done
say ""
if [ "$uncovered" -eq 0 ]; then
  say "  BRANCH COVERAGE: complete — every branch in the stack is declared by a check."
else
  say "  BRANCH COVERAGE: $uncovered branch(es) UNCOVERED. That is a harness gap, not a"
  say "  green run — the row above is the whole point of this table."
fi

say ""
say "  the #2094 APPLY is deliberately not run from here:"
say "    tools/postdeploy/verify-2094-backfill.sh --apply"
say ""
say "  STILL OWED BY A HUMAN, and no harness can discharge it:"
say "    Alex's 5-shot capture + the 60s force-quit check (READY-ux-105.md)."
say "    Alex's rendered check on https://bainluck.com/event/14877917 (#2086)."
say "    One native Bad + reason chip, which is the only thing that can move"
say "    #2060's routing half off UNKNOWN."
exit "$worst"
