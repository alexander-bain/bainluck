#!/bin/bash
# native/225 (#6444 row 19) — ONE reserved-simulator guard, for every rig entrypoint.
#
# WHAT THIS PROTECTS. Two simulators hold Alex's signed-in account: the launch
# candidate's row-19 evidence, which only he can re-create because no lane may
# sign in. `iPhone 17` / 76D961F0 (iOS 26.5) was reinstalled by some gate on
# 2026-09-17 and the state had to be restored by hand; `iPhone 17` / DD0DC456
# (iOS 27.0) is the device he signed in on afterwards.
#
# WHY A SHARED FILE AND NOT A FIFTH COPY. `scripts/ios_native_gate.sh` grew this
# guard on 2026-09-17 (PR #6910) and that fixed the gate and nothing else. Five
# other rig entrypoints still pointed at the reserved device, three of them by
# hardcoding its UDID as their DEFAULT — so the protection existed exactly where
# someone had already thought about it, which is the definition of a convention
# rather than a guard. The lesson from #6910 was that a convention is not a
# guard; a second bespoke copy would have been the same mistake with a wider
# blast radius.
#
# 🪤 THE SHOOT TOOLS' OWN DOCUMENTED REMEDY IS DESTRUCTIVE. `native-shoot.sh`'s
# header says, correctly, that once the notification alert is up it belongs to
# SpringBoard and the fix is "ERASE AND RE-SHOOT". With a reserved UDID as the
# default SIM, a lane following that instruction to the letter erases Alex's
# device. The header is right; the default was wrong.
#
# ═══ 🔴 WHY THE RESERVED SET IS A LIST (native/233, 2026-09-18) ═══
#
# IT WAS A SCALAR, AND A SCALAR HANDED OUT THE DEVICE IT EXISTED TO PROTECT.
# Alex signed in on a SECOND simulator, and the machine's actual state stopped
# being expressible: one variable, two devices to protect. Measured read-only by
# latency/562 at 1712Z and reproduced here before the edit —
#
#     bl_default_shoot_sim()                          -> DD0DC456   ← Alex's NEW device
#     BAINLUCK_RESERVED_SIMULATOR=DD0DC456 …          -> 76D961F0   ← the OTHER one
#
# It never returned a disposable device in EITHER configuration, and the override
# this file's own refusal message advertised did not fix it — it swapped which
# protected device got handed out. Two independent causes, both needing the list:
#
#   1. the refusal was an equality test, so exactly one UDID could be protected;
#   2. `bl_default_shoot_sim` filtered exactly one UDID and then took the first
#      iPhone sorted by MODEL NAME — and both of Alex's devices are named exactly
#      `iPhone 17`, so excluding one leaves the other first in line. The
#      same-model preference (below) is what steers it there, which is right for
#      geometry and was silently wrong for safety.
#
# THE SELF-TEST WAS GREEN THROUGHOUT. Its assertion 4 read "the default is never
# THE reserved device" — singular, like the variable — so it passed while the
# picker handed out Alex's other phone. A guard shaped like the bug it is
# checking cannot see it; that assertion is now over the whole set.
#
# 🔴 THE OVERRIDE IS ADDITIVE AND CANNOT UN-PROTECT. It used to REPLACE the set,
# which is how "protect this one too" became "stop protecting that one" in a
# single export — the exact swap measured above. `BAINLUCK_RESERVED_SIMULATOR`
# now ADDS to the built-in set and nothing removes from it. Retiring a device is
# an edit to the list below, which is the right amount of friction for a change
# that means "you may now erase Alex's signed-in phone".
#
# Sourced, never executed:  . "$(dirname "$0")/reserved-sim-guard.sh"

# The devices no rig tool may install to, erase, shoot or test on.
#
# DEFAULTS TO PROTECTING: an unset override is BOTH reserved UDIDs, never an
# empty allowlist. Adding a UDID here is how a device becomes protected;
# removing one is how it stops. `BAINLUCK_RESERVED_SIMULATOR` (space- or
# comma-separated, one or many) only ever ADDS.
BL_RESERVED_SIMS="76D961F0-8575-479F-ABCE-652D8A79DBF9
DD0DC456-E7C7-4740-8F5A-6BE6F61B606C"
if [ -n "${BAINLUCK_RESERVED_SIMULATOR:-}" ]; then
    BL_RESERVED_SIMS="${BL_RESERVED_SIMS}
$(printf '%s' "$BAINLUCK_RESERVED_SIMULATOR" | tr ', ' '\n\n')"
fi

# Is this UDID reserved? Membership over the whole set — NOT an equality test,
# which is what could only ever hold one device.
bl_is_reserved_sim() {
    [ -n "${1:-}" ] || return 1
    printf '%s\n' "$BL_RESERVED_SIMS" | /usr/bin/grep -qxF "$1"
}

# Refuse to act on a reserved device. Exit 7, matching the gate's preflight so
# a caller reading exit codes sees one meaning across the rig.
bl_refuse_reserved_sim() {
    _udid="${1:-}"
    _tool="${2:-$(basename "${0:-rig}")}"
    bl_is_reserved_sim "$_udid" || return 0
    echo "${_tool}: REFUSED — ${_udid} is a RESERVED simulator." >&2
    echo "" >&2
    echo "  That device holds Alex's signed-in account for the launch check." >&2
    echo "  Installing, erasing or shooting on it destroys evidence nobody" >&2
    echo "  here can re-create. Use a disposable device." >&2
    echo "" >&2
    echo "  There is no un-protect switch: BAINLUCK_RESERVED_SIMULATOR only ADDS" >&2
    echo "  to the reserved set. Retiring a device is an edit to" >&2
    echo "  tools/reserved-sim-guard.sh, on purpose." >&2
    exit 7
}

# A disposable iPhone UDID, or empty when the machine has none.
#
# Prefers another device of the SAME MODEL as a reserved one. MEASURED
# 2026-09-18: `iPhone 17` and `iPhone 17 Pro` both shoot 1206x2622 (402x874 @3x),
# so this is geometry-preserving either way and every historical LOOK stays
# comparable — but same-model first means that stays true if a future model's
# geometry differs.
#
# EVERY reserved UDID is filtered, not one. When only one was, this preference
# for the same model is precisely what promoted Alex's identically-named second
# device to the front of the queue.
bl_default_shoot_sim() {
    _pick_lines=$(xcrun simctl list devices available 2>/dev/null \
      | /usr/bin/grep -E '^[[:space:]]+iPhone ' \
      | sed -E 's/^[[:space:]]+//' \
      | sort -t'(' -k1,1)
    printf '%s\n' "$_pick_lines" | while IFS= read -r _line; do
        [ -n "$_line" ] || continue
        _udid=$(printf '%s' "$_line" | sed -E 's/.*\(([0-9A-Fa-f-]{36})\).*/\1/')
        case "$_udid" in
            "$_line") continue ;;   # no UDID on the line at all
        esac
        bl_is_reserved_sim "$_udid" && continue
        printf '%s\n' "$_udid"
        break
    done
}
