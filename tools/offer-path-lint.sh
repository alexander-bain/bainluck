#!/usr/bin/env bash
#
# offer-path-lint.sh — find merge offers written where the desk cannot see them.
#
#   usage:  tools/offer-path-lint.sh [--hours N] [--all] [--no-fetch] [--repo-dir DIR]
#
#   exit 0  nothing actionable
#   exit 1  at least one INVISIBLE OFFER — a gated sha waiting in a directory nobody reads
#   exit 2  bad usage / not a repo
#
# ── WHY THIS IS A FILE AND NOT A PARAGRAPH ───────────────────────────────────
#
# Standing notice 31, amended Fri 2026-09-11 1:35pm PT:
#
#     An offer exists only in `runner-inbox/integrator/`. The desk reads that
#     directory and nothing else.
#
# It had to be amended because on 9/11 the rule was broken twice in one
# afternoon, by two different lanes, in two different ways:
#
#   live/155   wrote a correct, complete, GREEN-certed merge request for #5247
#              — a p1: a US Open semifinal page printing "50%" off an empty
#              order book — to the `.claude/handoff/` ROOT at 19:25Z, then
#              polled the desk lock from 19:24Z waiting for a request the desk
#              structurally could not see. The lane was not idle. It was
#              blocked on something that did not exist.
#
#   calibration/1110  CERT-2632 (#2637) went GREEN at 18:24Z and was still
#              unoffered and unmerged 2h21m later, found only because
#              integrator/309 swept the ledger against master ancestry on a
#              hunch. Same outcome, no misfiled file at all.
#
# THE TRAP IS NOT CARELESSNESS. The handoff root contains ~21 files named
# `NOTE-TO-INTEGRATOR-FROM-<LANE>-*.md`, left there by the convention that
# preceded the inbox. A lane that goes looking for "how do I write an offer"
# finds a large, consistent, confidently-named body of precedent — and it is
# the wrong answer. Copying what you see in that directory is the failure mode.
#
# ── WHAT THIS LINT REFUSES TO BE ─────────────────────────────────────────────
#
# A grep for `NOTE-TO-INTEGRATOR*` in the root prints 21 hits on a clean tree.
# A check that cries every run is a check nobody runs. So a name match alone is
# NOT a finding here. A file is reported as an INVISIBLE OFFER only when all of:
#
#   1. it is offer-SHAPED by name, and sits in the handoff root;
#   2. it is not marked `.consumed` / `.superseded` / `.failed` / `.running`;
#   3. it names a sha that git can resolve;
#   4. that sha is NOT an ancestor of origin/master — an already-landed sha is
#      a historical note, not a pending offer (notice 31's first clause);
#   5. NO file in `runner-inbox/integrator/` mentions that sha — because a lane
#      that wrote to both places is fine, and notice 36 explicitly permits a
#      copy to the desk. Only the sha the desk has NO path to is a defect.
#
# Condition 5 is the one that makes this decisive rather than nagging, and
# condition 4 is what keeps the 21 historical files quiet.
#
# Everything that is offer-shaped but fails 2–5 is COUNTED, not listed. Pass
# `--all` to see it, e.g. for a one-time cleanup of the root.
#
# ── THE SECOND HALF OF THE BUG ───────────────────────────────────────────────
#
# calibration/1110's token was never written down anywhere, so no filename lint
# could ever have found it. That half is the desk's ledger-ancestry sweep
# (notice 31(b)), not this script. This tool closes the misfiled-offer half and
# says so; it does not claim to close the other. Run both.
#
set -uo pipefail

HOURS=48
SHOW_ALL=0
NO_FETCH=0
REPO_DIR="${REPO_DIR:-$(pwd)}"

while [ $# -gt 0 ]; do
  case "$1" in
    --hours)    HOURS="${2:-}"; shift 2 ;;
    --all)      SHOW_ALL=1; shift ;;
    --no-fetch) NO_FETCH=1; shift ;;
    --repo-dir) REPO_DIR="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "offer-path-lint: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

case "$HOURS" in ''|*[!0-9]*) echo "offer-path-lint: --hours needs a whole number" >&2; exit 2 ;; esac

G() { git -C "$REPO_DIR" "$@"; }
G rev-parse --git-dir >/dev/null 2>&1 || { echo "offer-path-lint: $REPO_DIR is not a git repo" >&2; exit 2; }

ROOT="$REPO_DIR/.claude/handoff"
INBOX="$ROOT/runner-inbox/integrator"
[ -d "$ROOT" ]  || { echo "offer-path-lint: no $ROOT" >&2; exit 2; }
[ -d "$INBOX" ] || { echo "offer-path-lint: no $INBOX" >&2; exit 2; }

# notice 44: the interactive lane `grep` is a ugrep wrapper whose -qv is inverted.
# Gates use the real binary explicitly. (`bash script.sh` is unaffected, but a
# reader who lifts a line out of here into a shell is not.)
GREP=/usr/bin/grep
[ -x "$GREP" ] || GREP=grep

# The fetch is the whole cost of this tool: 0.4s of work behind a ~53s fetch on
# this box. It matters because ancestry (condition 4) is answered against
# origin/master, and a STALE master makes a landed sha read as unlanded — a
# FALSE FINDING. That direction is the safe one (it says "go look at this file"
# about a file that is fine), so --no-fetch is offered for a quick pass, and the
# age of the ref is printed either way so a stale answer is never silent.
FETCH_NOTE=""
if [ "$NO_FETCH" -eq 1 ]; then
  FETCH_NOTE="skipped (--no-fetch)"
elif G fetch origin master -q 2>/dev/null; then
  FETCH_NOTE="ok"
else
  FETCH_NOTE="FAILED — ancestry below is answered against a stale ref"
fi

MASTER_SHORT="$(G rev-parse --short origin/master 2>/dev/null || echo '?')"
MASTER_AGE="$(G log -1 --format='%cr' origin/master 2>/dev/null || echo '?')"

echo "offer-path-lint  root=$ROOT"
echo "                 inbox=$INBOX"
echo "                 window=${HOURS}h   master=$MASTER_SHORT ($MASTER_AGE)   fetch=$FETCH_NOTE"
echo

# Every sha mentioned anywhere in the inbox, in a FILENAME or in a body: a tray
# entry that names a sha in its prose counts as the desk being able to see it.
# Hex tokens only, deduped — the inbox is ~1,200 files and slurping them whole
# is both slow and pointless. `find -print0`/`xargs -0` because the glob would
# blow ARG_MAX at that count.
INBOX_SHAS="$(
  { ls -1 "$INBOX" 2>/dev/null
    find "$INBOX" -maxdepth 1 -type f -print0 2>/dev/null | xargs -0 cat 2>/dev/null
  } | $GREP -oE '\b[0-9a-f]{7,40}\b' 2>/dev/null | cut -c1-8 | sort -u
)"

# Offer-shaped: the families lanes actually produce, plus anything that says
# MERGE-OFFER anywhere in the name. Deliberately broad — the cheap half of the
# test is the name, the decisive half is conditions 4 and 5 below.
#
# ONE `ls | grep` pass, not a loop. The handoff root holds ~4,000 files, and the
# obvious `for f in "$ROOT"/*` with a basename+grep per file costs 78 SECONDS
# against 0.065s for this — measured, 1,200x. A three-minute lint does not get
# run before a merge, so the shape of this loop is part of whether the check
# works at all.
CANDIDATES=()
while IFS= read -r b; do
  [ -n "$b" ] || continue
  [ -f "$ROOT/$b" ] || continue
  CANDIDATES+=("$ROOT/$b")
done < <(ls -1 "$ROOT" 2>/dev/null | $GREP -iE '^(NOTE-TO-INTEGRATOR|MERGE-OFFER|BATCH-MERGE-OFFER|MERGE-REQUEST)|MERGE-OFFER' || true)

n_total=${#CANDIDATES[@]}
n_marked=0; n_old=0; n_nosha=0; n_landed=0; n_seen=0
FINDINGS=()
QUIET=()

now="$(date +%s)"
for f in "${CANDIDATES[@]}"; do
  b="$(basename "$f")"

  # (2) resolved states — a marked file is a record, not a request.
  # Bash-native, no subprocess: this runs once per candidate and the whole point
  # of the pass above is not to spend processes here.
  if [[ "$b" =~ \.(consumed|superseded|failed|running) ]]; then
    n_marked=$((n_marked+1)); QUIET+=("marked     $b"); continue
  fi

  # age
  mt="$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)"
  age_h=$(( (now - mt) / 3600 ))
  if [ "$SHOW_ALL" -eq 0 ] && [ "$age_h" -gt "$HOURS" ]; then
    n_old=$((n_old+1)); QUIET+=("aged ${age_h}h   $b"); continue
  fi

  # (3) a sha we can resolve: prefer a full 40, else the first plausible short one.
  # Resolved in ONE `cat-file --batch-check` per file, not one subprocess per
  # candidate token: the naive loop is ~25 git invocations x every candidate and
  # takes minutes on this repo, which is the same as not having the check.
  sha="$(
    { $GREP -oE '\b[0-9a-f]{40}\b' "$f" 2>/dev/null | head -5
      $GREP -oE '\b[0-9a-f]{7,12}\b' "$f" 2>/dev/null | head -20
    } | awk '!seen[$0]++' | sed 's/$/^{commit}/' \
      | G cat-file --batch-check 2>/dev/null \
      | awk '$2=="commit"{print $1; exit}'
  )"
  if [ -z "$sha" ]; then
    n_nosha=$((n_nosha+1)); QUIET+=("no sha     $b"); continue
  fi

  # (4) already landed ⇒ historical note, not a pending offer.
  if G merge-base --is-ancestor "$sha" origin/master 2>/dev/null; then
    n_landed=$((n_landed+1)); QUIET+=("landed     ${sha:0:8}  $b"); continue
  fi

  # (5) does the desk have ANY path to this sha?
  if printf '%s\n' "$INBOX_SHAS" | $GREP -qxF "${sha:0:8}"; then
    n_seen=$((n_seen+1)); QUIET+=("in inbox   ${sha:0:8}  $b"); continue
  fi

  FINDINGS+=("$sha|$b|$age_h")
done

if [ "$SHOW_ALL" -eq 1 ] && [ ${#QUIET[@]} -gt 0 ]; then
  echo "=== offer-shaped files in the root that are NOT findings ==="
  printf '  %s\n' "${QUIET[@]}"
  echo
fi

echo "=== scanned ==="
echo "  $n_total offer-shaped file(s) in the handoff root"
echo "  quiet: $n_marked marked · $n_old older than ${HOURS}h · $n_nosha no resolvable sha · $n_landed already on master · $n_seen also in the inbox"
echo

if [ ${#FINDINGS[@]} -eq 0 ]; then
  echo "PASS — no invisible offers."
  echo
  echo "This says nothing about a token that was never written down at all"
  echo "(calibration/1110, CERT-2632). For that half, sweep TOKEN GRANTED ledger"
  echo "rows against origin/master ancestry — standing notice 31(b)."
  exit 0
fi

echo "!!! INVISIBLE OFFER — ${#FINDINGS[@]} file(s) the desk cannot see !!!"
echo
for row in "${FINDINGS[@]}"; do
  IFS='|' read -r sha b age <<< "$row"
  echo "  file  $b"
  echo "  age   ${age}h old, unmarked"
  echo "  sha   $sha"
  echo "        $(G log -1 --format='%s' "$sha" 2>/dev/null | cut -c1-72)"
  echo "        not on master; no file in runner-inbox/integrator/ mentions it"
  echo
done

cat <<EOF
THE DESK READS \`runner-inbox/integrator/\` AND NOTHING ELSE (standing notice 31).

A file in \`.claude/handoff/\` is not an offer, however it is named. The root holds
~21 historical NOTE-TO-INTEGRATOR-* files from the pre-inbox convention; they are
precedent for nothing.

  mv .claude/handoff/<file> .claude/handoff/runner-inbox/integrator/

Then gate the sha before you wait on it:

  git -C $REPO_DIR show origin/master:tools/merge-gate.sh | bash -s -- <sha>

And if you are a lane polling the desk lock: re-check that your own offer file is
actually in the inbox before you wait another window. That is the whole of what
went wrong on 9/11 — the lane was blocked on a request that did not exist.
EOF
exit 1
