# shellcheck shell=sh
# tools/lane-zdotdir/.zprofile — chain only. See `.zshenv` in this directory for why.
#
# Pointing ZDOTDIR at this directory MOVES zsh's whole startup search, it does not add to
# it: without this file, `$HOME/.zprofile` silently stops being read in every lane shell. That
# would be a larger regression than the one rung 2 exists to fix, so each of the four names
# zsh looks for is present here and does nothing but chain the real one.
#
# Guarded and unconditional-success on purpose: a startup file that can fail breaks every
# command every lane runs.

if [ -n "${HOME:-}" ] && [ "${ZDOTDIR:-}" != "$HOME" ] && [ -f "$HOME/.zprofile" ]; then
    . "$HOME/.zprofile"
fi
