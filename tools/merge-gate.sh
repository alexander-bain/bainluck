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

# ─────────────────────────────────────────────────────────────────────────────
# supersedes_scan — classify one cert id against the ledger for notice 18.
#
# Sets SUP_VERDICT to exactly one of: clean | declared | review, and leaves the
# matching rows in SUP_ROWS with the counts in SUP_N / SUP_DECL.
#
# It SETS rather than echoes on purpose. Called as `$(supersedes_scan ...)` the
# body runs in a subshell and every one of those four variables is discarded —
# the caller then dies on `SUP_N: unbound variable` under `set -u`, and no unit
# test that only reads the classification can see it. Call it as a statement.
#
# WHY THREE ANSWERS AND NOT TWO. Notice 18's rule is positional: "no LATER
# ledger row names that CERT-N AFTER the word 'supersedes'". No grep decides
# that, because the ledger writes both halves of the question in English:
#
#   a bus-status row  "CERT-2620 supersedes CERT-2617 ... CERT-2619 token stands"
#     names 2619 BEFORE the word and AFFIRMS it — the broad grep STOPs on it
#     anyway. That false STOP held 97e9923b for hours on 2026-09-11 while 1,558
#     wrong period verdicts stayed live (integrator/304, lane1b/158).
#
# The obvious repair is to match only `supersedes: CERT-N`, the header form
# notice 12 mandates. MEASURED on the 2,810-line ledger, that form silently
# passes four REAL declarations written as prose — `supersedes the earlier
# CERT-700 ancestor row`, `the CERT-874 BLOCK`, `the CERT-793 GREEN`, `the
# CERT-599 sha`. It cures the false STOP by opening a hole.
#
# Widening it to "the id anywhere in the same clause" catches those four and
# then fires on a dozen sentences ABOUT the check — `supersedes scan for
# CERT-893`, `supersedes rows naming CERT-2217`, `supersedes | grep CERT-2246`.
# Both directions are a branch flag built from a substring, and the branch that
# DENIES the condition cites the same words as the branch that asserts it.
#
# So the gate stops pretending it can read. Broad grep is the SCREEN, the
# canonical form is the TEST, and the case they disagree on is handed to a
# person WITH THE ROW PRINTED — which turns an escalation to the orchestrator
# into one five-second read. It never resolves that case silently in either
# direction.
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# resolve_cert_id — the id to PRINT and to hand to notice 18, for one sha.
#
# Sets CERT_ID (empty if no granting row). Statement, not `$( )`; see below.
#
# It reads the id off the GRANTED row, not off the first row naming the sha. A
# ship that was blocked once and repaired has two or more rows on one sha — the
# BLOCK first, then the GREEN that repairs it — so `head -1` over all of them
# returns the BLOCK. Measured on `5d18064c` (#5088): all-rows resolves CERT-2613
# `BLOCK -- TOKEN WITHHELD`, the granted row resolves CERT-2622 `GREEN -- TOKEN
# GRANTED` (#5252, found by live/153).
#
# The gate never *decided* anything on that id — `granted` is counted separately
# and correctly — but the id is what goes into the merge subject and the ledger
# note, and it fires on exactly the ships whose provenance most needs to be
# legible: a later reader auditing "what did we merge on?" finds a withdrawn
# token. It is also the id notice 18 scans, so resolving it from the granted row
# is what makes that scan provably about the cert that granted the token.
#
# `head -1` still picks the granting cert rather than a `repairs CERT-M`
# reference inside the same row, because `| CERT-N --` opens the row.
# ─────────────────────────────────────────────────────────────────────────────
CERT_ID=""
resolve_cert_id () {
  local sha="$1" ledger="$2"
  CERT_ID="$($GREP "$sha" "$ledger" | $GREP 'TOKEN GRANTED' | $GREP -o 'CERT-[0-9]\+' | head -1)"
}

# ─────────────────────────────────────────────────────────────────────────────
# ancestry_of — "is this sha on master?", answered so that a SHALLOW clone
# cannot turn the answer into a silent yes-you-may.
#
# Sets ANC_STATE to merged | not-merged | unknown, and ANC_HOW to local|remote.
#
# ── THE BUG THIS EXISTS FOR (measured 2026-09-11, latency/343) ───────────────
#
# `~/bainluck/.git` is a SHALLOW clone — `rev-parse --is-shallow-repository` is
# true, `.git/shallow` lists twelve boundary commits dated 2026-09-10, and only
# 348 commits are reachable from origin/master. Every lane worktree shares that
# object store, so every lane has the same truncated view.
#
# `git merge-base --is-ancestor X origin/master` cannot see past the boundary.
# For anything merged before it, the honest graph answer is "I don't know" and
# git's answer is exit 1 — indistinguishable from "not merged". Notice 31 reads
# exit 1 as GO. Measured on the shipped gate: `a1fe4212`, whose own subject is
# "Merge live/041 … into master" and which notice 12 records as merged on 9/2,
# printed `PASS notice 31 ancestry — not an ancestor of origin/master`. The gate
# whose entire job is "do not offer or re-gate what has already landed" said go.
#
# That case then STOPped at the composition gate, but only by luck: a 9/2 merge
# commit no longer applies cleanly. A pre-boundary sha that still composes gets
# a clean GO.
#
# ── THE ASYMMETRY THAT MAKES THE FIX CHEAP ───────────────────────────────────
#
# A local YES is always true: `--is-ancestor` only says yes about commits it can
# actually walk to. It is only a local NO that a shallow clone can fabricate. So
# the remote is consulted on exactly one branch — local-no, clone-shallow — and
# a full clone never reaches the network at all. Behaviour there is unchanged.
#
# The remote oracle is `compare/<sha>...master`, whose `status` is `ahead` when
# master is ahead of the sha (i.e. the sha is an ancestor) or `identical` when
# they are the same commit; `behind` and `diverged` both mean not merged.
# Measured: a1fe4212 -> ahead; f74de8a7 and 4564d947 (real unmerged shas) ->
# diverged.
#
# If the remote cannot be reached the state is `unknown`, never `not-merged`.
# A gate that could not be evaluated is a STOP everywhere else in this file and
# it is a STOP here: the whole point is that "I could not tell" must stop being
# spelled the same way as "no".
# ─────────────────────────────────────────────────────────────────────────────
IS_SHALLOW=""
ANC_STATE=""; ANC_HOW=""
ancestry_of () {
  local full="$1"
  if git -C "$REPO_PATH" merge-base --is-ancestor "$full" "$MASTER" 2>/dev/null; then
    ANC_STATE=merged; ANC_HOW=local; return
  fi
  if [ "$IS_SHALLOW" != "true" ]; then
    ANC_STATE=not-merged; ANC_HOW=local; return
  fi
  local st
  st="$(gh api "repos/$REPO_SLUG/compare/${full}...master" --jq '.status' 2>/dev/null)"
  case "$st" in
    ahead|identical) ANC_STATE=merged;     ANC_HOW=remote ;;
    behind|diverged) ANC_STATE=not-merged; ANC_HOW=remote ;;
    *)               ANC_STATE=unknown;    ANC_HOW=remote ;;
  esac
}

SUP_VERDICT=""; SUP_ROWS=""; SUP_N=0; SUP_DECL=0
supersedes_scan () {
  local cert="$1" ledger="$2"
  # SCREEN: every row mentioning the word and this id, minus the cert's OWN
  # grade row — a repair row cites its own id after "supersedes" (notice 8b).
  # `-w` on the screen too: without it `supersedes.*CERT-261` matches a row that
  # only ever says CERT-2619, and the shorter id inherits the longer one's
  # review. `-w` anchors the END of the match, so CERT-261 followed by `9` is
  # not a match while CERT-2619 followed by a space is.
  #
  # THE WORD IS NOT ALWAYS "supersedes" (#5264). Matched literally and
  # case-sensitively, this screen and the test below missed the three commonest
  # ways the ledger actually writes a supersession, so the rows never reached
  # the screen at all and the verdict came back `clean` — a PASS on a superseded
  # cert, which is the one thing notice 18 exists to prevent. Measured over the
  # real ledger: 18 real supersessions read `clean`. All verbatim:
  #
  #   superseding CERT-770.                    23 certs, the commonest real form
  #   SUPERSEDES CERT-858                      caps; case alone loses these
  #   supersede CERT-1871,  Supersedes: CERT-2309
  #   supersedes CERT-913/914                  slash list — the TAIL id
  #   CERT-2042 GREEN is superseded by CERT-2043 BLOCK    inverse, 7 occurrences
  #
  # So: case-insensitive, verb `supersed(es|e|ing)`, and the inverse phrasing as
  # a second alternative with `[^0-9]` guarding the id (`-w` anchors the whole
  # match, and in that branch the id is not at the end).
  #
  # Widening the SCREEN cannot cause a false STOP — a screened row with no
  # declaration is `review`, which is a WARN that prints the row. Only the TEST
  # below STOPs. Measured: 103 certs leave `clean` (29 to `declared`, 74 to
  # `review`) and NOTHING moves toward `clean`.
  # The `/${num}` alternative is load-bearing and easy to leave out: in
  # `supersedes CERT-9130/9140` the string `CERT-9140` never appears, so without
  # it the tail id does not reach the screen at all and comes back `clean` — the
  # fail-open this whole block is about, one level down. A selftest case caught
  # exactly that.
  #
  # `-w` had to go with it. It anchors on the character before the MATCH, and in
  # `CERT-9130/9140` the character before `/9140` is a digit, so `-w` threw the
  # slash tail away — the id would have gone on reading `clean`. The boundary is
  # written out instead: `([^0-9]|$)` after the id does the same job as `-w` did
  # (CERT-261 followed by `9` is not CERT-261) and does it in both shapes.
  SUP_ROWS="$($GREP -niE "supersed(es|e|ing).*$cert([^0-9]|\$)|supersed(es|e|ing).*/${cert#CERT-}([^0-9]|\$)|$cert[^0-9].*supersede(d)? by" "$ledger" | $GREP -v "| $cert --")"
  # `grep -c .` over an empty string is 0; `printf '%s'` adds no trailing line.
  SUP_N="$(printf '%s' "$SUP_ROWS" | $GREP -c . )"
  # TEST: the declaration form notice 12 mandates. `-w` so CERT-261 never
  # matches CERT-2619 and CERT-2619 never matches CERT-26190.
  #
  # Same three widenings, and the id may be a slash-list TAIL — `supersedes
  # CERT-913/914` declares a supersede of 914 and never spells `CERT-914`, so
  # the count matches `/914` too, with `-w` keeping it off CERT-9140.
  #
  # This one CAN false-STOP, so it stays tight: the verb, an optional colon,
  # spaces, then the id IMMEDIATELY. Any intervening word makes it prose and it
  # falls through to `review` — which is what keeps the sentences ABOUT the
  # check out of it (`supersedes scan for CERT-893`, `supersedes rows naming
  # CERT-2217`, `notice 18 **tight** supersedes — 0 for CERT-2300/2301/…`).
  # Audited: all 34 newly-`declared` ids are the canonical form, zero prose.
  # A declaration may carry more than one id: `SUPERSEDES CERT-913 AND CERT-914`
  # and `supersedes CERT-9130/9140` each declare two. Both continuations stay
  # inside the tight form — the list may only grow by `/N` or `and CERT-N`, so
  # no ordinary word can creep in and turn prose into a STOP.
  SUP_DECL="$($GREP -oiE 'supersed(es|e|ing):? *CERT-[0-9]+((/[0-9]+)|(,? +and +CERT-[0-9]+))*' "$ledger" | $GREP -ciE "$cert([^0-9]|\$)|/${cert#CERT-}([^0-9]|\$)")"
  if [ "${SUP_N:-0}" -eq 0 ]; then
    SUP_VERDICT=clean
  elif [ "${SUP_DECL:-0}" -gt 0 ]; then
    SUP_VERDICT=declared
  else
    SUP_VERDICT=review
  fi
}

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
    "/usr/bin/grep -q -- '-v \"| \$cert --\"' '$self'"

  # The bug the unit tests below could NOT see, because they only ever read the
  # classification: called in `$( )` the function's four output variables are
  # set in a subshell and discarded, and the caller dies on an unbound SUP_N.
  # Caught by an end-to-end run, so it is guarded at the source.
  check "supersedes_scan is called as a statement, never in a subshell" \
    "! sed -e 's/#.*//' '$self' | /usr/bin/grep -q '\$(supersedes_scan'"

  check "resolve_cert_id is called as a statement, never in a subshell" \
    "! sed -e 's/#.*//' '$self' | /usr/bin/grep -q '\$(resolve_cert_id'"

  # ── notice 18, behavioural. These call the SHIPPED function against fixture
  # ledgers rather than re-deriving its greps, because a test that reimplements
  # the thing it guards measures the reimplementation. Every fixture below is a
  # verbatim shape lifted off the real ledger.
  fx="$(mktemp -d)"
  trap 'rm -rf "$fx"' EXIT

  # The row that caused all of this: 2619 is named BEFORE the word and is
  # AFFIRMED; the id named after it is 2617. Must not STOP on 2619.
  cat > "$fx/busrow.md" <<'FIXEOF'
| CERT-BUS-STATUS-2026-09-11-1407-01a090b5 | DRAINED | CERT-2620 supersedes CERT-2617, whose earlier token is not merge authority; required repair remains. CERT-2619 token stands; follow-up remains. |
FIXEOF
  check "notice 18: an affirming bus row is REVIEW, not a STOP (the 97e9923b false STOP)" \
    "supersedes_scan CERT-2619 '$fx/busrow.md'; [ \"\$SUP_VERDICT\" = review ]"
  check "notice 18: the genuine supersede in that same row IS declared" \
    "supersedes_scan CERT-2617 '$fx/busrow.md'; [ \"\$SUP_VERDICT\" = declared ]"

  # A prose declaration that the canonical form alone would silently PASS.
  # Four of these are on the real ledger; this is why the middle case is a
  # review and not a clean.
  cat > "$fx/prose.md" <<'FIXEOF'
| CERT-0701 -- SUBJECT | GREEN | supersedes the earlier CERT-700 ancestor row at `65c2e4ed`. |
FIXEOF
  check "notice 18: a prose declaration is REVIEW, never clean (no silent pass)" \
    "supersedes_scan CERT-700 '$fx/prose.md'; [ \"\$SUP_VERDICT\" = review ]"

  cat > "$fx/clean.md" <<'FIXEOF'
| CERT-2619 -- SUBJECT | GREEN/TOKEN GRANTED | supersedes scan returned 0. |
| CERT-2700 -- OTHER | GREEN | nothing to see here. |
FIXEOF
  check "notice 18: the cert's own row never supersedes itself (notice 8b)" \
    "supersedes_scan CERT-2619 '$fx/clean.md'; [ \"\$SUP_VERDICT\" = clean ]"
  check "notice 18: an id absent from the ledger is clean" \
    "supersedes_scan CERT-9999 '$fx/clean.md'; [ \"\$SUP_VERDICT\" = clean ]"

  # ── notice 18, THE FAIL-OPEN (#5264). The word is not always "supersedes".
  # Matched literally and case-sensitively, each row below returned `clean` — a
  # PASS on a superseded cert. 18 real ones read `clean` on the live ledger.
  # Every fixture row is verbatim shape, ids as they really are.
  cat > "$fx/failopen.md" <<'FIXEOF'
| CERT-0799 -- SUBJECT | GREEN | Token granted for `9a6a014c`, superseding CERT-770. |
| CERT-0861 -- SUBJECT | GREEN -- TOKEN GRANTED; SUPERSEDES CERT-858 | a connected live tennis page. |
| CERT-1872 -- SUBJECT | GREEN | this row is here to supersede CERT-1871, and it says so. |
| CERT-2310 -- SUBJECT | GREEN | Supersedes: CERT-2309. |
| CERT-0915 -- SUBJECT | BLOCK | SUPERSEDES CERT-913 AND CERT-914 on the same sha. |
| CERT-0916 -- SUBJECT | BLOCK | supersedes CERT-9130/9140 together. |
| CERT-2043 -- SUBJECT | BLOCK | CERT-2042 GREEN is superseded by CERT-2043 BLOCK, so notice 18 refuses. |
FIXEOF
  check "n18 fail-open: 'superseding CERT-N' is declared, not clean (CERT-770)" \
    "supersedes_scan CERT-770 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: CAPS 'SUPERSEDES CERT-N' is declared (CERT-858)" \
    "supersedes_scan CERT-858 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: bare 'supersede CERT-N' is declared (CERT-1871)" \
    "supersedes_scan CERT-1871 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: 'Supersedes: CERT-N' capitalised is declared (CERT-2309)" \
    "supersedes_scan CERT-2309 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: an AND list declares BOTH ids (CERT-913, CERT-914)" \
    "supersedes_scan CERT-913 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ] && supersedes_scan CERT-914 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: a slash list declares its TAIL id (CERT-9140)" \
    "supersedes_scan CERT-9140 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" = declared ]"
  check "n18 fail-open: the inverse 'CERT-N ... superseded by' is not clean (CERT-2042)" \
    "supersedes_scan CERT-2042 '$fx/failopen.md'; [ \"\$SUP_VERDICT\" != clean ]"

  # The widening must not re-import the false STOPs it was built beside. A
  # sentence ABOUT the check names the id after the verb with a word in between;
  # that is prose and must fall through to review, never declared. All three
  # shapes are verbatim from the real ledger.
  cat > "$fx/mention.md" <<'FIXEOF'
| CERT-2320 -- SUBJECT | MERGED | notice 18 **tight** supersedes -- 0 for CERT-2300/2301/2306; notice 28 completed/success. |
| CERT-2321 -- SUBJECT | MERGED | notice 18 = 0 word-anchored `supersedes` rows for CERT-2154. |
| CERT-2322 -- SUBJECT | GREEN | the same expression finds the live supersedes targets CERT-894/901/903. |
FIXEOF
  for _m in 2300 2301 2306 2154 894 901 903; do
    check "n18 fail-open: prose ABOUT the check is review, never a STOP (CERT-$_m)" \
      "supersedes_scan CERT-$_m '$fx/mention.md'; [ \"\$SUP_VERDICT\" != declared ]"
  done

  # `-w` still has to keep a short id off a longer one, in BOTH the widened
  # screen and the widened slash-list count.
  cat > "$fx/bounds2.md" <<'FIXEOF'
| CERT-9500 -- SUBJECT | GREEN | superseding CERT-2619 and nothing else. |
FIXEOF
  check "n18 fail-open: the widened screen keeps CERT-261 off CERT-2619" \
    "supersedes_scan CERT-261 '$fx/bounds2.md'; [ \"\$SUP_VERDICT\" = clean ]"
  check "n18 fail-open: the widened screen still declares the full id (CERT-2619)" \
    "supersedes_scan CERT-2619 '$fx/bounds2.md'; [ \"\$SUP_VERDICT\" = declared ]"

  # ── notice 13, behavioural (#5252). A repaired ship has a BLOCK row and a
  # GREEN row on ONE sha; the id we print and scan must come off the GREEN.
  # Verbatim shape of #5088's two rows on 5d18064c.
  cat > "$fx/repaired.md" <<'FIXEOF'
| CERT-2613 -- 5088-MIDGAME-WINDOW-RESULTS | 2026-09-11 11:39Z | live/148 | BLOCK -- TOKEN WITHHELD | sha 5d18064c91caac7cae36caaaf9efe54fba3f885e |
| CERT-2622 -- 5088-CLOSED-WINDOW-SETTLED-REPAIR-LANDED-RE-PRESENT | 2026-09-11 14:30Z | live/152 | GREEN -- TOKEN GRANTED (repairs CERT-2613) | sha 5d18064c91caac7cae36caaaf9efe54fba3f885e |
FIXEOF
  check "notice 13: a repaired ship resolves the GRANTING cert, not the BLOCK it repaired" \
    "resolve_cert_id 5d18064c91caac7cae36caaaf9efe54fba3f885e '$fx/repaired.md'; [ \"\$CERT_ID\" = CERT-2622 ]"
  check "notice 13: 'repairs CERT-2613' inside the granted row does not win over the row's own id" \
    "resolve_cert_id 5d18064c91caac7cae36caaaf9efe54fba3f885e '$fx/repaired.md'; [ \"\$CERT_ID\" != CERT-2613 ]"
  check "notice 13: a sha with no granted row resolves to empty, not to a withheld id" \
    "resolve_cert_id deadbeef '$fx/repaired.md'; [ -z \"\$CERT_ID\" ]"

  # -w, not \b: BSD grep is what /usr/bin/grep is here, and a prefix match
  # would make CERT-261 inherit CERT-2619's verdict.
  cat > "$fx/bounds.md" <<'FIXEOF'
| CERT-9000 -- SUBJECT | GREEN | supersedes: CERT-2619 |
FIXEOF
  check "notice 18: CERT-261 does not match CERT-2619's declaration (-w boundary)" \
    "supersedes_scan CERT-261 '$fx/bounds.md'; [ \"\$SUP_VERDICT\" = clean ]"
  check "notice 18: CERT-2619 itself is declared in that fixture (control)" \
    "supersedes_scan CERT-2619 '$fx/bounds.md'; [ \"\$SUP_VERDICT\" = declared ]"

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

  # ── ancestry_of, behavioural. These call the SHIPPED function with a stubbed
  # `gh` on PATH, so they measure the real mapping table rather than a copy of
  # it. The sha is deliberately not a local ancestor, which is what pushes the
  # function onto its remote branch.
  #
  # The third case is the one that matters. Before this function existed, "the
  # clone cannot see that far" and "not merged" were the same exit code, and
  # notice 31 read both as GO — that is how the shipped gate came to print
  # `PASS ancestry` for a1fe4212, a commit whose own subject says it was merged
  # into master on 9/2. If a broken/absent `gh` ever collapses back into
  # `not-merged`, the fail-open is silently reopened and no other test sees it.
  mkdir -p "$fx/bin"
  _sv_shallow="$IS_SHALLOW"; _sv_master="${MASTER:-}"; _sv_repo="$REPO_PATH"
  IS_SHALLOW=true
  MASTER="$(git -C "$REPO_PATH" rev-parse HEAD 2>/dev/null || echo HEAD)"
  _fake_sha=0123456789012345678901234567890123456789

  printf '#!/bin/sh\necho ahead\n'    > "$fx/bin/gh"; chmod +x "$fx/bin/gh"
  PATH="$fx/bin:$PATH" ancestry_of "$_fake_sha"
  check "ancestry_of: remote 'ahead' means the sha IS on master" \
    "[ \"$ANC_STATE\" = merged ] && [ \"$ANC_HOW\" = remote ]"

  printf '#!/bin/sh\necho identical\n' > "$fx/bin/gh"
  PATH="$fx/bin:$PATH" ancestry_of "$_fake_sha"
  check "ancestry_of: remote 'identical' also means on master" "[ \"$ANC_STATE\" = merged ]"

  printf '#!/bin/sh\necho diverged\n' > "$fx/bin/gh"
  PATH="$fx/bin:$PATH" ancestry_of "$_fake_sha"
  check "ancestry_of: remote 'diverged' means genuinely not merged" "[ \"$ANC_STATE\" = not-merged ]"

  printf '#!/bin/sh\nexit 1\n' > "$fx/bin/gh"
  PATH="$fx/bin:$PATH" ancestry_of "$_fake_sha"
  check "ancestry_of: an UNREACHABLE remote is 'unknown', never 'not-merged' (the fail-open)" \
    "[ \"$ANC_STATE\" = unknown ]"

  IS_SHALLOW=false
  PATH="$fx/bin:$PATH" ancestry_of "$_fake_sha"
  check "ancestry_of: a FULL clone never consults the remote (behaviour unchanged there)" \
    "[ \"$ANC_STATE\" = not-merged ] && [ \"$ANC_HOW\" = local ]"

  IS_SHALLOW="$_sv_shallow"; MASTER="$_sv_master"; REPO_PATH="$_sv_repo"

  check "the notice 31 gate routes through ancestry_of, not a bare --is-ancestor" \
    "sed -e 's/#.*//' '$self' | /usr/bin/grep -q 'ancestry_of \"\$SHA\"'"

  # ── --orphans, behavioural. THE EMPTINESS GUARD IS THE POINT: a sweep whose
  # parser stops matching reports an empty orphan list, and empty reads as a
  # clean board. It must exit 2 (rig failure), never 0.
  cat > "$fx/noledger.md" <<'FIXEOF'
| CERT-9001 -- SUBJECT | 2026-09-11 10:00Z | lane | BLOCK -- TOKEN WITHHELD | nothing granted here |
FIXEOF
  out="$(MERGE_GATE_LEDGER="$fx/noledger.md" bash "$self" --orphans 2>&1)"; rc=$?
  check "--orphans: a ledger with zero granted rows is a RIG FAILURE (exit 2), not a clean board" \
    "[ $rc -eq 2 ]"
  check "--orphans: and it says so in words, not just in an exit code" \
    "printf '%s' \"\$out\" | /usr/bin/grep -q 'RIG FAILURE'"

  out="$(MERGE_GATE_LEDGER=/nonexistent/ledger.md bash "$self" --orphans 2>&1)"; rc=$?
  check "--orphans: an unreadable ledger exits 2, never 0" "[ $rc -eq 2 ]"

  # It must print its denominator every run. A coverage number whose population
  # nobody stated is the failure that read 674 priced legs out of 2,652.
  out="$(bash "$self" --orphans 2>&1)"
  check "--orphans: prints its population (granted rows -> unique shas)" \
    "printf '%s' \"\$out\" | /usr/bin/grep -q 'population:.*granted row'"

  check "--orphans: --all cannot widen past a shallow clone's floor" \
    "sed -e 's/#.*//' '$self' | /usr/bin/grep -q 'window clamped to'"

  echo
  if [ "$fails" -eq 0 ]; then
    echo "  selftest: PASS"
    exit 0
  fi
  echo "  selftest: $fails FAILED"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# --orphans — notice 31(b), mechanized: which GRANTED tokens never landed?
#
#   usage:  tools/merge-gate.sh --orphans [--all] [<repo-path>]
#
# Every other gate in this file answers "may I merge THIS sha?". That question
# presupposes somebody is already merging, and the failure it cannot see is the
# sha nobody is holding at all: a cert graded GREEN, a token granted, and no
# offer ever written. Notice 31(b) exists because that is not hypothetical —
# int310 found FOUR unoffered GREEN shas in one day, two of them only by
# re-running a sweep after pushing, and the tray read empty the whole time. The
# tray records what a lane remembered to say; the ledger records what graded.
#
# So this mode reads the LEDGER and git ANCESTRY, and never the inbox. An offer
# file is exactly the artifact that goes missing, so a sweep that consulted it
# would be blind in the one direction it exists to see (live/155 wrote a real
# offer into the wrong directory and polled a lock for hours; the offer was
# never the evidence — the ledger row was).
#
# ── THE PREDICATE IS THE GATE'S OWN ──────────────────────────────────────────
#
# "Merged" is `git merge-base --is-ancestor`, the identical call the notice-31
# gate makes on a single sha, not a lookup in a commit list that happens to
# agree with it today. Two instruments answering one question is how they come
# to disagree; there is only one instrument here.
#
# ── WHAT IT REFUSES TO DO SILENTLY ───────────────────────────────────────────
#
# It prints its denominator on every run. A sweep whose population predicate is
# wrong reports a clean board and reports it confidently — the same failure that
# read 674 priced legs where there were 2,652, because the walker invented the
# denominator instead of taking it from the data. So: the granted-row count, the
# unique-sha count, and the count outside the window are all printed, and a
# population of ZERO exits 2 as a rig failure rather than 0 as "nothing to do".
#
# Every sha it declines to report is declined OUT LOUD and counted — parked,
# superseded, already merged, or unresolvable. A suppression you cannot see is
# indistinguishable from a bug in the suppressor.
#
# ── THE WINDOW, AND WHY IT DEFAULTS SHORT ────────────────────────────────────
#
# The ledger goes back to 2026-09-01 and most of its early rows name shas whose
# branches are long gone. Defaulting to the whole file buries this week's real
# orphan under a hundred dead ones, so the default is 7 days and `--all` opens
# it. The rows outside the window are COUNTED in the summary either way — a
# truncated bound that does not say it truncated is how a sweep goes vacuous.
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SHA_IN" = "--orphans" ]; then
  ORPH_ALL=0
  orph_repo=""
  shift
  for a in "$@"; do
    case "$a" in
      --all) ORPH_ALL=1 ;;
      --*)   echo "  unknown flag for --orphans: $a" >&2; exit 2 ;;
      *)     orph_repo="$a" ;;
    esac
  done
  # `$2` is the repo path for the single-sha form, so REPO_PATH was set at the
  # top of this file from an argument that here may be `--all`. Re-derive it.
  REPO_PATH="${orph_repo:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

  if ! git -C "$REPO_PATH" rev-parse --git-dir >/dev/null 2>&1; then
    echo "  not a git repository: $REPO_PATH" >&2
    exit 2
  fi
  if [ ! -r "$LEDGER" ]; then
    echo "  ledger unreadable at $LEDGER — a sweep that cannot read the ledger" >&2
    echo "  has not found zero orphans, it has found nothing." >&2
    exit 2
  fi
  git -C "$REPO_PATH" fetch origin master --quiet 2>/dev/null
  MASTER="$(git -C "$REPO_PATH" rev-parse origin/master)"
  IS_SHALLOW="$(git -C "$REPO_PATH" rev-parse --is-shallow-repository 2>/dev/null)"

  # ── The shallow floor. `ancestry_of` repairs a single wrong answer by asking
  # the remote, but a sweep cannot ask 700 times, so this mode instead refuses to
  # GUESS about rows it cannot judge locally and says how many there were.
  #
  # In a shallow clone every pre-boundary merge reads as "not an ancestor", which
  # in this mode means "orphan". Unclamped, the first run of this sweep would have
  # reported some five hundred long-merged shas as unoffered GREEN tokens — a
  # confident, entirely false emergency, and precisely the rig artifact this file
  # keeps warning about. The floor is the newest boundary commit's date: at or
  # after it the local graph is complete, before it the local answer is noise.
  SHALLOW_FLOOR=""
  if [ "$IS_SHALLOW" = "true" ]; then
    gitdir="$(git -C "$REPO_PATH" rev-parse --git-common-dir 2>/dev/null)"
    case "$gitdir" in /*) ;; *) gitdir="$REPO_PATH/$gitdir" ;; esac
    if [ -r "$gitdir/shallow" ]; then
      SHALLOW_FLOOR="$(while read -r b; do
          git -C "$REPO_PATH" log -1 --format=%cd --date=format:%Y-%m-%d "$b" 2>/dev/null
        done < "$gitdir/shallow" | sort | tail -1)"
    fi
  fi

  # The window. BSD `date` first (the lanes are macOS), GNU second. If NEITHER
  # parses, the window is abandoned and every row is scanned — widening, never
  # narrowing, and it says so, because a sweep that silently shrank its own
  # window would under-report exactly when its clock is broken.
  ORPH_DAYS="${MERGE_GATE_ORPHAN_DAYS:-7}"
  cutoff=""
  if [ "$ORPH_ALL" -eq 0 ]; then
    cutoff="$(date -u -v-"${ORPH_DAYS}"d +%Y-%m-%d 2>/dev/null)" ||
      cutoff="$(date -u -d "${ORPH_DAYS} days ago" +%Y-%m-%d 2>/dev/null)" || cutoff=""
    if [ -z "$cutoff" ]; then
      echo "  note: neither date(1) dialect parsed a ${ORPH_DAYS}-day cutoff — scanning ALL rows"
      ORPH_ALL=1
    fi
  fi

  echo "merge-gate --orphans — granted tokens that never landed (notice 31b)"
  echo "  ledger=$LEDGER"
  echo "  repo=$REPO_PATH"
  echo "  master=$MASTER"
  if [ "$ORPH_ALL" -eq 1 ]; then
    echo "  window=ALL rows"
  else
    echo "  window=rows dated >= $cutoff (${ORPH_DAYS}d; --all for the whole ledger)"
  fi
  # The floor overrides both, including --all: --all asks for more rows, it does
  # not make the clone able to answer for them.
  if [ -n "$SHALLOW_FLOOR" ]; then
    echo "  CLONE IS SHALLOW — local ancestry is only valid at/after $SHALLOW_FLOOR (.git/shallow boundary)."
    echo "  Rows older than that are counted as UNJUDGEABLE, never as orphans."
    echo "  To sweep the whole ledger: git -C $REPO_PATH fetch --unshallow"
    if [ "$ORPH_ALL" -eq 1 ] || [ -z "$cutoff" ] || [ "$cutoff" \< "$SHALLOW_FLOOR" ]; then
      cutoff="$SHALLOW_FLOOR"; ORPH_ALL=0
      echo "  window clamped to >= $SHALLOW_FLOOR"
    fi
  fi
  echo

  # ── Parse. One awk pass, no brace-interval regexes: macOS awk is not GNU awk
  # and `{40}` is not portable there, so a hex run is recognised by charset and
  # LENGTH, which is exactly what `{40}` was going to mean anyway.
  #
  # Columns are pipe-delimited (`| CERT-N -- SUBJ | date | lane | verdict | …`),
  # so cert/date/lane come from their own column and cannot be captured out of
  # the prose. The sha is scanned across the WHOLE row: it is written into the
  # notes column about as often as anywhere else.
  #
  # A 40-hex token wins over a short one wherever both appear. 781 of the 975
  # granted rows carry a full sha and 193 more carry only an 8-hex — dropping
  # the short form would silently exclude a fifth of the ledger.
  orph_rows="$(awk -F'|' '
    function ishex(s,   i,c) {
      if (length(s) < 7) return 0
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (index("0123456789abcdef", c) == 0) return 0
      }
      return 1
    }
    index($0, "TOKEN GRANTED") == 0 { next }
    {
      cert = ""; dt = ""; lane = ""; sha40 = ""; shashort = ""
      if (match($2, /CERT-[0-9]+/)) cert = substr($2, RSTART, RLENGTH)
      if (match($3, /2026-[0-9][0-9]-[0-9][0-9]/)) dt = substr($3, RSTART, RLENGTH)
      lane = $4
      gsub(/^[ \t]+|[ \t]+$/, "", lane)
      # Fall back to a whole-row date scan for the 32 rows whose third column is
      # not the canonical stamp.
      if (dt == "" && match($0, /2026-[0-9][0-9]-[0-9][0-9]/)) dt = substr($0, RSTART, RLENGTH)
      n = split($0, tok, /[^0-9A-Za-z-]+/)
      for (i = 1; i <= n; i++) {
        t = tok[i]
        if (!ishex(t)) continue
        if (length(t) == 40) { if (sha40 == "") sha40 = t }
        else if (length(t) <= 12) { if (shashort == "") shashort = t }
      }
      s = (sha40 != "" ? sha40 : shashort)
      if (cert == "") cert = "CERT-?"
      if (dt == "") dt = "0000-00-00"
      printf "%s\t%s\t%s\t%s\n", s, dt, cert, lane
    }
  ' "$LEDGER")"

  granted_rows="$(/usr/bin/grep -c 'TOKEN GRANTED' "$LEDGER")"
  rows_parsed="$(printf '%s' "$orph_rows" | /usr/bin/grep -c .)"
  no_sha="$(printf '%s' "$orph_rows" | awk -F'\t' '$1 == "" {n++} END {print n+0}')"

  # THE EMPTINESS GUARD. A reused scanner inherits its first caller's assumptions
  # about shape, and the failure is silent: nothing matches, the report is empty,
  # and empty reads as clean. Zero granted rows or zero parsed rows means the
  # ledger's format moved under this parser — that is a rig failure, not a green
  # board, and it exits 2 so nobody can mistake it for one.
  if [ "${granted_rows:-0}" -eq 0 ] || [ "${rows_parsed:-0}" -eq 0 ]; then
    echo "  RIG FAILURE: $granted_rows granted row(s), $rows_parsed parsed."
    echo "  The ledger's row format has moved under this parser. This is NOT a clean board."
    exit 2
  fi

  # Unique shas, earliest granted row wins (that is the moment it became
  # offerable, and it is the row `resolve_cert_id` would pick).
  uniq_shas="$(printf '%s\n' "$orph_rows" | awk -F'\t' '$1 != "" && !seen[$1]++')"
  n_uniq="$(printf '%s' "$uniq_shas" | /usr/bin/grep -c .)"

  # ── The park list. Read from origin/master, the same ref the script itself is
  # fetched from, because the shared checkout drifts by hours (#5269) and a park
  # that is stale in the working tree would hide a live orphan. `MERGE_GATE_PARKED`
  # overrides for anyone editing it.
  #
  # If it cannot be read the sweep continues with an EMPTY park list, which makes
  # held shas noisy. That is the correct direction to fail: a sweep that suppresses
  # on evidence it could not load is worse than one that shows too much.
  parked_src=""
  parked_txt=""
  if [ -n "${MERGE_GATE_PARKED:-}" ] && [ -r "${MERGE_GATE_PARKED}" ]; then
    parked_txt="$(cat "${MERGE_GATE_PARKED}")"; parked_src="${MERGE_GATE_PARKED}"
  elif parked_txt="$(git -C "$REPO_PATH" show origin/master:tools/merge-gate-parked.txt 2>/dev/null)"; then
    parked_src="origin/master:tools/merge-gate-parked.txt"
  else
    parked_txt=""; parked_src="(none — no park list; held shas will be reported)"
  fi
  n_parked_entries="$(printf '%s\n' "$parked_txt" | /usr/bin/grep -cE '^[0-9a-f]{7,40}[[:space:]]' || true)"
  echo "  parked=$parked_src (${n_parked_entries:-0} entr(y|ies))"
  # A park with no stated reason is how a sha goes quiet forever. Name them.
  bare_park="$(printf '%s\n' "$parked_txt" | awk '/^[0-9a-f]/ && NF < 2 {print "    " $1}')"
  if [ -n "$bare_park" ]; then
    echo "  WARN: park entries with no reason (a park without a reason is a disappearance):"
    printf '%s\n' "$bare_park"
  fi
  echo

  n_merged=0; n_unres=0; n_parked=0; n_super=0; n_window=0; n_out=0; n_orph=0
  orph_out=""; unres_out=""; parked_out=""; super_out=""; review_out=""

  while IFS=$'\t' read -r tok dt cert lane; do
    [ -n "$tok" ] || continue
    if [ "$ORPH_ALL" -eq 0 ] && [ "$dt" \< "$cutoff" ]; then
      n_out=$((n_out + 1)); continue
    fi
    n_window=$((n_window + 1))

    full="$(git -C "$REPO_PATH" rev-parse --verify --quiet "${tok}^{commit}" 2>/dev/null)"
    rc=$?
    if [ "$rc" -ne 0 ] || ! printf '%s' "$full" | $GREP -Eq '^[0-9a-f]{40}$'; then
      # Not judgeable: the object is not in this clone. That is usually a branch
      # deleted after merge, but it can also be a sha never pushed here, so it is
      # reported as its own class and never folded into "merged".
      n_unres=$((n_unres + 1))
      unres_out="$unres_out
    $tok  $dt  $cert  $lane"
      continue
    fi

    # The gate's own predicate, via the same helper the single-sha gate uses —
    # not a second instrument that agrees with it today. Inside the clamped
    # window the local graph is complete, so this answers locally; the remote is
    # reached only for a sha that looks like an orphan in a shallow clone, which
    # is a handful of calls and buys exactness on the only rows we will print.
    ancestry_of "$full"
    if [ "$ANC_STATE" = merged ]; then
      n_merged=$((n_merged + 1)); continue
    fi

    short="$(printf '%s' "$full" | cut -c1-8)"

    if [ "$ANC_STATE" = unknown ]; then
      n_unres=$((n_unres + 1))
      unres_out="$unres_out
    $short  $dt  $cert  $lane — ancestry UNDECIDABLE (shallow clone, remote unreachable)"
      continue
    fi

    # Prefix match, computed rather than pattern-matched: a park entry matches
    # when it IS a prefix of this candidate's full sha. Written as a regex on
    # the short form instead, a 7-character park entry never matches an 8-character
    # short sha — the entry sits in the file looking effective and suppresses
    # nothing, which is the one way a park list can fail silently in the noisy
    # direction and the one way nobody would notice.
    why="$(printf '%s\n' "$parked_txt" | awk -v f="$full" '
      /^[0-9a-f]/ {
        s = $1
        if (substr(f, 1, length(s)) == s) {
          $1 = ""; sub(/^[ \t]+/, "")
          print; exit
        }
      }')"
    if [ -n "$why" ]; then
      n_parked=$((n_parked + 1))
      parked_out="$parked_out
    $short  $dt  $cert  — $why"
      continue
    fi

    # Notice 18: a superseded token is not an orphan to go and offer.
    supersedes_scan "$cert" "$LEDGER"
    if [ "$SUP_VERDICT" = declared ]; then
      n_super=$((n_super + 1))
      super_out="$super_out
    $short  $dt  $cert  $lane — superseded; do NOT offer, the orchestrator rules (notice 17)"
      continue
    fi

    n_orph=$((n_orph + 1))
    flag=""
    [ "$SUP_VERDICT" = review ] && flag="  [notice 18: REVIEW — read the row before offering]"
    orph_out="$orph_out
    $short  $dt  $cert  $lane$flag"
  done <<EOF
$uniq_shas
EOF

  echo "  population: $granted_rows granted row(s) -> $n_uniq unique sha(s); $no_sha row(s) carried no sha"
  if [ -n "$SHALLOW_FLOOR" ]; then
    echo "  in window:  $n_window   outside/unjudgeable-in-a-shallow-clone: $n_out"
  else
    echo "  in window:  $n_window   outside: $n_out"
  fi
  echo "  merged: $n_merged   parked: $n_parked   superseded: $n_super   unresolvable here: $n_unres"
  echo

  if [ -n "$parked_out" ]; then
    echo "  PARKED (counted, deliberately not offered):$parked_out"
    echo
  fi
  if [ -n "$super_out" ]; then
    echo "  SUPERSEDED:$super_out"
    echo
  fi
  if [ -n "$unres_out" ]; then
    echo "  NOT IN THIS CLONE (cannot judge — fetch the branch, or it was deleted after merge):$unres_out"
    echo
  fi

  if [ "$n_orph" -eq 0 ]; then
    echo "  VERDICT: no orphans in window — every granted token is on master, parked or superseded."
    echo "  True at $(date -u +%H:%M:%S)Z and not one second longer."
    exit 0
  fi
  echo "  ORPHANS — granted, not on master, nobody parked them:$orph_out"
  echo
  echo "  Each line is a candidate, not a verdict: run the full gate on it"
  echo "  (tools/merge-gate.sh <sha>) before offering — ancestry is only the first gate."
  echo "  VERDICT: $n_orph orphan(s) at $(date -u +%H:%M:%S)Z."
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
IS_SHALLOW="$(git -C "$REPO_PATH" rev-parse --is-shallow-repository 2>/dev/null)"
ancestry_of "$SHA"
case "$ANC_STATE" in
  merged)
    stop "notice 31 ancestry" "ALREADY ON MASTER — nothing to merge, record it and move on (by $ANC_HOW)"
    echo
    echo "  VERDICT: STOP (already merged)"
    exit 1
    ;;
  unknown)
    stop "notice 31 ancestry" "UNDECIDABLE — clone is shallow and the remote could not be reached; a local 'no' here is not an answer"
    echo
    echo "  VERDICT: STOP (ancestry undecidable — deepen the clone with 'git fetch --unshallow' or fix gh auth)"
    exit 1
    ;;
esac
if [ "$IS_SHALLOW" = "true" ]; then
  pass "notice 31 ancestry" "not on master (confirmed against the remote; local clone is SHALLOW and cannot see past its boundary)"
else
  pass "notice 31 ancestry" "not an ancestor of origin/master"
fi

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
    resolve_cert_id "$SHA" "$LEDGER"
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
#
# Three outcomes, not two — the reasoning is on `supersedes_scan` above.
# ─────────────────────────────────────────────────────────────────────────────
if [ -n "$CERT_ID" ] && [ -r "$LEDGER" ]; then
  # A statement, not a command substitution — see supersedes_scan's note.
  supersedes_scan "$CERT_ID" "$LEDGER"
  case "$SUP_VERDICT" in
    clean)
      pass "notice 18 supersedes" "0 later rows name $CERT_ID after 'supersedes'"
      ;;
    declared)
      stop "notice 18 supersedes" "$SUP_DECL row(s) declare a supersede of $CERT_ID — write the orchestrator, do not merge, do not revert"
      ;;
    review)
      # NOT a pass and NOT a stop. The rows are printed because the whole point
      # is that the answer is legible in them and in nothing else.
      warn "notice 18 supersedes" "READ THESE $SUP_N ROW(S) — no declaration of the form 'supersedes: $CERT_ID' exists, so this is prose UNLESS one of them names $CERT_ID *after* the word:"
      printf '%s\n' "$SUP_ROWS" | head -3 | cut -c1-200 | sed 's/^/          /'
      [ "${SUP_N:-0}" -gt 3 ] && echo "          ... and $((SUP_N - 3)) more — search the ledger for '$CERT_ID'"
      echo "          if one does: STOP, write the orchestrator, do not revert. If all are prose: this sha is clear."
      ;;
  esac
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
