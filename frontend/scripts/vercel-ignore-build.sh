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
# WHY IT GREW A PRODUCTION HALF (#7846, off Alex's 75%-budget mail 2026-09-21):
# Build CPU is ~98% of billed usage, and two of the latest five READY production
# builds (21730d011a, 0c58f558f8) changed backend files ONLY. We were paying to
# rebuild the website when the website had not changed. Part 2 below skips those.
#
# VERCEL'S CONTRACT IS INVERTED — get this backwards and you either build
# everything (no saving) or build nothing (master stops deploying):
#     exit 0  -> SKIP the build
#     exit 1  -> PROCEED with the build
#
# FAIL-SAFE DIRECTION: every branch of this script that is not a confident
# "this is a disposable preview" / "the live website already contains this
# commit's web inputs" exits 1 (build). A missing or empty environment variable,
# an unreachable marker, an unresolvable sha or a failed git command must never
# silently stop master from deploying, so the unknown case builds — we would
# rather pay for one wasted build than lose a production deploy.

set -u

log () { echo "[vercel-ignore] $*"; }

BRANCH="${VERCEL_GIT_COMMIT_REF:-}"
MSG="${VERCEL_GIT_COMMIT_MESSAGE:-}"

# --- 0. Explicit per-commit opt-in, on ANY deployment. ------------------------
# Fable asked for a `wants-preview` PR label. A label is NOT readable from this
# hook — Vercel exposes no PR metadata and an API call here would need a token in
# Vercel's env — so the durable, dependency-free equivalent is a commit-message
# flag. Put `wants-preview` (a lane branch) or `force-build` (a production build
# this script would otherwise skip) anywhere in the commit message and that push
# builds. This is deliberately the FIRST test: the override has to outrank every
# piece of cleverness below it, or it is not an override.
case "$MSG" in
  *wants-preview*|*force-build*)
    log "commit message opts in ('wants-preview'/'force-build') -> BUILD"
    exit 1
    ;;
esac

# ==============================================================================
# PART 2 — production: build only when the live website is not already current.
# ==============================================================================
#
# THE QUESTION IS NOT "did this commit touch frontend/". It is "is the deployed
# frontend current". A first-parent diff cannot answer that: if a web change rode
# a batch whose deploy failed or was canceled, the next backend-only push must
# still rebuild it, and HEAD^..HEAD would say "nothing to do" and strand it.
#
# So the comparison base is the commit the website is ACTUALLY SERVING, read from
# our own public build marker (`/api/frontend-build`, `frontend/lib/buildInfo.ts`,
# force-dynamic + no-store). That marker is ground truth in a way no git heuristic
# is: it proves a deployment both succeeded and is serving. Its consequence is the
# property this whole section rests on — skipping does not move the live commit,
# so the NEXT push diffs from the same base and still sees the undeployed web
# change. A skip can therefore delay a web deploy by zero commits; it cannot
# strand one.
#
# `VERCEL_GIT_PREVIOUS_SHA` (Vercel's own previous-successful-deployment
# metadata, exposed only to this hook) is consulted as an ADDITIONAL gate, never
# as the authority: its exact semantics around failed and canceled deployments
# are not verified here, so it is only ever allowed to turn a SKIP into a BUILD.
# Both values are logged on every production run so the first real deployments
# settle those semantics from evidence rather than from documentation.

# Paths that are provably not inputs to `npm install && npm run build` run inside
# `frontend/` (the Vercel root directory). Everything NOT listed here — including
# frontend/package.json, frontend/package-lock.json, frontend/next.config.mjs,
# frontend/vercel.json, root scripts, tools/, and any directory nobody has thought
# of yet — counts as a web input and forces a build. The list is an EXCLUSION list
# for exactly that reason: the unknown path must land on the expensive side.
NON_WEB_PATHS=(
  ':(top,exclude)backend/'   # Python/FastAPI, deployed to Heroku
  ':(top,exclude)ios/'       # Swift/Xcode, not in any web bundle
  ':(top,exclude)docs/'      # markdown reference docs
  ':(top,exclude).claude/'   # lane handoff files
  ':(top,exclude).github/'   # GitHub Actions workflows; Vercel does not read them
  # Added by #7846 part b. These are the same CLASS as the five above and were
  # simply missed: Vercel's root directory is `frontend/`, so a repo-TOP-level
  # directory is outside the build root and cannot be read by `npm install &&
  # npm run build` — the identical argument that justifies excluding `backend/`.
  # They were the three biggest remaining build-forcers on master (30 h to
  # 2026-09-21: artifacts/ 67 file-changes, tools/ 21, scripts/ 2).
  ':(top,exclude)artifacts/' # lane measurement output (probes, PNGs, JSONL)
  ':(top,exclude)tools/'     # repo-root lane tooling (look.sh, merge-gate.sh)
  ':(top,exclude)scripts/'   # repo-root Python lane tooling (claim_lane_lock.py)
  # Added by #7846 part c. These two live INSIDE the Vercel root, so the "outside
  # the build root" argument above does not reach them — they are excluded on
  # measured evidence instead. Probe: a hard parse error was injected into one
  # file in each directory (`SyntaxError: Unexpected token ')'` / `TS1005`) and
  # `npm run build` still exited 0. `next build` never reads them, because
  # nothing under app/, components/ or lib/ imports them, next.config.mjs sets
  # `typescript.ignoreBuildErrors` (so the build prints "Skipping validation of
  # types" and tsconfig's `**/*.ts` never runs), and no `eslint.dirs` override
  # widens lint past its defaults. The contract suite pins that premise, so
  # removing either half of it fails loudly instead of stranding a web change.
  ':(top,exclude)frontend/__tests__/' # jest unit tests; not in the module graph
  ':(top,exclude)frontend/e2e/'       # contract + playwright suites; tsconfig already excludes e2e
)
# 🪤 `:(top,...)` anchors at the repo root, so `scripts/` above excludes ONLY the
# top-level directory — `frontend/scripts/` (which holds THIS hook) is still a
# web input and still forces a build. The contract suite pins that both ways.

# The live-marker endpoint. Overridable so the contract suite can point the real
# script at a fixture; the apex host 307s to www, so www is the default.
MARKER_URL="${BUILD_FILTER_MARKER_URL:-https://www.bainluck.com/api/frontend-build}"

# Sets CHANGED to the web build inputs that differ between $1 and HEAD.
# Returns non-zero if the diff itself could not be computed — which the caller
# must treat as BUILD. This deliberately does NOT `exit` and is deliberately not
# called inside `$( )`: an `exit` from a command substitution kills the subshell
# and leaves the parent reading an empty result, i.e. a failed git command would
# have read as "nothing changed" and skipped the build.
CHANGED=""
compute_changed () {
  CHANGED=$(git diff --name-only "$1" "$HEAD_SHA" -- "${NON_WEB_PATHS[@]}" 2>/dev/null) || return 1
  return 0
}

# Resolves $1 to a commit that is an ancestor of HEAD, or exits the script with
# BUILD. A sha outside a shallow clone, a rolled-back deployment, or a rewritten
# history all land here, and all of them mean "we cannot tell" — so we build.
require_usable_base () {
  local sha="$1" label="$2"
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    log "$label ${sha} is not in this clone (shallow or rewritten history) -> BUILD (fail-safe)"
    exit 1
  fi
  if ! git merge-base --is-ancestor "$sha" "$HEAD_SHA" 2>/dev/null; then
    log "$label ${sha} is not an ancestor of HEAD (rollback or divergence) -> BUILD (fail-safe)"
    exit 1
  fi
}

decide_production () {
  if ! command -v git >/dev/null 2>&1; then
    log "git is unavailable -> BUILD (fail-safe)"
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    log "curl is unavailable -> BUILD (fail-safe)"
    exit 1
  fi

  # The commit being deployed. Empty means we are not in a real Vercel git
  # deployment and cannot identify what we would be comparing.
  local head_env="${VERCEL_GIT_COMMIT_SHA:-}"
  if [ -z "$head_env" ]; then
    log "VERCEL_GIT_COMMIT_SHA is empty -> BUILD (fail-safe)"
    exit 1
  fi
  if ! HEAD_SHA=$(git rev-parse --verify --quiet "${head_env}^{commit}"); then
    log "VERCEL_GIT_COMMIT_SHA=${head_env} does not resolve here -> BUILD (fail-safe)"
    exit 1
  fi

  # --- the live website's own answer to "what are you serving?" ---------------
  local body live_sha
  body=$(curl -fsSL --connect-timeout 5 --max-time 10 "$MARKER_URL" 2>/dev/null) || body=""
  if [ -z "$body" ]; then
    log "build marker ${MARKER_URL} unreachable -> BUILD (fail-safe)"
    exit 1
  fi
  body=$(printf '%s' "$body" | tr -d '[:space:]')
  case "$body" in
    *'"env":"production"'*) : ;;
    *)
      log "build marker does not report env=production -> BUILD (fail-safe)"
      exit 1
      ;;
  esac
  # `"commit":null` and any abbreviation fail this on purpose: only a full
  # 40-hex sha is a base we are willing to skip a production build against.
  live_sha=$(printf '%s' "$body" | sed -n 's/.*"commit":"\([0-9a-f]\{40\}\)".*/\1/p')
  if [ -z "$live_sha" ]; then
    log "build marker carries no full 40-hex commit -> BUILD (fail-safe)"
    exit 1
  fi

  local prev_sha="${VERCEL_GIT_PREVIOUS_SHA:-}"
  log "head=${HEAD_SHA} live=${live_sha} previous=${prev_sha:-<unset>}"

  # A redeploy of the commit that is already serving is somebody asking for a
  # rebuild of exactly this tree. Never swallow that.
  if [ "$live_sha" = "$HEAD_SHA" ]; then
    log "the live website is already built from this commit (redeploy) -> BUILD"
    exit 1
  fi

  require_usable_base "$live_sha" "live commit"
  if ! compute_changed "$live_sha"; then
    log "git diff against live commit ${live_sha} failed -> BUILD (fail-safe)"
    exit 1
  fi
  if [ -n "$CHANGED" ]; then
    log "web build inputs changed since the live commit -> BUILD"
    printf '%s\n' "$CHANGED" | sed 's/^/[vercel-ignore]   /'
    exit 1
  fi

  # Additional gate, never the authority (see the note above).
  if [ -n "$prev_sha" ]; then
    require_usable_base "$prev_sha" "VERCEL_GIT_PREVIOUS_SHA"
    if ! compute_changed "$prev_sha"; then
      log "git diff against VERCEL_GIT_PREVIOUS_SHA ${prev_sha} failed -> BUILD (fail-safe)"
      exit 1
    fi
    if [ -n "$CHANGED" ]; then
      log "web build inputs changed since VERCEL_GIT_PREVIOUS_SHA -> BUILD"
      printf '%s\n' "$CHANGED" | sed 's/^/[vercel-ignore]   /'
      exit 1
    fi
  fi

  log "the live website already contains every web build input of this commit -> SKIP"
  log "to force a production build, include 'force-build' in the commit message"
  exit 0
}

# --- 1. Production, and master whatever Vercel calls the environment. ---------
# Belt and braces: if the project's production branch is ever reconfigured,
# master still takes the production path rather than being read as a preview.
if [ "${VERCEL_ENV:-}" = "production" ] || [ "$BRANCH" = "master" ]; then
  log "production path (VERCEL_ENV=${VERCEL_ENV:-<unset>} branch=${BRANCH:-<unset>})"
  decide_production
  # Unreachable: every path in decide_production exits. Kept because falling
  # through would land on the PREVIEW rules below, and those end in `exit 0` —
  # a future edit that turns one `exit` into a `return` would silently stop
  # master deploying rather than fail loudly.
  log "decide_production returned without deciding -> BUILD (fail-safe)"
  exit 1
fi

# --- 2. Unknown branch => build. ----------------------------------------------
# An empty VERCEL_GIT_COMMIT_REF means we could not identify the branch. We do
# not know it is disposable, so we do not skip it.
if [ -z "$BRANCH" ]; then
  log "branch could not be determined -> BUILD (fail-safe)"
  exit 1
fi

# --- 3. Everything left is a lane branch preview. -----------------------------
log "branch=$BRANCH is not master and did not opt in -> SKIP"
log "to force a preview, include 'wants-preview' in the commit message"
exit 0
