#!/usr/bin/env bash
#
# is-it-live.sh — is the code you merged the code production is SERVING?
#
#   usage:  tools/is-it-live.sh --control TOKEN [--control TOKEN]...
#                               [--ship TOKEN]... [--absent TOKEN]...
#                               [--url URL] [--wait SECONDS] [--quiet]
#           tools/is-it-live.sh --selftest
#
#   exit 0 = LIVE      the served bundle carries your change — LOOK now
#   exit 1 = NOT LIVE  merged, not yet served — wait, do not photograph
#   exit 2 = UNKNOWN   the evidence cannot answer — never read this as "no"
#
# ── WHY THIS IS A FILE AND NOT A PARAGRAPH ───────────────────────────────────
#
# `8d88dfd5` (#5072) merged at 06:56:37Z. The bundle production served did not
# contain it until 07:35:04Z — 38 minutes. The post-deploy LOOK owed on that
# ship ran at 07:00-07:19Z and faithfully photographed PRE-FIX CODE ON A
# POST-MERGE CLOCK: the page latched after one failed poll and never came back,
# which is precisely the thing the ship had fixed (#5150).
#
# The three merges immediately before it deployed in ~2-4 minutes. That is what
# makes the trap sharp — the fleet's working assumption that a post-merge
# screenshot shows your own code is USUALLY true, so it is never checked, and
# the one time it is false the evidence is wrong in whichever direction hurts:
# a false p1 filed against a fix that works, or a green LOOK of the PREVIOUS
# deploy closing an issue whose fix is actually broken.
#
# Nothing in the merge path can catch this. Notices 13/18/28/31/32 and
# `tools/merge-gate.sh` gate the MERGE and say nothing about what is served.
# `/api/health`'s `commit` is the backend only — silent about Vercel. The
# GitHub Deployments API does know, but the record only appears when the build
# COMPLETES, so "no record" is indistinguishable from "queued" at exactly the
# moment you are asking. (INDEX-deploy-reality: merged != live != running !=
# exercised.) The only basis disjoint from all of them is the JS the browser
# actually downloads.
#
# ── THE CONTROL IS THE WHOLE IDEA ────────────────────────────────────────────
#
# Grepping the served bundle for a token your ship introduces answers "yes"
# honestly and "no" dishonestly: a miss is equally consistent with "not
# deployed", "I fetched the wrong chunk", "code-splitting moved it" and "the
# minifier mangled that name". Three of those four are not "no".
#
# So a `--control` is MANDATORY: a token that exists in the same neighbourhood
# both BEFORE and AFTER the ship. If no chunk carries the control, this script
# is looking at the wrong thing and says UNKNOWN. An absence is only evidence
# once you can prove you were looking in the right place. Property names survive
# minification, which is what makes any of this viable — pick identifiers
# (`dedupingInterval`, `shouldRetryOnError`), never local variables.
#
# ── THE EVIDENCE IS ASYMMETRIC, AND SO IS THE CODE ───────────────────────────
#
# Finding a ship token is self-sufficient: the code is there, whatever else is
# true. NOT finding one is a claim about every chunk, and it is only as good as
# the weakest read in the sweep. Hence:
#
#   * a ship token found ANYWHERE wins immediately (short-circuit, no control
#     needed — the original .lat325 probe only looked inside control-bearing
#     chunks and would have called a re-split bundle "not live");
#   * "found nowhere" requires the control AND a clean sweep, so a single failed
#     chunk fetch downgrades NOT LIVE to UNKNOWN rather than answering from a
#     hole in the evidence;
#   * a PARTIAL hit — some ship tokens present, others not — is UNKNOWN, not no.
#     It almost always means one token was a poor choice, and the one thing it
#     must never do is print green.
#
# `--absent` is the mirror, for a ship that REMOVES code (a notice-33 copy
# sweep, a dead-branch deletion): finding the token is positive evidence of the
# OLD code and settles it as NOT LIVE.
#
# ── IT RUNS UNDER bash, DELIBERATELY ─────────────────────────────────────────
#
# `#!/usr/bin/env bash`, and every pattern match below is `/usr/bin/grep -F`. In
# a lane's interactive shell `grep` is a function wrapping ugrep 7.8.4 (#5037);
# a `#!` script does not source the snapshot, and the explicit paths keep a line
# copied OUT of this file safe too. `-F` because the tokens are identifiers
# supplied on the command line, not patterns — `$` and `.` are ordinary
# characters in minified JS and must not be read as regex.
#
# ── WHAT IT CANNOT DO ────────────────────────────────────────────────────────
#
# It answers for ONE page's chunk graph at ONE instant. A token that only ever
# lands in a lazily-imported chunk the landing page does not reference will read
# UNKNOWN forever — pass `--url` for a page that pulls it. And LIVE means the
# bytes are being served, not that the surface is correct: it tells you the LOOK
# is now worth taking, never what the LOOK will show.

set -uo pipefail

GREP=/usr/bin/grep
SELF="${BASH_SOURCE[0]:-}"

CONTROLS=()
SHIPS=()
ABSENTS=()
URL="${IS_IT_LIVE_URL:-https://www.bainluck.com/}"
WAIT=0
QUIET=no
SELFTEST=no

usage () {
  $GREP -E '^#( |$)' "${SELF:-/dev/null}" 2>/dev/null | sed -n '2,12p' | sed 's/^# \{0,1\}//'
  [ -n "${SELF:-}" ] && [ -r "${SELF:-}" ] || cat <<'EOF'
usage: tools/is-it-live.sh --control TOKEN [--ship TOKEN]... [--absent TOKEN]...
                           [--url URL] [--wait SECONDS] [--quiet]
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --control) CONTROLS+=("${2:-}"); shift 2 ;;
    --ship)    SHIPS+=("${2:-}");    shift 2 ;;
    --absent)  ABSENTS+=("${2:-}");  shift 2 ;;
    --url)     URL="${2:-}";         shift 2 ;;
    --wait)    WAIT="${2:-0}";       shift 2 ;;
    --quiet)   QUIET=yes;            shift ;;
    --selftest) SELFTEST=yes;        shift ;;
    -h|--help) usage; exit 2 ;;
    *) echo "is-it-live: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

say () { [ "$QUIET" = yes ] || echo "$@"; }

# ─────────────────────────────────────────────────────────────────────────────
# classify — the whole judgement, over a directory of already-fetched bodies.
#
# Split out from fetching for one reason: it is the part that can be WRONG in a
# way that looks right, so --selftest has to be able to drive it with fixtures
# and no network. Sets CONTROL_CHUNK, SHIP_FOUND, SHIP_MISSING, ABSENT_PRESENT.
# ─────────────────────────────────────────────────────────────────────────────
classify () {
  local dir="$1" f tok ok
  CONTROL_CHUNK=""
  SHIP_FOUND=(); SHIP_MISSING=(); ABSENT_PRESENT=()

  for f in "$dir"/*; do
    [ -f "$f" ] || continue
    ok=yes
    for tok in "${CONTROLS[@]}"; do
      $GREP -F -q -- "$tok" "$f" || { ok=no; break; }
    done
    if [ "$ok" = yes ]; then CONTROL_CHUNK="$(label_for "$(basename "$f")")"; break; fi
  done

  for tok in ${SHIPS[@]+"${SHIPS[@]}"}; do
    if $GREP -R -F -q -l -- "$tok" "$dir" 2>/dev/null; then
      SHIP_FOUND+=("$tok")
    else
      SHIP_MISSING+=("$tok")
    fi
  done

  for tok in ${ABSENTS[@]+"${ABSENTS[@]}"}; do
    if $GREP -R -F -q -l -- "$tok" "$dir" 2>/dev/null; then
      ABSENT_PRESENT+=("$tok")
    fi
  done
}

# ─────────────────────────────────────────────────────────────────────────────
# verdict — turn the classification into an exit code. Order matters, and the
# order IS the asymmetry argued for in the header: positive evidence first,
# then everything that could only ever be an absence.
# ─────────────────────────────────────────────────────────────────────────────
verdict () {
  local n_ship=${#SHIPS[@]} n_found=${#SHIP_FOUND[@]} n_missing=${#SHIP_MISSING[@]}
  local n_absent_present=${#ABSENT_PRESENT[@]}

  # 1. The old code is demonstrably still there. Nothing else can outrank a
  #    positive sighting of what the ship removed.
  if [ "$n_absent_present" -gt 0 ]; then
    VERDICT_LINE="NOT LIVE — the served bundle still carries: ${ABSENT_PRESENT[*]}"
    return 1
  fi

  # 2. Every ship token sighted. Positive evidence; the control is not needed to
  #    believe a thing you can see.
  if [ "$n_ship" -gt 0 ] && [ "$n_missing" -eq 0 ]; then
    VERDICT_LINE="LIVE — the served bundle carries: ${SHIP_FOUND[*]}"
    return 0
  fi

  # 3. Some but not all. Almost always a badly chosen token rather than a
  #    half-deployed bundle — and the one answer it must never give is green.
  if [ "$n_found" -gt 0 ] && [ "$n_missing" -gt 0 ]; then
    VERDICT_LINE="UNKNOWN — your tokens disagree: $n_found of $n_ship present (missing: ${SHIP_MISSING[*]}). Pick tokens the minifier keeps."
    return 2
  fi

  # 4. From here down every answer is an absence, so it is worth exactly as much
  #    as the sweep behind it. No control = wrong neighbourhood = no claim.
  if [ -z "$CONTROL_CHUNK" ]; then
    VERDICT_LINE="UNKNOWN — no chunk carried the control (${CONTROLS[*]}). Wrong page or wrong token; this is NOT a 'no'."
    return 2
  fi

  # 5. A hole in the sweep is a hole in the claim.
  if [ "${FETCH_FAILURES:-0}" -gt 0 ]; then
    VERDICT_LINE="UNKNOWN — control found in $CONTROL_CHUNK, but $FETCH_FAILURES chunk(s) could not be read; an unread chunk could hold the token."
    return 2
  fi

  # 6. --absent only, and none of them survive: the removal is served.
  if [ "$n_ship" -eq 0 ] && [ "${#ABSENTS[@]}" -gt 0 ]; then
    VERDICT_LINE="LIVE — none of the removed tokens survive, control found in $CONTROL_CHUNK"
    return 0
  fi

  VERDICT_LINE="NOT LIVE — control found in $CONTROL_CHUNK, but no chunk carries: ${SHIP_MISSING[*]}"
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# --selftest — the guard for the guard. Offline, read-only, no network.
#
# In this file rather than in `backend/tests/` on purpose: a test under
# `backend/tests/**` forces a Heroku release (notice 10), so guarding a local
# shell tool would make every edit to it wait for a server-side release batch.
# `tools/merge-gate.sh --selftest` sets the precedent.
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SELFTEST" = yes ]; then
  fails=0
  fixdir="$(mktemp -d)"
  trap 'rm -rf "$fixdir"' EXIT
  label_for () { echo "$1"; }

  # Each case: write a fixture bundle, set the token arrays, assert the code.
  #
  # The point of asserting the CODE and not just a string is that callers branch
  # on it: `--wait` loops on 1 and stops on 2, and a LOOK rule that treated
  # UNKNOWN as "not yet" would hang forever on a mistyped control.
  case_run () {
    local want="$1" name="$2"; shift 2
    classify "$fixdir"
    verdict; local got=$?
    if [ "$got" = "$want" ]; then
      echo "  ok    $name (exit $got)"
    else
      echo "  FAIL  $name — wanted exit $want, got $got: $VERDICT_LINE"
      fails=$((fails + 1))
    fi
  }
  reset_fixture () { rm -f "$fixdir"/*; CONTROLS=(); SHIPS=(); ABSENTS=(); FETCH_FAILURES=0; }

  echo "is-it-live --selftest"

  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError)
  echo 'var a={dedupingInterval:5,recordError:f}' > "$fixdir/chunk-1"
  case_run 0 "control + ship in one chunk is LIVE"

  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError)
  echo 'var a={dedupingInterval:5,shouldRetryOnError:0}' > "$fixdir/chunk-1"
  case_run 1 "control found, ship absent everywhere is NOT LIVE"

  # The reason the control exists. Without it this case is indistinguishable
  # from the one above, and answering "no" to it is how a LOOK gets taken of the
  # previous deploy.
  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError)
  echo 'var a={somethingElseEntirely:1}' > "$fixdir/chunk-1"
  case_run 2 "no control anywhere is UNKNOWN, never NOT LIVE"

  # Code-splitting moved the ship token out of the control's chunk. The probe
  # this generalises would have called that NOT LIVE.
  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError)
  echo 'var a={dedupingInterval:5}' > "$fixdir/chunk-1"
  echo 'var b={recordError:f}'      > "$fixdir/chunk-2"
  case_run 0 "ship token in a DIFFERENT chunk than the control is still LIVE"

  # Positive evidence does not need the control.
  reset_fixture
  CONTROLS=(neverAppearsAnywhere); SHIPS=(recordError)
  echo 'var b={recordError:f}' > "$fixdir/chunk-2"
  case_run 0 "a sighted ship token outranks a missing control"

  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError useSWRConfig)
  echo 'var a={dedupingInterval:5,recordError:f}' > "$fixdir/chunk-1"
  case_run 2 "a PARTIAL ship hit is UNKNOWN, never LIVE and never NOT LIVE"

  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError); FETCH_FAILURES=1
  echo 'var a={dedupingInterval:5}' > "$fixdir/chunk-1"
  case_run 2 "an unreadable chunk downgrades NOT LIVE to UNKNOWN"

  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=(recordError); FETCH_FAILURES=1
  echo 'var a={dedupingInterval:5,recordError:f}' > "$fixdir/chunk-1"
  case_run 0 "an unreadable chunk does NOT downgrade a positive sighting"

  reset_fixture
  CONTROLS=(sourceLabel); ABSENTS=(bookmakers)
  echo 'var a={sourceLabel:"Kalshi"}' > "$fixdir/chunk-1"
  case_run 0 "--absent: removed token gone, control found, is LIVE"

  reset_fixture
  CONTROLS=(sourceLabel); ABSENTS=(bookmakers)
  echo 'var a={sourceLabel:"Kalshi",t:"7 bookmakers"}' > "$fixdir/chunk-1"
  case_run 1 "--absent: removed token still served is NOT LIVE"

  reset_fixture
  CONTROLS=(sourceLabel); ABSENTS=(bookmakers)
  echo 'var a={t:"7 bookmakers"}' > "$fixdir/chunk-1"
  case_run 1 "--absent: a sighting outranks a missing control"

  # Tokens are identifiers, not patterns. `.` and `$` are ordinary characters in
  # minified JS; read as regex, `a.b` matches `axb` and this prints a false LIVE.
  reset_fixture
  CONTROLS=(dedupingInterval); SHIPS=('cfg.recordError')
  echo 'var a={dedupingInterval:5,cfgXrecordError:f}' > "$fixdir/chunk-1"
  case_run 1 "tokens match as FIXED strings, not regex"

  # The reason this file runs under bash. An unqualified pattern-match call in a
  # lane's interactive shell is ugrep, whose `-qv` is the bit-flip of `-q` and
  # fails open (#5037). Comments are stripped first: this file TALKS about the
  # tool at length.
  #
  # Neither the label nor the failure message spells the token being scanned
  # for, and that is not squeamishness — written the obvious way the message
  # MATCHES ITS OWN SCAN and the check reports one permanent failure that no
  # edit can clear. `merge-gate.sh` documents the same trap; this file fell into
  # it anyway on the first run, which is the argument for the check existing.
  if [ -n "$SELF" ] && [ -r "$SELF" ]; then
    bare="$(sed -e 's/#.*//' "$SELF" | $GREP -cE '(^|[;&|(]|[[:space:]])grep[[:space:]]')"
    if [ "${bare:-0}" -eq 0 ]; then
      echo "  ok    every pattern match is /usr/bin/... or \$GREP (unqualified calls found: ${bare:-0})"
    else
      echo "  FAIL  ${bare} unqualified pattern-match call(s) — a lane shell would run ugrep"
      fails=$((fails + 1))
    fi
    if head -1 "$SELF" | $GREP -q bash; then
      echo "  ok    runs under bash, which does not source the ugrep snapshot"
    else
      echo "  FAIL  not a bash shebang"
      fails=$((fails + 1))
    fi
  fi

  echo
  if [ "$fails" -eq 0 ]; then echo "  SELFTEST: ok"; exit 0; fi
  echo "  SELFTEST: $fails failure(s)"; exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Live path.
# ─────────────────────────────────────────────────────────────────────────────
if [ "${#CONTROLS[@]}" -eq 0 ]; then
  echo "is-it-live: --control is mandatory." >&2
  echo "  Without a token that exists BOTH before and after your ship, a miss is" >&2
  echo "  equally consistent with 'not deployed' and 'wrong chunk' — and the" >&2
  echo "  whole point of this script is to tell those two apart (#5150)." >&2
  exit 2
fi
if [ "${#SHIPS[@]}" -eq 0 ] && [ "${#ABSENTS[@]}" -eq 0 ]; then
  echo "is-it-live: give at least one --ship (a token your change ADDS) or" >&2
  echo "            --absent (a token your change REMOVES)." >&2
  exit 2
fi

case "$URL" in
  http://*|https://*) : ;;
  *) echo "is-it-live: --url must be absolute (got '$URL')" >&2; exit 2 ;;
esac
BASE="$(printf '%s' "$URL" | sed -E 's#^(https?://[^/]+).*#\1#')"

WORK="$(mktemp -d)"
# Inside WORK so the trap reaps it, but NOT inside WORK/bodies — classify globs
# that directory and would otherwise scan the map as if it were a served chunk.
MAP="$WORK/.map"
: > "$MAP"
trap 'rm -rf "$WORK"' EXIT

label_for () { $GREP -F -- "$1	" "$MAP" 2>/dev/null | head -1 | cut -f2- || echo "$1"; }

fetch_all () {
  local dir="$1" n=0 c body
  rm -rf "$dir"; mkdir -p "$dir"; : > "$MAP"
  FETCH_FAILURES=0

  # A cachebust on the HTML only. `_next/static` assets are content-hashed, so
  # busting them would just miss the CDN for no gain — and the stale thing we
  # are hunting is the HTML's chunk LIST, not the chunks.
  local sep="?"; case "$URL" in *\?*) sep="&" ;; esac
  local html; html="$(curl -sS --max-time 25 "${URL}${sep}cachebust=$RANDOM" 2>/dev/null)"
  if [ -z "$html" ]; then
    VERDICT_LINE="UNKNOWN — no HTML from $URL (the page, not the bundle, is the failure)"
    return 2
  fi

  # The page's own HTML counts as a body: a server-rendered copy change (a
  # notice-33 word sweep) lands in the markup, never in a chunk.
  printf '%s' "$html" > "$dir/000-page-html"
  printf '%s\t%s\n' "000-page-html" "(page html)" >> "$MAP"

  for c in $(printf '%s' "$html" | $GREP -oE '/_next/static/[^"]+\.js' | sort -u); do
    n=$((n + 1))
    local f; f="$(printf '%03d-chunk' "$n")"
    body="$(curl -sS --max-time 25 "$BASE$c" 2>/dev/null)"
    if [ -z "$body" ]; then
      FETCH_FAILURES=$((FETCH_FAILURES + 1))
      continue
    fi
    printf '%s' "$body" > "$dir/$f"
    printf '%s\t%s\n' "$f" "$c" >> "$MAP"
  done
  CHUNKS_READ=$n
  return 0
}

attempt () {
  fetch_all "$WORK/bodies" || return 2
  classify "$WORK/bodies"
  verdict
}

started=$(date +%s)
while :; do
  attempt; rc=$?
  now=$(date -u +%H:%M:%SZ)
  if [ "$rc" -eq 0 ] || [ "$WAIT" -le 0 ]; then break; fi
  elapsed=$(( $(date +%s) - started ))
  if [ "$elapsed" -ge "$WAIT" ]; then
    say "  gave up waiting after ${elapsed}s"
    break
  fi
  # Only exit 1 is worth waiting out. UNKNOWN means the QUESTION is wrong, and
  # no amount of waiting fixes a mistyped control — polling on it would hang for
  # the full --wait and then print the same sentence.
  if [ "$rc" -ne 1 ]; then break; fi
  say "  $now  not yet (${elapsed}s elapsed, waiting up to ${WAIT}s)"
  sleep 20
done

say "is-it-live  url=$URL"
say "  chunks read=${CHUNKS_READ:-0}  unreadable=${FETCH_FAILURES:-0}  control=${CONTROL_CHUNK:-<not found>}"
say ""
say "  VERDICT: $VERDICT_LINE"
say "  (true at $(date -u +%H:%M:%S)Z; LIVE means the bytes are served, not that the surface is right)"
[ "$QUIET" = yes ] && echo "$VERDICT_LINE"
exit $rc
