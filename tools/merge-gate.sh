#!/usr/bin/env bash
#
# merge-gate.sh — run every standing merge gate against one sha and say STOP or GO.
#
#   usage:  tools/merge-gate.sh <sha> [<repo-path>]
#
# ── WHY THIS IS A FILE AND NOT A PARAGRAPH ───────────────────────────────────
#
# Notices 13, 18, 28, 31 and 32 are five hand-typed commands that a lane runs
# before every merge, from memory, at the end of a session, usually inside an
# eighteen-minute push window. Each has already been got wrong in production:
#
#   notice 28  `?head_sha=` with an abbreviated sha returns a valid EMPTY result
#              at exit 0 — indistinguishable from "CI never ran" (lane1/221).
#              And the runs list PAGES AT 30, so a master sha with 47 runs can
#              hold no CI row on page one (#4221, the fifth occurrence).
#   notice 32  the obvious `.output.title|test(...)` form ABORTS at the first
#              null title — `deploy` is element 0 on real shas — printing a jq
#              error to stderr and NOTHING to stdout, i.e. an empty refusal set
#              that examined one run (three independent reproductions).
#   notice 18  the plain `supersedes.*CERT-N` grep fires a FALSE STOP on exactly
#              the repair certs that grade first, because a repair row cites its
#              own id after the word "supersedes".
#
# Every one of those is a wrong answer that LOOKS like the right answer. That is
# the class of thing that belongs in a file with the reasoning attached, not in
# prose a tired session retypes.
#
# ── IT RUNS UNDER bash, DELIBERATELY ─────────────────────────────────────────
#
# `#!/usr/bin/env bash`, and every `grep` below is `/usr/bin/grep`. In a lane's
# interactive shell `grep` is a function wrapping ugrep 7.8.4, whose `-qv` is the
# bit-flip of its `-q` — "does NO line match?" rather than "is at least one line
# not matching?" (#5037). The two agree on all-match and no-match input and
# diverge only on MIXED input, toward "confined", which is the fail-open
# direction for every "is this change confined to one tree?" test. A `#!` script
# does not source the snapshot and so is already safe; the explicit paths are
# here so that copying a line OUT of this file into a lane shell stays safe too.
#
# ── WHAT IT CANNOT DO ────────────────────────────────────────────────────────
#
# A GO is true at the instant it is printed and not one second longer. Ancestry,
# PR mergeability and the push window all move under you (notice 29's amendment
# exists because a window was computed from elapsed sleeps and could never say
# "outside"). Run this again INSIDE the push, and read the clock there too.
#
# It also does not grade. A GO means the paperwork is in order for a sha someone
# else already certed; it is never a substitute for the cert.

set -uo pipefail

SHA_IN="${1:-}"

# `${BASH_SOURCE[0]}` is UNBOUND — and fatal under `set -u` — when this script is
# piped rather than executed, which is exactly how a lane runs it before it is
# merged: `git show <branch>:tools/merge-gate.sh | bash -s -- <sha>`. Deriving
# the repo from it then produced `repo=/` and a "not a git repository" refusal
# on a perfectly good sha. Ask git where we are instead; it is also the right
# answer when the script is invoked from a subdirectory.
SELF="${BASH_SOURCE[0]:-}"
REPO_PATH="${2:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REPO_SLUG="alexander-bain/bainluck"
LEDGER="${MERGE_GATE_LEDGER:-$HOME/bainluck/.claude/handoff/CODEX-CERT-LOG.md}"
GREP=/usr/bin/grep

if [ -z "$SHA_IN" ]; then
  echo "usage: tools/merge-gate.sh <sha> [<repo-path>]" >&2
  echo "       tools/merge-gate.sh --selftest" >&2
  exit 2
fi

# ─────────────────────────────────────────────────────────────────────────────
# --selftest — the guard for the guard. Offline, read-only, touches no remote.
#
# It lives inside the script rather than in `backend/tests/` on purpose: a test
# under `backend/tests/**` forces a Heroku release (notice 10), so guarding a
# LOCAL shell tool would make every edit to it wait for a server-side batch.
# One command, no network, no fixtures.
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SHA_IN" = "--selftest" ]; then
  self="$SELF"
  if [ -z "$self" ] || [ ! -r "$self" ]; then
    # The selftest reads its own source, so it needs a file. Piped in, there
    # isn't one — say so instead of failing every scan for the wrong reason.
    echo "  --selftest needs the script on disk; run tools/merge-gate.sh --selftest, not a pipe" >&2
    exit 2
  fi
  fails=0
  check () {
    if eval "$2" >/dev/null 2>&1; then
      echo "  ok    $1"
    else
      echo "  FAIL  $1"
      fails=$((fails + 1))
    fi
  }

  echo "merge-gate --selftest"

  # The reason this file exists at all. A bare `grep` in a lane's interactive
  # shell is ugrep, whose `-qv` is the bit-flip of `-q` and fails OPEN (#5037).
  # This script is read by people who then paste lines out of it.
  # Comments are stripped first: this file TALKS about `grep -qv` at length, and
  # a scan that cannot tell prose from a command would either fire constantly or
  # be written loose enough to miss the real thing.
  bare_greps="$(sed -e 's/#.*//' "$self" | /usr/bin/grep -cE '(^|[;&|(]|[[:space:]])grep[[:space:]]')"
  # The label deliberately avoids spelling the token it scans for: written the
  # obvious way ("no bare grep is executed") the check MATCHES ITS OWN LABEL and
  # reports one permanent failure. That is funny once and confusing forever.
  check "every pattern match is /usr/bin/... or \$GREP (bare calls found: ${bare_greps:-0})" \
    "[ ${bare_greps:-0} -eq 0 ]"

  check "runs under bash, which does not source the ugrep snapshot" \
    "head -1 '$self' | /usr/bin/grep -q 'bash'"

  # Notice 28's amendment: an abbreviated or unpushed sha returns a valid EMPTY
  # result, so the script must never reach the API with anything but 40 hex.
  check "the runs API is only ever called with per_page=100" \
    "! /usr/bin/grep -q 'actions/runs?head_sha=[^\"]*' '$self' || /usr/bin/grep -q 'per_page=100' '$self'"

  # Notice 32's two amendments, both of which cost three lanes a wrong answer.
  check "check-runs jq guards a null title with // \"\"" \
    "/usr/bin/grep -q '(.output.title) // \"\"' '$self'"
  check "check-runs is gated on the EXIT CODE, not on empty stdout" \
    "/usr/bin/grep -q 'refusal_rc' '$self'"

  # Notice 18: a repair row cites its own id after "supersedes".
  check "the supersedes scan excludes the cert's own row" \
    "/usr/bin/grep -q -- '-vc \"| \$CERT_ID --\"' '$self'"

  check "rev-parse is verified, not trusted to be empty on failure" \
    "/usr/bin/grep -q 'rev-parse --verify --quiet' '$self'"

  # Behavioural: an unresolvable ref must exit 2, not sail on. `git rev-parse`
  # echoes its input back and exits 128, so this is a real regression risk.
  out="$(bash "$self" deadbeefdeadbeefdead 2>&1)"; rc=$?
  check "an unresolvable sha exits 2 (git rev-parse echoes bad input back)" "[ $rc -eq 2 ]"

  out="$(bash "$self" 2>&1)"; rc=$?
  check "no argument exits 2" "[ $rc -eq 2 ]"

  # The regression that made this fix necessary: piped in, `BASH_SOURCE[0]` is
  # unbound under `set -u` and the repo path fell back to `/`.
  piped="$(cat "$self" | bash -s -- --help-nonexistent-sha 2>&1)"
  check "piped into bash it still finds the repo, not /" \
    "! printf '%s' \"\$piped\" | /usr/bin/grep -q 'not a git repository: /$'"

  echo
  if [ "$fails" -eq 0 ]; then
    echo "  selftest: PASS"
    exit 0
  fi
  echo "  selftest: $fails FAILED"
  exit 1
fi

stops=0
warns=0

# `pass`/`stop`/`warn` are the only three verdicts. A gate that cannot be
# EVALUATED is a `stop`, never a `warn` — an unreadable ledger and a clean
# ledger must not look the same.
pass () { printf '  \033[32mPASS\033[0m  %-26s %s\n' "$1" "$2"; }
warn () { printf '  \033[33mWARN\033[0m  %-26s %s\n' "$1" "$2"; warns=$((warns + 1)); }
stop () { printf '  \033[31mSTOP\033[0m  %-26s %s\n' "$1" "$2"; stops=$((stops + 1)); }

echo
echo "merge-gate  repo=$REPO_PATH  ledger=$LEDGER"

# ─────────────────────────────────────────────────────────────────────────────
# 0. Resolve the FULL sha. Notice 28's amendment: `?head_sha=` matches nothing
#    for an abbreviation and returns total_count 0 at exit 0, which reads as the
#    real CONFLICTING-PR hazard. Resolving first makes that state unreachable.
# ─────────────────────────────────────────────────────────────────────────────
if ! git -C "$REPO_PATH" rev-parse --git-dir >/dev/null 2>&1; then
  echo "  not a git repository: $REPO_PATH" >&2
  exit 2
fi
git -C "$REPO_PATH" fetch origin master --quiet 2>/dev/null

# `git rev-parse` on an unresolvable ref ECHOES THE INPUT BACK on stdout and
# exits 128, so a non-empty result proves nothing — checked here because the
# first cut of this script did exactly that and handed `deadbeefdeadbeef^{commit}`
# on to five gates, which duly refused it for four different wrong reasons.
# Verify the exit status AND the shape.
SHA="$(git -C "$REPO_PATH" rev-parse --verify --quiet "${SHA_IN}^{commit}" 2>/dev/null)"
rev_rc=$?
if [ "$rev_rc" -ne 0 ] || ! printf '%s' "$SHA" | $GREP -Eq '^[0-9a-f]{40}$'; then
  echo "  cannot resolve '$SHA_IN' to a commit in $REPO_PATH — fetch the branch first" >&2
  exit 2
fi
MASTER="$(git -C "$REPO_PATH" rev-parse origin/master)"
SUBJECT="$(git -C "$REPO_PATH" log -1 --format=%s "$SHA")"
echo "  sha=$SHA"
echo "  master=$MASTER"
echo "  subject=$SUBJECT"
echo

# ─────────────────────────────────────────────────────────────────────────────
# notice 31 — ancestry BEFORE anything else. Already merged means no offer, no
# re-gate, no merge; four lanes once re-ran gate tables for work already live.
# ─────────────────────────────────────────────────────────────────────────────
if git -C "$REPO_PATH" merge-base --is-ancestor "$SHA" "$MASTER"; then
  stop "notice 31 ancestry" "ALREADY ON MASTER — nothing to merge, record it and move on"
  echo
  echo "  VERDICT: STOP (already merged)"
  exit 1
fi
pass "notice 31 ancestry" "not an ancestor of origin/master"

# ─────────────────────────────────────────────────────────────────────────────
# notice 13 — a banked GREEN row IS the token. A cert id in a merge subject is
# not a verdict; the sha must appear on a row that says TOKEN GRANTED.
# ─────────────────────────────────────────────────────────────────────────────
CERT_ID=""
if [ ! -r "$LEDGER" ]; then
  stop "notice 13 token" "ledger unreadable at $LEDGER — cannot prove a token exists"
else
  granted="$($GREP "$SHA" "$LEDGER" | $GREP -c 'TOKEN GRANTED')"
  # `grep -c` exits 1 when the count is 0, so read the NUMBER, never the exit.
  if [ "${granted:-0}" -gt 0 ]; then
    CERT_ID="$($GREP "$SHA" "$LEDGER" | $GREP -o 'CERT-[0-9]\+' | head -1)"
    pass "notice 13 token" "$granted TOKEN GRANTED row(s)${CERT_ID:+ — $CERT_ID}"
  else
    # Not automatically fatal: notice 10 Tier A self-certifies with no cert
    # block at all. It IS fatal for anything bus-graded, and the caller is the
    # only one who knows which this is, so say so plainly rather than guess.
    warn "notice 13 token" "no TOKEN GRANTED row for this sha — legal ONLY if this is Tier A"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# notice 18 — a later row naming this cert after "supersedes" revokes nothing by
# itself, but it means DO NOT MERGE and DO NOT REVERT; the orchestrator rules.
#
# The mechanized form excludes the cert's OWN row, because a repair row cites
# its own id after "supersedes" and the plain grep therefore fires a false STOP
# on precisely the certs that grade first (notice 8b).
# ─────────────────────────────────────────────────────────────────────────────
if [ -n "$CERT_ID" ] && [ -r "$LEDGER" ]; then
  sup="$($GREP -n "supersedes.*$CERT_ID" "$LEDGER" | $GREP -vc "| $CERT_ID --")"
  if [ "${sup:-0}" -eq 0 ]; then
    pass "notice 18 supersedes" "0 later rows name $CERT_ID after 'supersedes'"
  else
    stop "notice 18 supersedes" "$sup row(s) supersede $CERT_ID — write the orchestrator, do not merge, do not revert"
  fi
else
  warn "notice 18 supersedes" "no cert id resolved — skipped (expected for Tier A)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# notice 28 — exact-sha CI. `pull_request` workflows run on the merge ref, so a
# PR GitHub cannot merge gets NO run scheduled at all, while gitleaks' bare
# `push:` trigger and Vercel still print passes and `gh pr checks` EXITS 0.
# ABSENCE OF THE CI ROW IS A STOP, NOT A PASS.
#
# `&per_page=100` is load-bearing twice over: master shas carry 35-47 runs and
# the list pages at 30, so page one can hold no CI row on a sha whose CI passed.
# ─────────────────────────────────────────────────────────────────────────────
RUNS_URL="repos/$REPO_SLUG/actions/runs?head_sha=$SHA&per_page=100"
total="$(gh api "$RUNS_URL" --jq '.total_count' 2>/dev/null)"
if [ -z "$total" ]; then
  stop "notice 28 exact-sha CI" "the runs API did not answer — re-run, do not merge"
elif [ "$total" -eq 0 ]; then
  # total_count 0 means "the API could not match this commit", i.e. the sha is
  # unpushed — a fixable mistake, NOT evidence about CI.
  stop "notice 28 exact-sha CI" "total_count=0 — this sha is not pushed to the remote"
else
  ci="$(gh api "$RUNS_URL" --jq '.workflow_runs[]|select(.name=="CI")|"\(.status)/\(.conclusion)"' 2>/dev/null)"
  if [ -z "$ci" ]; then
    stop "notice 28 exact-sha CI" "total_count=$total but NO CI row — the real hazard; check the PR is mergeable"
  elif [ "$ci" = "completed/success" ]; then
    pass "notice 28 exact-sha CI" "total_count=$total, CI completed/success"
  else
    stop "notice 28 exact-sha CI" "CI is $ci"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# notice 32 — CHECK-RUNS, which are not the same thing as workflow runs: a sha
# once passed 13, 18 AND 28 while its CodeQL CHECK-RUN carried "N new alert(s),
# high severity", because the WORKFLOW had run successfully.
#
# The refuse test is (a) conclusion == failure, or (b) a CodeQL title reporting
# alerts with a security severity. Read titles as SENTENCES: the clean message
# "No new alerts in code changed by this pull request" contains the word alert,
# and `success — N new alerts` at note/warning level is style lint, not a refuse.
#
# `// ""` is mandatory — ten of sixteen titles are null on a real sha and the
# unguarded form aborts at the first one. GATE ON THE EXIT CODE, not on empty
# stdout: exit 0 + no output = pass; exit 1 + no output = the abort, re-run.
# ─────────────────────────────────────────────────────────────────────────────
refusal="$(gh api "repos/$REPO_SLUG/commits/$SHA/check-runs?per_page=100" \
  --jq '.check_runs[]|select((.conclusion=="failure") or (((.output.title) // "")|test("high|critical|security vulnerability";"i")))|"\(.name): \(.conclusion) — \((.output.title) // "null")"' 2>/dev/null)"
refusal_rc=$?
if [ "$refusal_rc" -ne 0 ]; then
  stop "notice 32 check-runs" "the check-runs query failed (exit $refusal_rc) — re-run; an empty result here is NOT a pass"
elif [ -z "$refusal" ]; then
  n_runs="$(gh api "repos/$REPO_SLUG/commits/$SHA/check-runs?per_page=100" --jq '.check_runs|length' 2>/dev/null)"
  pass "notice 32 check-runs" "refusal set empty at exit 0 over ${n_runs:-?} check-runs"
else
  stop "notice 32 check-runs" "refused: $(printf '%s' "$refusal" | tr '\n' ';')"
fi

# ─────────────────────────────────────────────────────────────────────────────
# The PR itself. `mergeable: CONFLICTING` is what causes the notice-28 hazard in
# the first place, and its corollary is harsh: a certed sha that conflicts can
# never be given exact-sha CI, because resolving the conflict changes the sha
# and breaks the notice-13 grep. That token is DEAD, not pending.
# ─────────────────────────────────────────────────────────────────────────────
# `gh pr list --search` is unreliable for finding a PR by sha; the commit's own
# `/pulls` endpoint is the direct question and answers it exactly.
pr_num="$(gh api "repos/$REPO_SLUG/commits/$SHA/pulls" --jq '.[]|select(.state=="open")|.number' 2>/dev/null | head -1)"
if [ -z "$pr_num" ]; then
  warn "PR state" "no open PR found for this sha (fine for a direct merge; check if you expected one)"
else
  # GitHub computes mergeability ASYNCHRONOUSLY and answers `UNKNOWN` for a
  # short while after any push. Reporting that as a conflict is a wrong answer
  # in the same family as the ones this script exists to prevent — it tells a
  # lane to rebase a branch that is perfectly clean. Give it a few seconds.
  mergeable=UNKNOWN
  for _attempt in 1 2 3 4; do
    pr_line="$(gh pr view "$pr_num" --repo "$REPO_SLUG" \
      --json isDraft,mergeable,mergeStateStatus,headRefOid \
      --jq '"\(.isDraft)|\(.mergeable)|\(.mergeStateStatus)|\(.headRefOid)"' 2>/dev/null)"
    IFS='|' read -r is_draft mergeable mstate head_oid <<< "$pr_line"
    [ "$mergeable" = "UNKNOWN" ] || break
    sleep 3
  done
  # `gh --jq` renders a JSON boolean as lowercase `true`/`false`.
  if [ "$is_draft" = "true" ]; then
    stop "PR state" "#$pr_num is a DRAFT"
  elif [ "$mergeable" = "UNKNOWN" ]; then
    stop "PR state" "#$pr_num mergeability still UNKNOWN after 4 reads — GitHub has not computed it yet, re-run (this is NOT a conflict)"
  elif [ "$mergeable" != "MERGEABLE" ]; then
    stop "PR state" "#$pr_num is $mergeable/$mstate — a conflicting PR gets NO pull_request CI run at all"
  elif [ "$head_oid" != "$SHA" ]; then
    stop "PR state" "#$pr_num head is $head_oid, NOT the gated sha — the branch moved under the cert"
  else
    pass "PR state" "#$pr_num OPEN, non-draft, $mergeable/$mstate, head == gated sha"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Composition at the CURRENT master. A cert composes against the master it saw;
# master moves. `merge-tree --write-tree` exits non-zero on a conflict.
# ─────────────────────────────────────────────────────────────────────────────
comp="$(git -C "$REPO_PATH" merge-tree --write-tree "$MASTER" "$SHA" 2>&1)"
comp_rc=$?
if [ "$comp_rc" -eq 0 ]; then
  pass "composition" "conflict-free at $MASTER, tree $(printf '%s' "$comp" | head -1)"
else
  stop "composition" "CONFLICTS against current master — rebase, restage, re-grade (the token dies with the sha)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Does it force a Heroku release? Not a gate — a routing fact. Notice 10: a
# `backend/tests/**` merge never releases ALONE; it rides a server-side batch.
#
# This value is computed HERE, from the diff. Do not cross-check it against the
# CI check-run of the same name: `release-required` in ci.yml is gated on
# `github.ref == 'refs/heads/master' && github.event_name == 'push'`, so on a
# pull_request run it never executes — and a skipped job still publishes a
# check-run, conclusion `skipped`. That `skipped` is therefore on EVERY PR sha
# in the repo and says nothing about whether the sha releases (#5235; notice 32
# already says the same of `deploy: skipped`).
# ─────────────────────────────────────────────────────────────────────────────
rr_script="$REPO_PATH/.github/scripts/heroku-release-required.sh"
if [ -x "$rr_script" ] || [ -r "$rr_script" ]; then
  base="$(git -C "$REPO_PATH" merge-base "$MASTER" "$SHA")"
  rr="$(cd "$REPO_PATH" && bash "$rr_script" "$base" "$SHA" 2>/dev/null | tail -1)"
  echo "  ----  release-required           $rr — computed here from the diff; the CI check-run of this name is push-gated, reads 'skipped' on EVERY PR sha, and is never a verdict"
fi

# ─────────────────────────────────────────────────────────────────────────────
# notice 29 — the push window binds the RELEASE, not the push: the accuracy
# rebuild starts at :15 UTC and a push reaches production 10-20 minutes later.
# Advisory only, and true only at this instant: read the clock again IN the
# push, because a window computed from elapsed sleeps only drifts ahead and can
# never report "outside".
# ─────────────────────────────────────────────────────────────────────────────
now_min=$((10#$(date -u +%M)))
if [ "$now_min" -ge 32 ] && [ "$now_min" -le 50 ]; then
  echo "  ----  push window (notice 29)    IN WINDOW at $(date -u +%H:%M)Z (:32-:50) — re-read the clock in the push"
else
  echo "  ----  push window (notice 29)    OUTSIDE at $(date -u +%H:%M)Z — next window :32-:50 (matters only if it releases)"
fi

echo
if [ "$stops" -eq 0 ]; then
  echo "  VERDICT: GO — $warns warning(s). True at $(date -u +%H:%M:%S)Z and not one second longer."
  exit 0
fi
echo "  VERDICT: STOP — $stops gate(s) refused, $warns warning(s)."
exit 1
