#!/usr/bin/env bash
# Never-backwards guarded deploy to Heroku (extracted from ci.yml for Ruling 394).
# Shared identically by `deploy` (release on merge) and `deploy-after-full` (fail-closed).

set -e

if [ -z "$HEROKU_API_KEY" ]; then
  echo "HEROKU_API_KEY not set — skipping deploy"
  exit 0
fi
# Receipt reads are trusted master-push code and run while this job
# owns heroku-deploy. A failed read refuses release; no catch-and-pass.
check_source_veto () {
  if [ -f tools/release/discover.py ]; then
    python3 - <<'SOURCE_VETO'
import os, sys
sys.path.insert(0, 'tools/release')
import discover
if os.environ['GITHUB_SHA'] in discover.failed_sources(discover.receipt_rows('heroku')):
    raise SystemExit('REFUSING to release a source rejected by the full-suite watchdog')
SOURCE_VETO
  fi
}
git remote add heroku https://heroku:$HEROKU_API_KEY@git.heroku.com/bainluck.git 2>/dev/null || true

# `|| true` keeps an unreadable live ref from reddening the job (and
# holds under `-o pipefail` too); it falls through to the push, where
# git adjudicates it for us.
LIVE="$(git ls-remote heroku refs/heads/master 2>/dev/null | cut -f1 || true)"
git fetch --quiet heroku refs/heads/master 2>/dev/null || true
if [ -z "$LIVE" ]; then
  echo "Could not read Heroku's live commit — deferring to the push below."
elif [ "$LIVE" = "$GITHUB_SHA" ]; then
  echo "Skipping deploy: $GITHUB_SHA is already the live commit."
  exit 0
elif git merge-base --is-ancestor "$GITHUB_SHA" "$LIVE"; then
  echo "Skipping deploy: this run's commit ($GITHUB_SHA) is an ancestor of"
  echo "the live commit ($LIVE) — something newer is already deployed."
  echo "An older re-run can no longer clobber a newer deploy."
  exit 0
else
  echo "Deploying $GITHUB_SHA over live commit ${LIVE:-<unknown>}."
fi

_push_log="$(mktemp)"
verify_push () {
  local _rc="$1" _allow_non_ff="${2:-0}" _v=0
  cat "$_push_log"
  if python3 .github/scripts/check_heroku_push.py \
    --log "$_push_log" --push-exit "$_rc" \
    --require-release-done --verify-api \
    --app bainluck --expected-sha "$GITHUB_SHA"; then
    _v=0
  else
    _v=$?
  fi
  if [ "$_allow_non_ff" = 1 ] && [ "$_v" = 2 ]; then return 2; fi
  rm -f "$_push_log"
  if [ "$_v" = 0 ]; then return 0; fi
  exit 1
}

# The check above is a read followed by a write, so it cannot close the
# race by itself. Push WITHOUT --force and let git refuse a
# non-fast-forward: if a newer deploy won the race in between, the
# server rejects us instead of quietly rewinding production. Push the
# SHA explicitly rather than the local `master` branch, so what gets
# released is the commit this run actually gated.
check_source_veto
exec 3>&1 4>&2 >"$_push_log" 2>&1
if git push heroku "$GITHUB_SHA:refs/heads/master"; then
  _push_rc=0
else
  _push_rc=$?
fi
exec 1>&3 2>&4 3>&- 4>&-
if verify_push "$_push_rc" 1; then _pv=0; else _pv=$?; fi
if [ "$_pv" = 0 ]; then
  echo "Deployed $GITHUB_SHA."
  [ -z "${GITHUB_OUTPUT:-}" ] || { echo "deployed=true"; echo "prev_live_sha=${LIVE:-}"; } >> "$GITHUB_OUTPUT"
  exit 0
fi

# Rejected. Do NOT force by reflex. A rejection can perfectly well mean
# a NEWER deploy won the race, and forcing then rewinds production —
# the exact incident this guard exists to prevent. So establish what is
# live and whether we can REASON about it before doing anything, and
# treat "cannot prove" as a refusal rather than as permission.
LIVE_NOW="$(git ls-remote heroku refs/heads/master 2>/dev/null | cut -f1 || true)"
git fetch --quiet heroku refs/heads/master 2>/dev/null || true
# Ancestry is only meaningful for a commit whose object we actually
# hold. `merge-base --is-ancestor` on a commit we never fetched exits
# non-zero, which reads identically to a truthful "no" — so ask
# directly instead of inferring it from a failure.
HAVE_LIVE=0
if [ -n "$LIVE_NOW" ] && git cat-file -e "${LIVE_NOW}^{commit}" 2>/dev/null; then
  HAVE_LIVE=1
fi

if [ "$HAVE_LIVE" = 1 ] && git merge-base --is-ancestor "$GITHUB_SHA" "$LIVE_NOW"; then
  rm -f "$_push_log"
  echo "Superseded mid-push: $LIVE_NOW is newer than $GITHUB_SHA. Leaving it."
  exit 0
fi

if [ "$HAVE_LIVE" = 1 ] && git merge-base --is-ancestor "$LIVE_NOW" "$GITHUB_SHA"; then
  # The live commit is provably BEHIND us, so a fast-forward does exist
  # and the rejection was transient. Retry as a fast-forward — never as
  # a force. A second rejection reddens the job under `-e`, which is
  # the honest outcome: somebody should look.
  echo "Live commit $LIVE_NOW is behind $GITHUB_SHA and a fast-forward exists; retrying."
  check_source_veto
  exec 3>&1 4>&2 >"$_push_log" 2>&1
  if git push heroku "$GITHUB_SHA:refs/heads/master"; then
    _push_rc=0
  else
    _push_rc=$?
  fi
  exec 1>&3 2>&4 3>&- 4>&-
  verify_push "$_push_rc" 0
  echo "Deployed $GITHUB_SHA."
  [ -z "${GITHUB_OUTPUT:-}" ] || { echo "deployed=true"; echo "prev_live_sha=${LIVE_NOW:-}"; } >> "$GITHUB_OUTPUT"
  exit 0
fi

# What is left is either genuinely diverged history, or a live commit
# whose ancestry we cannot establish. A force push in EITHER state can
# rewind a newer production, so both fail closed.
#
# One exception, and only one: when this commit IS GitHub's current
# master tip there is no newer commit for a force to lose, so a history
# rewrite can still self-heal without a human. Note the direction of
# the test — the tip is used here to NARROW when forcing is allowed,
# never to decide whether to deploy. That inversion is #3171.
ORIGIN_TIP="$(git ls-remote origin refs/heads/master 2>/dev/null | cut -f1 || true)"
if [ -n "$ORIGIN_TIP" ] && [ "$ORIGIN_TIP" = "$GITHUB_SHA" ]; then
  echo "Push rejected and the live commit (${LIVE_NOW:-<unreadable>}) has no provable"
  echo "ancestry with $GITHUB_SHA — but this commit IS origin/master's tip, so there is"
  echo "no newer commit to rewind past. History diverged; forcing."
  check_source_veto
  exec 3>&1 4>&2 >"$_push_log" 2>&1
  if git push heroku "$GITHUB_SHA:refs/heads/master" --force; then
    _push_rc=0
  else
    _push_rc=$?
  fi
  exec 1>&3 2>&4 3>&- 4>&-
  verify_push "$_push_rc" 0
  [ -z "${GITHUB_OUTPUT:-}" ] || { echo "deployed=true"; echo "prev_live_sha=${LIVE_NOW:-}"; } >> "$GITHUB_OUTPUT"
  exit 0
fi

rm -f "$_push_log"
echo "REFUSING to deploy. The push was rejected, the live commit"
echo "(${LIVE_NOW:-<unreadable>}) has no provable ancestry with $GITHUB_SHA, and this"
echo "commit is not origin/master's tip (${ORIGIN_TIP:-<unreadable>}). Forcing from here"
echo "could rewind a newer production, so this fails closed. Deploy by hand once the"
echo "divergence is understood."
exit 1
