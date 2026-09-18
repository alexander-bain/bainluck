#!/bin/bash
# native/225 (#6444 row 19) — ONE reserved-simulator guard, for every rig entrypoint.
#
# WHAT THIS PROTECTS. `iPhone 17` / 76D961F0 holds Alex's signed-in account: the
# launch candidate's row-19 evidence, which only he can re-create because no lane
# may sign in. It was reinstalled by some gate on 2026-09-17 and the state had to
# be restored by hand.
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
# SpringBoard and the fix is "ERASE AND RE-SHOOT". With the reserved UDID as the
# default SIM, a lane following that instruction to the letter erases Alex's
# device. The header is right; the default was wrong.
#
# Sourced, never executed:  . "$(dirname "$0")/reserved-sim-guard.sh"

# Defaults to PROTECTING: an unset variable is the reserved UDID, never an empty
# allowlist. Same variable the gate reads, so one export moves both.
BL_RESERVED_SIM="${BAINLUCK_RESERVED_SIMULATOR:-76D961F0-8575-479F-ABCE-652D8A79DBF9}"

# Refuse to act on the reserved device. Exit 7, matching the gate's preflight so
# a caller reading exit codes sees one meaning across the rig.
bl_refuse_reserved_sim() {
    _udid="${1:-}"
    _tool="${2:-$(basename "${0:-rig}")}"
    [ "$_udid" = "$BL_RESERVED_SIM" ] || return 0
    echo "${_tool}: REFUSED — ${_udid} is the RESERVED simulator." >&2
    echo "" >&2
    echo "  That device holds Alex's signed-in account for the launch check." >&2
    echo "  Installing, erasing or shooting on it destroys evidence nobody" >&2
    echo "  here can re-create. Use a disposable device." >&2
    echo "" >&2
    echo "  Override only if you are certain: BAINLUCK_RESERVED_SIMULATOR=<other-udid>" >&2
    exit 7
}

# A disposable iPhone UDID, or empty when the machine has none.
#
# Prefers another device of the SAME MODEL as the reserved one. MEASURED
# 2026-09-18: `iPhone 17` and `iPhone 17 Pro` both shoot 1206x2622 (402x874 @3x),
# so this is geometry-preserving either way and every historical LOOK stays
# comparable — but same-model first means that stays true if a future model's
# geometry differs.
bl_default_shoot_sim() {
    xcrun simctl list devices available 2>/dev/null \
      | /usr/bin/grep -E '^[[:space:]]+iPhone ' \
      | sed -E 's/^[[:space:]]+//' \
      | /usr/bin/grep -v "$BL_RESERVED_SIM" \
      | sort -t'(' -k1,1 \
      | sed -E 's/.*\(([0-9A-Fa-f-]{36})\).*/\1/' \
      | head -1
}
