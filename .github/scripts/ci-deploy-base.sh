#!/usr/bin/env bash
# #7610 — what should the two deploy-scope gates diff FROM?
#
# Usage:  ci-deploy-base.sh <FALLBACK_BASE> <HEAD_SHA>
# Prints: a base sha on stdout (plus reasoning on stderr). Never empty unless
#         the fallback it was handed was empty.
#
# WHY THIS EXISTS. `ci-change-scope.sh` and `heroku-release-required.sh` are both
# correct: each classifies the range it is given and fails toward running/
# releasing. Both were handed `github.event.before` — THE PREVIOUS PUSH, which is
# not THE LAST THING THAT REACHED A DYNO. When a push does not release (red gate,
# skipped job, anything), the next push's base moves past that delta and neither
# gate ever reconsiders it. Measured 2026-09-20 21:26Z: production served
# `56c9d27e` while master was `f3d5be5ae`, with 10 backend app files — two certed
# fixes — merged above it and no future push able to carry them. Silent by
# construction: master green, tray empty, `heroku releases` recent.
#
# ── THE INVARIANT THAT MAKES THIS SAFE ─────────────────────────────────────
# The base this prints is ALWAYS an ancestor of (or equal to) the fallback it
# was given. So the range handed to the two gates can only ever GROW, never
# shrink — whatever they would have concluded from `event.before`, they still
# conclude, plus anything stranded below it. That is the whole safety argument,
# and it is asserted rather than described: see
# `backend/tests/test_ci_deploy_base_7610.py`.
#
# It follows that this script cannot cause a missed release or a skipped shard.
# The worst it can do is widen a range — a redundant release or a full shard run
# — which is the side both sibling scripts already say they choose on a tie.
#
# ── IT LIVES IN A FILE FOR THE REASON ITS SIBLINGS DO ──────────────────────
# An inline heredoc in ci.yml is unreachable by every gate we own, which is how a
# deploy-path decision rots unnoticed. Everything here is executable by a test.

set -uo pipefail

FALLBACK="${1:-}"
HEAD_SHA="${2:-}"

# The deployed commit is read from the app's own health endpoint. Overridable so
# the guard test can point it at a local file (`curl` speaks `file://`) instead
# of the network, and so a second app can be asked about later without editing
# this logic.
HEALTH_URL="${CI_DEPLOYED_SHA_URL:-https://api.bainluck.com/api/health}"
CURL_MAX_TIME="${CI_DEPLOYED_SHA_TIMEOUT:-10}"

say () { echo "$*" >&2; }
emit () { echo "$1"; say "BASE: $1 ($2)"; exit 0; }

# Every failure path below emits the FALLBACK, which is exactly today's
# behaviour — this script can only ever improve the base or leave it alone.
[ -n "$FALLBACK" ] || emit "$FALLBACK" "no fallback base given — nothing to improve on"
[ -n "$HEAD_SHA" ] || emit "$FALLBACK" "no head commit given — cannot validate a deployed sha"

case "$FALLBACK" in
  0000000000000000000000000000000000000000)
    # A branch's first push. The siblings both read this as "no usable base" and
    # fail toward full/true; substituting a real sha would NARROW that to a
    # diffable range and could turn a `full` into a `frontend`.
    emit "$FALLBACK" "fallback is the null sha — the gates' own fail-safe must keep it" ;;
esac

BODY="$(curl -fsS --max-time "$CURL_MAX_TIME" "$HEALTH_URL" 2>/dev/null)" \
  || emit "$FALLBACK" "could not read $HEALTH_URL — keeping the fallback base"

# Deliberately not `jq`: this runs before any tooling step, and a missing
# interpreter here would be a deploy-path failure for a string extraction. The
# `7,40` bound is what makes an abbreviated `"commit":"4e3e7674"` usable and a
# truncated or templated value ("unknown", "") unusable.
DEPLOYED="$(printf '%s' "$BODY" \
  | tr ',{}' '\n\n\n' \
  | sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]\{7,40\}\)".*/\1/p' \
  | head -1)"
[ -n "$DEPLOYED" ] || emit "$FALLBACK" "no usable commit field at $HEALTH_URL — keeping the fallback base"

# An abbreviation is only usable if THIS checkout can resolve it unambiguously.
FULL="$(git rev-parse --verify --quiet "${DEPLOYED}^{commit}" 2>/dev/null)" \
  || FULL=""
[ -n "$FULL" ] || emit "$FALLBACK" "deployed sha ${DEPLOYED} is not resolvable here — keeping the fallback base"

# THE INVARIANT, ENFORCED. The deployed sha is used only when it sits at or
# below the fallback. If production were somehow AHEAD of `event.before` — a
# force-push, a rebased master, a deploy from another ref — using it would
# SHRINK the range and could hide a backend path. That case keeps the fallback.
if ! git merge-base --is-ancestor "$FULL" "$FALLBACK" 2>/dev/null; then
  emit "$FALLBACK" "deployed ${FULL} is not an ancestor of the fallback — using it could only narrow the range"
fi

if [ "$FULL" = "$(git rev-parse --verify --quiet "${FALLBACK}^{commit}" 2>/dev/null)" ]; then
  emit "$FALLBACK" "production already serves the fallback base — nothing stranded"
fi

emit "$FULL" "production serves ${DEPLOYED}, which is below the fallback — widening the range to include what never released"
