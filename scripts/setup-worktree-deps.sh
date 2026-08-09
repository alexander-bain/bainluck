#!/usr/bin/env bash
# Give a program worktree its frontend deps, so a lane (or codex) can run the
# EXACT-BRANCH suites instead of master's.
#
# Why a symlink and not `npm ci`: a full install per worktree costs minutes and
# ~1GB of disk each, times three live slots. The dependency tree is identical
# across worktrees in practice -- what differs is the source, which is what the
# suites are actually testing.
#
# Why this script exists at all: the symlink kept getting DELETED. `.gitignore`
# had `node_modules/` with a trailing slash, which does not match a symlink, so
# git reported it as untracked and the standing advice became "remove it before
# committing". Lanes complied, and every refreshed worktree then arrived with no
# deps -- the ts-jest report of 2026-08-09. The slash is fixed; this script makes
# the setup one command instead of folklore.
#
# Usage:
#   scripts/setup-worktree-deps.sh                 # current worktree
#   scripts/setup-worktree-deps.sh ~/bainluck-dev/ux
set -euo pipefail

MASTER_MODULES="$HOME/bainluck/frontend/node_modules"
TARGET="${1:-$(git rev-parse --show-toplevel)}"

if [ ! -d "$MASTER_MODULES" ]; then
  echo "FAIL: $MASTER_MODULES does not exist. Run 'npm install' in ~/bainluck/frontend first;" >&2
  echo "      that is the one real install every worktree borrows." >&2
  exit 1
fi

if [ ! -d "$TARGET/frontend" ]; then
  echo "FAIL: $TARGET/frontend is not a directory -- is $TARGET a bainluck worktree?" >&2
  exit 1
fi

if [ -d "$TARGET/frontend/node_modules" ] && [ ! -L "$TARGET/frontend/node_modules" ]; then
  echo "SKIP: $TARGET/frontend/node_modules is a REAL directory, not a symlink."
  echo "      Leaving it alone -- someone installed deliberately, and replacing a real"
  echo "      install with a link to another tree's is not this script's call."
  exit 0
fi

ln -sfn "$MASTER_MODULES" "$TARGET/frontend/node_modules"
echo "linked: $TARGET/frontend/node_modules -> $MASTER_MODULES"

# Prove it, rather than assuming. ts-jest is the specific package whose absence
# was reported, and a bare `ls node_modules` would have looked fine while the
# suite still could not run.
missing=0
for pkg in ts-jest jest next typescript; do
  if [ ! -e "$TARGET/frontend/node_modules/$pkg" ]; then
    echo "  MISSING: $pkg" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "FAIL: master's node_modules is incomplete. Run 'npm install' in ~/bainluck/frontend." >&2
  exit 1
fi
echo "verified: ts-jest, jest, next, typescript all resolve"

# git must not see it. If this ever prints, the .gitignore slash regressed.
if git -C "$TARGET" status --porcelain 2>/dev/null | grep -q 'frontend/node_modules'; then
  echo "WARN: git still sees frontend/node_modules as untracked -- the .gitignore" >&2
  echo "      'node_modules' entry (NO trailing slash) has regressed. Fix that rather" >&2
  echo "      than deleting the link; deleting it is what caused this script to exist." >&2
  exit 1
fi
echo "clean: git does not see the symlink. Run suites with TZ=UTC (CI is UTC)."
