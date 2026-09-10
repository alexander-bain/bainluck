# shellcheck shell=sh
# tools/lane-zdotdir/.zshenv — the carrier for notice 39 rung 2.
#
# `lane-runner.sh` points `ZDOTDIR` here for the lane's headless `claude` process. Every
# shell that session then spawns reads THIS file, so `tools/bl-agent-curl.sh` is installed
# in every one of them and a lane's production reads carry `x-bainluck-origin` without any
# lane changing a command.
#
# ## Why ZDOTDIR and not the line notice 39 actually specifies
#
# Notice 39 rung 2 says "ONE line in `lane-runner.sh` that exports `BL_AGENT=<lane>` and
# sources latency's curl shadow". The export half works. **The sourcing half cannot** — it
# would merge, pass every gate, be recorded done, and tag nothing (#4662).
#
# A lane's every `Bash` tool call is a FRESH shell, exec'd from the profile. The shadow
# installs a shell FUNCTION, and a function is not inherited across `exec`. Measured from
# a live lane session: sourcing the real file, then exec'ing one child, gives
#
#     sourcing shell: curl is a shell function from .../tools/bl-agent-curl.sh
#     CHILD shell:    curl is /usr/bin/curl
#
# and a variable exported plus a function defined in one Bash call were both gone by the
# next. It is #4632's shape — D70 merged, tested, ruled, and inert for four days.
#
# `ZDOTDIR` is an ordinary environment variable, so it DOES cross the exec. Pointing it at
# a tracked repo directory is the only mechanism measured to put the shadow in the shell
# that actually types the curl.
#
# ## Why `.zshenv` specifically, and not `.zshrc`
#
# The lane shell is login NON-interactive (`flags=569Xl`, no `i`). Marker-per-file test:
#
#   | invocation                       | .zshenv | .zprofile | .zshrc | .zlogin |
#   |----------------------------------|---------|-----------|--------|---------|
#   | `zsh -l -c` (what the lane gets) | yes     | yes       | **no** | yes     |
#   | `zsh -c`                         | yes     | no        | no     | -       |
#
# `~/.zshrc` is NEVER read by a lane shell. `.zshenv` is read by every zsh there is.
#
# 🔴 An earlier read of mine said ".zshrc IS read", off `PATH` and `HOMEBREW_PREFIX` being
# present. That was CONTAMINATED: both are exported, so they were inherited, not sourced.
# Only a marker defined solely inside each file can tell "this file ran" from "this value
# arrived from the parent".
#
# ## Why ZDOTDIR beats editing `~/.zshenv`
#
# It is set only by `lane-runner.sh`, so the shadow exists only inside lane sessions —
# Alex's own terminals are untouched — and the whole mechanism stays tracked in the repo
# instead of living on one laptop.
#
# ## The cost this file exists to pay
#
# Redirecting ZDOTDIR does not add a startup file, it MOVES the whole search: zsh now looks
# for `.zprofile`, `.zshrc` and `.zlogin` HERE and stops reading the user's. Silently
# dropping `~/.zprofile` out of every lane shell is a bigger regression than the one rung 2
# fixes. So each of the four files in this directory chains its real counterpart, and this
# directory is only ever pointed at when `.zshenv` is verified present (`lane-runner.sh`).
#
# Nothing here may fail: no `set -e`, every source guarded on presence. A broken startup
# file breaks every command every lane runs.

# Re-entrancy guard. Sourcing `$HOME/.zshenv` is a loop if HOME's copy is ever a symlink to
# this one, or if a user file re-points ZDOTDIR back here.
if [ -z "${_BL_ZDOTDIR_ZSHENV:-}" ]; then
    _BL_ZDOTDIR_ZSHENV=1

    # 1. Chain the real one first, so anything it sets is in place before the shadow loads
    #    and so a lane shell is otherwise indistinguishable from an untouched one.
    if [ -n "${HOME:-}" ] && [ "${ZDOTDIR:-}" != "$HOME" ] && [ -f "$HOME/.zshenv" ]; then
        . "$HOME/.zshenv"
    fi

    # 2. Install the tag. Self-locating from ZDOTDIR, so there is no second env var to keep
    #    in sync and no absolute path baked into a tracked file — this directory is always
    #    `<repo>/tools/lane-zdotdir`, so the shadow is always its sibling.
    #
    #    NOTICE 39 GUARD 1: an ABSENT shadow file falls through to plain `curl`. That is not
    #    hypothetical — `~/bainluck/tools/bl-agent-curl.sh` did not exist on disk on
    #    2026-09-09 (that tree was stale at `8991f1a6`; the shadow merged later at
    #    `8c37c7f0`), which is exactly the path the shadow's own docstring tells agents to
    #    source. Guarding on presence is what keeps a stale checkout from being a broken
    #    shell instead of an untagged one.
    if [ -n "${ZDOTDIR:-}" ] && [ -f "$ZDOTDIR/../bl-agent-curl.sh" ]; then
        . "$ZDOTDIR/../bl-agent-curl.sh"
    fi
fi
