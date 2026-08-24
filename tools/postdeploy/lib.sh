#!/usr/bin/env bash
# Shared plumbing for the UX post-deploy proof one-shots (UX-P119 item 3).
#
# ## Why this file exists at all
#
# The proofs it serves are each three curls and a comparison. What is NOT cheap,
# and what has cost this lane whole cycles, is everything around them:
#
#   1. **A proof run against the wrong build is worse than no proof.** Every
#      "OWED: production evidence" line in the last five READY files exists
#      because the drain had not deployed. A green proof taken before the deploy
#      does not read as premature — it reads as PASSED. `require_deployed` makes
#      that state unreachable: it refuses unless the commit `/api/health` reports
#      actually CONTAINS the branch being proven, measured with
#      `merge-base --is-ancestor` on a local ref, never read off a handoff file.
#
#   2. **An empty 200 is a response shape, not an absence** (gotcha #53). Each
#      proof therefore reports its denominators, and a zero-population read is
#      `UNKNOWN`, never `PASS`.
#
#   3. **A throttled response parses as null** (60 req/min). `api_get` retries
#      429 with backoff and returns non-zero rather than handing back an empty
#      body a caller would read as data.
#
#   4. **`cmd | tail` reports tail's exit code** (gotcha #54). Nothing here pipes
#      a check; exit codes are read from `$?` on their own line.
#
# Verdicts are printed as `PASS`/`FAIL`/`UNKNOWN`/`SKIP` with the numbers that
# produced them, because a bare verdict is not evidence.

set -u

: "${TOOLS_QUIET:=0}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO_ROOT

# `~/.claude/.env` is where the credentials live, and it uses `export FOO=...`,
# not `: "${FOO:=...}"`. Sourcing it therefore OVERWRITES whatever the caller
# set — so `BAINLUCK_API=http://127.0.0.1:8791 ./some-check.sh` silently ran
# against PRODUCTION instead. That is not a cosmetic override bug: it is how a
# mutation test of `checks/proof-2060-labeling-card.sh` came back green while
# reading real, unmutated data, which would have certified a check that cannot
# fail. Caller-set values are captured first and restored after, so the env file
# supplies what is missing and never replaces what was chosen. (Same shape as
# #2120: a tool that honours an override only when nothing overrides it.)
__caller_api="${BAINLUCK_API:-}"
__caller_web="${BAINLUCK_WEB:-}"
__caller_admin_token="${ADMIN_TOKEN:-}"
# shellcheck disable=SC1090
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
[ -n "$__caller_api" ] && BAINLUCK_API="$__caller_api"
[ -n "$__caller_web" ] && BAINLUCK_WEB="$__caller_web"
[ -n "$__caller_admin_token" ] && ADMIN_TOKEN="$__caller_admin_token"
unset __caller_api __caller_web __caller_admin_token
: "${BAINLUCK_API:=https://api.bainluck.com}"
: "${BAINLUCK_WEB:=https://bainluck.com}"
export BAINLUCK_API BAINLUCK_WEB

# Exit codes, so a caller can tell "the check failed" from "the check could not
# run" — gotcha #54's amendment: 1 is a result, anything else is a story about
# the harness.
readonly RC_PASS=0
readonly RC_FAIL=1
readonly RC_UNKNOWN=3
readonly RC_NOT_DEPLOYED=4
readonly RC_TRANSPORT=5
export RC_PASS RC_FAIL RC_UNKNOWN RC_NOT_DEPLOYED RC_TRANSPORT

say()  { [ "$TOOLS_QUIET" = "1" ] || printf '%s\n' "$*"; }
hdr()  { say ""; say "── $* ──────────────────────────────────────────"; }
verdict() { printf '%s: %s\n' "$1" "$2"; }

# --- transport ---------------------------------------------------------------

# api_get <path> <outfile> [max_attempts]
# Retries on 429 and on 5xx (the calibration route 503s for 1–4 minutes after
# every release and then self-heals — that is a known window, not a failure).
api_get() {
  local path="$1" out="$2" attempts="${3:-6}" i=1 code
  while [ "$i" -le "$attempts" ]; do
    code=$(curl -s --max-time 120 -o "$out" -w '%{http_code}' "$BAINLUCK_API$path")
    case "$code" in
      200) return 0 ;;
      429|500|502|503|504)
        say "   [retry $i/$attempts] HTTP $code on $path"
        sleep $(( i * 10 ))
        ;;
      *)
        say "   HTTP $code on $path"
        return 1
        ;;
    esac
    i=$(( i + 1 ))
  done
  say "   gave up after $attempts attempts on $path (last HTTP $code)"
  return 1
}

# api_get_admin <path> <outfile> [max_attempts]
# The authenticated twin of `api_get`, with the same retry discipline. It exists
# so an admin read is never hand-rolled as a bare `curl`: the admin routes are
# behind the same 60/min limiter as everything else, and a throttled response
# parses as `None` — which a caller reads as a phantom regression rather than as
# "I was not answered". The token goes in the `Authorization: Bearer` header and
# ONLY there; the `?secret=` query transport was removed (Queue #252 item 3), so
# a URL carrying it gets a 403 and would also have leaked the token into every
# shell history and log line that echoed the path.
api_get_admin() {
  local path="$1" out="$2" attempts="${3:-6}" i=1 code
  if [ -z "${ADMIN_TOKEN:-}" ]; then
    say "   ADMIN_TOKEN unset — source ~/.claude/.env"
    return 1
  fi
  while [ "$i" -le "$attempts" ]; do
    code=$(curl -s --max-time 120 -o "$out" -w '%{http_code}' \
      -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API$path")
    case "$code" in
      200) return 0 ;;
      429|500|502|503|504)
        say "   [retry $i/$attempts] HTTP $code on $path"
        sleep $(( i * 10 ))
        ;;
      *)
        say "   HTTP $code on $path"
        return 1
        ;;
    esac
    i=$(( i + 1 ))
  done
  say "   gave up after $attempts attempts on $path (last HTTP $code)"
  return 1
}

# api_post_admin <path> <outfile>
api_post_admin() {
  local path="$1" out="$2" code
  if [ -z "${ADMIN_TOKEN:-}" ]; then
    say "   ADMIN_TOKEN unset — source ~/.claude/.env"
    return 1
  fi
  code=$(curl -s --max-time 300 -o "$out" -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" "$BAINLUCK_API$path")
  [ "$code" = "200" ] && return 0
  say "   HTTP $code on POST $path"
  return 1
}

# --- the deploy gate ---------------------------------------------------------

deployed_sha() {
  local tmp; tmp=$(mktemp)
  api_get "/api/health" "$tmp" 3 || { rm -f "$tmp"; return 1; }
  python3 -c "import json,sys; print(json.load(open('$tmp')).get('commit',''))"
  rm -f "$tmp"
}

# require_deployed <ref>  — refuse unless production is running a commit that
# CONTAINS <ref>. Measured with merge-base against a local ref; a handoff file's
# claim about what merged is never the input.
require_deployed() {
  local ref="$1" live
  live=$(deployed_sha) || { verdict "GATE" "UNKNOWN — /api/health unreachable"; return $RC_TRANSPORT; }
  say "   /api/health commit: $live"
  if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$live^{commit}" >/dev/null; then
    say "   fetching, deployed commit not in this worktree…"
    git -C "$REPO_ROOT" fetch -q origin 2>/dev/null
  fi
  if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$live^{commit}" >/dev/null; then
    verdict "GATE" "UNKNOWN — deployed commit $live is not an object in this repo"
    return $RC_UNKNOWN
  fi
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$ref" "$live" 2>/dev/null; then
    say "   $ref IS an ancestor of the deployed commit — proof is due"
    return 0
  fi
  verdict "GATE" "NOT DEPLOYED — $ref is not an ancestor of $live; this proof is not yet due"
  return $RC_NOT_DEPLOYED
}
