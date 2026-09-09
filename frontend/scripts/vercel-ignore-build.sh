#!/usr/bin/env bash
# Vercel "Ignored Build Step" — decides whether Vercel builds this commit at all.
#
# WHY THIS EXISTS (#4456, Fable-5 4:26pm PT 2026-09-09, off Alex's 50%-budget mail):
# the deploy log showed ~20 Vercel deploys/hour of which 17 were PREVIEW builds
# (`target:null`) — one per lane branch push, ten lanes pushing all day. Preview
# builds are the on-demand spend, and nobody reads them: the previews are
# auth-gated, so every lane already shoots PRODUCTION for its LOOK (notice 4).
# We were paying full build price for artifacts with no reader.
#
# VERCEL'S CONTRACT IS INVERTED — get this backwards and you either build
# everything (no saving) or build nothing (master stops deploying):
#     exit 0  -> SKIP the build
#     exit 1  -> PROCEED with the build
#
# The rule: build production and master. Skip everything else, unless the commit
# explicitly opts in.
#
# FAIL-SAFE DIRECTION: every branch of this script that is not a confident
# "this is a disposable preview" exits 1 (build). A missing or empty environment
# variable must never silently stop master from deploying, so the unknown case
# builds — we would rather pay for one wasted build than lose a production deploy.

set -u

log () { echo "[vercel-ignore] $*"; }

# --- 1. Production is never skipped. ------------------------------------------
# VERCEL_ENV is "production" for the production deployment of the production
# branch. This is the load-bearing guard: if everything else in this script were
# wrong, this line still keeps the site deploying.
if [ "${VERCEL_ENV:-}" = "production" ]; then
  log "VERCEL_ENV=production -> BUILD"
  exit 1
fi

# --- 2. master builds, whatever Vercel calls the environment. -----------------
# Belt and braces with (1): if the project's production branch is ever
# reconfigured, master must still build.
BRANCH="${VERCEL_GIT_COMMIT_REF:-}"
if [ "$BRANCH" = "master" ]; then
  log "branch=master -> BUILD"
  exit 1
fi

# --- 3. Explicit per-commit opt-in. -------------------------------------------
# Fable asked for a `wants-preview` PR label. A label is NOT readable from this
# hook — Vercel exposes no PR metadata and an API call here would need a token in
# Vercel's env — so the durable, dependency-free equivalent is a commit-message
# flag. Put `wants-preview` anywhere in the commit message (or amend it onto the
# branch tip) and that push builds a preview as before.
MSG="${VERCEL_GIT_COMMIT_MESSAGE:-}"
case "$MSG" in
  *wants-preview*)
    log "commit message opts in via 'wants-preview' -> BUILD"
    exit 1
    ;;
esac

# --- 4. Unknown branch => build. ----------------------------------------------
# An empty VERCEL_GIT_COMMIT_REF means we could not identify the branch. We do
# not know it is disposable, so we do not skip it.
if [ -z "$BRANCH" ]; then
  log "branch could not be determined -> BUILD (fail-safe)"
  exit 1
fi

# --- 5. Everything left is a lane branch preview. -----------------------------
log "branch=$BRANCH is not master and did not opt in -> SKIP"
log "to force a preview, include 'wants-preview' in the commit message"
exit 0
