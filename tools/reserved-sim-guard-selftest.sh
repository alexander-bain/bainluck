#!/bin/bash
# native/225 — the reserved-simulator guard, and the ban on re-introducing a
# bespoke default, are both testable.
#
# WHY A TREE SCAN AND NOT JUST UNIT ASSERTIONS. The guard's behaviour was never
# the hard part; the hard part is that on 2026-09-17 the gate grew a correct
# guard and five other entrypoints kept pointing at the reserved device. Nothing
# in the repo could SEE that. Assertions 5 and 6 are the ones that would have
# caught it, so they are the reason this file exists.
#
#   bash tools/reserved-sim-guard-selftest.sh     # exit 0 = clean
#
# 🔴 WHY ASSERTION 4 IS OVER A SET (native/233, 2026-09-18). It read "the
# resolved default is never THE reserved device" — singular, because the
# variable was — and it was GREEN on 2026-09-18 while `bl_default_shoot_sim`
# handed out Alex's newly signed-in `iPhone 17`. One device was protected; two
# needed to be; the assertion could not see the difference because it was shaped
# like the bug. Assertions 4, 7 and 8 are over the whole set, and 8 is the one
# that fails if the override is ever made subtractive again.
set -u
cd "$(dirname "$0")/.."
RESERVED=76D961F0-8575-479F-ABCE-652D8A79DBF9
RESERVED2=DD0DC456-E7C7-4740-8F5A-6BE6F61B606C
FAILED=0
ok()   { echo "  ok   — $1"; }
fail() { echo "  FAIL — $1" >&2; FAILED=$((FAILED+1)); }

# The entrypoints that select or accept a simulator. Adding a rig tool that
# takes a device means adding it here.
#
# 🔴 `tools/native-gates.sh` JOINED THIS LIST ON 2026-09-18 (native/233c) and it
# is the reason assertion 10 exists. It was missing while the guard shipped, and
# it is the one entrypoint that INSTALLS A TEST BUNDLE — so the list that decides
# what is guarded omitted the caller with the most to lose. Adding a rig tool
# that takes or resolves a device means adding it here, and the omission is
# exactly what nothing else can see.
#
# 🔴 `tools/native-firstcard.sh` JOINED ON 2026-09-19 (native/249) — and it is
# the reason assertions 11 and 12 exist. It terminated the app, deleted its
# caches and relaunched it six times over, at the literal target `booted`, which
# for four consecutive sessions was Alex's signed-in `DD0DC456`. Four handoffs
# named the hazard in prose and none of them could make the repo say it, because
# the list below is hand-maintained and the file took no device argument — there
# was nothing that LOOKED like a device to guard. The comment above says adding
# a tool means adding it here; that instruction had already been missed twice
# when it was written. A list that must be remembered is the same shape of
# defect as the convention this whole file replaced, so 11 derives the list.
ENTRYPOINTS="tools/native-shoot.sh tools/native_live_shoot.sh tools/native-g1-shoot.sh tools/native-uitest.sh tools/native-walk.sh tools/native-gates.sh tools/native-firstcard.sh tools/native-925-scrub-shoot.sh tools/native-257-freeze-shoot.sh"

echo "1. the guard refuses the reserved device with exit 7"
( . tools/reserved-sim-guard.sh; bl_refuse_reserved_sim "$RESERVED" selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "exit 7" || fail "expected exit 7"

echo "2. the guard passes a disposable device"
( . tools/reserved-sim-guard.sh; bl_refuse_reserved_sim 00000000-0000-0000-0000-000000000000 selftest ) >/dev/null 2>&1
[ $? -eq 0 ] && ok "exit 0" || fail "a non-reserved udid must not be refused"

echo "2b. BOTH of Alex's devices are refused, not just the first"
( . tools/reserved-sim-guard.sh; bl_refuse_reserved_sim "$RESERVED2" selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "exit 7 on $RESERVED2" || fail "the second signed-in device is NOT protected"

echo "3. BAINLUCK_RESERVED_SIMULATOR ADDS to what is protected"
( BAINLUCK_RESERVED_SIMULATOR=DEADBEEF . tools/reserved-sim-guard.sh
  bl_refuse_reserved_sim DEADBEEF selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "override protects the device it names" || fail "override protected nothing"
( BAINLUCK_RESERVED_SIMULATOR="$RESERVED2 DEADBEEF" . tools/reserved-sim-guard.sh
  bl_refuse_reserved_sim DEADBEEF selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "override takes a list" || fail "override does not accept several udids"

echo "4. the resolved default is never ANY reserved device"
. tools/reserved-sim-guard.sh
# The set must be NON-EMPTY before "is the pick in it" means anything. Measured
# while proving this file red against the old scalar guard: `bl_is_reserved_sim`
# answers "no" to everything when the set is unset, so this assertion printed
# `ok` for a pick that WAS Alex's device. An emptied set is the one input that
# makes the rest of this file agree with a broken guard.
RESERVED_COUNT=$(printf '%s' "${BL_RESERVED_SIMS:-}" | /usr/bin/grep -c .)
[ "$RESERVED_COUNT" -ge 2 ] \
  && ok "the reserved set holds $RESERVED_COUNT udids, so the checks below can fail" \
  || fail "the reserved set holds $RESERVED_COUNT udids — every check below is vacuous"
for u in "$RESERVED" "$RESERVED2"; do
  bl_is_reserved_sim "$u" || fail "$u is not in the reserved set"
done
PICK=$(bl_default_shoot_sim)
if [ -z "$PICK" ]; then
  ok "no iPhone on this machine — vacuously clean, and the callers :? on it"
elif bl_is_reserved_sim "$PICK"; then
  fail "bl_default_shoot_sim returned a RESERVED device: $PICK"
else
  ok "picked $PICK, and it is in none of $(printf '%s' "$BL_RESERVED_SIMS" | /usr/bin/grep -c .) reserved udids"
fi

echo "5. no entrypoint hardcodes the reserved UDID as its device"
# The guard file itself is where the constant is allowed to live; the gate has
# its own copy of the refusal (a preflight, not a default) and is allowed too.
HITS=0
for f in $ENTRYPOINTS; do
  if /usr/bin/grep -nE "^[[:space:]]*(SIM|DEVICE|DEV)=.*$RESERVED" "$f" >/dev/null 2>&1; then
    fail "$f assigns the reserved UDID as a device default"
    HITS=$((HITS+1))
  fi
done
[ "$HITS" -eq 0 ] && ok "$(echo $ENTRYPOINTS | wc -w | tr -d ' ') entrypoints, 0 bespoke defaults"
# The scan must be able to fail, or it is decoration (a vacuous guard reads
# exactly like a clean tree). Prove it on a synthetic line.
printf 'SIM=%s\n' "$RESERVED" > /tmp/reserved-sim-strawman.sh
if /usr/bin/grep -nE "^[[:space:]]*(SIM|DEVICE|DEV)=.*$RESERVED" /tmp/reserved-sim-strawman.sh >/dev/null 2>&1; then
  ok "strawman: the scan does fire on a reintroduced default"
else
  fail "the scan cannot detect a reintroduced default — it proves nothing"
fi
rm -f /tmp/reserved-sim-strawman.sh

echo "6. every entrypoint sources the shared guard"
for f in $ENTRYPOINTS; do
  /usr/bin/grep -q "reserved-sim-guard.sh" "$f" \
    && ok "$(basename "$f")" \
    || fail "$f does not source reserved-sim-guard.sh"
done

echo "7. no entrypoint filters the reserved set with a SCALAR"
# The shape that let this break: `grep -v "$BL_RESERVED_SIM"` excludes exactly
# one UDID, so a second protected device walks straight through it. The variable
# no longer exists; naming it is now the defect, and so is any bespoke pick that
# reimplements the filter instead of calling bl_default_shoot_sim.
SCALARS=0
for f in $ENTRYPOINTS scripts/ios_native_gate.sh tools/reserved-sim-guard.sh; do
  if /usr/bin/grep -n 'BL_RESERVED_SIM[^S]' "$f" >/dev/null 2>&1; then
    fail "$f filters on the retired SCALAR BL_RESERVED_SIM"
    SCALARS=$((SCALARS+1))
  fi
done
[ "$SCALARS" -eq 0 ] && ok "0 scalar filters across $(echo $ENTRYPOINTS | wc -w | tr -d ' ') entrypoints + the gate + the guard"
printf 'grep -v "$BL_RESERVED_SIM"\n' > /tmp/reserved-sim-scalar-strawman.sh
if /usr/bin/grep -n 'BL_RESERVED_SIM[^S]' /tmp/reserved-sim-scalar-strawman.sh >/dev/null 2>&1; then
  ok "strawman: the scalar scan does fire"
else
  fail "the scalar scan cannot detect a scalar filter — it proves nothing"
fi
rm -f /tmp/reserved-sim-scalar-strawman.sh

echo "8. the override cannot UN-PROTECT a built-in reserved device"
# This is the whole of the 2026-09-18 incident in one assertion. Under the old
# replacing override, naming one of Alex's devices unprotected the other, so the
# picker handed it out — "protect this too" and "stop protecting that" were the
# same export. Additive means there is no spelling of the second.
for pair in "$RESERVED2:$RESERVED" "$RESERVED:$RESERVED2"; do
  NAMED=${pair%%:*}; OTHER=${pair##*:}
  ( BAINLUCK_RESERVED_SIMULATOR="$NAMED" . tools/reserved-sim-guard.sh
    bl_refuse_reserved_sim "$OTHER" selftest ) >/dev/null 2>&1
  [ $? -eq 7 ] \
    && ok "naming ${NAMED%%-*} leaves ${OTHER%%-*} protected" \
    || fail "naming ${NAMED%%-*} UN-PROTECTED ${OTHER%%-*} — the override is subtractive again"
done
# And the picker, which is where an un-protect actually does the damage.
for u in "$RESERVED" "$RESERVED2"; do
  P=$(BAINLUCK_RESERVED_SIMULATOR="$u" sh -c '. tools/reserved-sim-guard.sh; bl_default_shoot_sim')
  if [ -n "$P" ] && ( . tools/reserved-sim-guard.sh; bl_is_reserved_sim "$P" ); then
    fail "with $u named, the picker handed out reserved $P"
  else
    ok "with ${u%%-*} named, the picker returned ${P:-nothing}"
  fi
done

echo "9. the gate's preflight resolves a device and refuses both reserved ones"
# `scripts/ios_native_gate.sh` is the entrypoint that INSTALLS, so it is the one
# whose device resolution matters most — and it was the last place still holding
# its own copy of the constant. Its default was the literal name `iPhone 17`,
# which on 2026-09-18 matched both of Alex's devices and nothing else: exit 6 on
# every bare invocation, with the reserved pair offered as the disambiguation.
# These five outcomes are the contract; the preflight runs no xcodebuild.
gate() { bash scripts/ios_native_gate.sh preflight ${1:+"$1"} >/dev/null 2>&1; echo $?; }
gate_is() {  # gate_is <want> <arg-or-empty> <what>
  _got=$(gate "$2")
  [ "$_got" = "$1" ] && ok "$3 (exit $_got)" || fail "$3 — got exit $_got, want $1"
}
gate_is 0 ""                 "bare invocation resolves a device"
gate_is 0 "iPhone 17 Pro"    "a disposable name passes"
gate_is 6 "iPhone 17"        "an ambiguous name refuses"
gate_is 7 "$RESERVED"        "the first reserved udid is refused BY UDID"
gate_is 7 "$RESERVED2"       "the second reserved udid is refused BY UDID"
# The bare case must not be passing because it silently fell back to a NAME that
# happens to work; it must be the picker's udid, which is the unambiguous form.
GATE_DEST=$(bash scripts/ios_native_gate.sh preflight 2>/dev/null | sed -n "s/.*destination '\([^']*\)'.*/\1/p")
[ "$GATE_DEST" = "$(. tools/reserved-sim-guard.sh; bl_default_shoot_sim)" ] \
  && ok "the bare default IS the shared picker's udid, not a name" \
  || fail "the bare default is '$GATE_DEST', not the shared picker's udid"

echo "10. no entrypoint resolves a device with a pick of its own"
# 🔴 THE SHAPE ASSERTIONS 5, 6 AND 7 ALL MISS. `tools/native-gates.sh` held
#
#     SIMLINE=$(xcrun simctl list devices available | grep -E '^ +iPhone ' | head -1)
#
# which hardcodes no UDID (5 clean), and — before today — sourced no guard and
# named no scalar (6 and 7 had nothing to read, because the file was not in the
# list). It picked the first iPhone `simctl` happened to print, in the one tool
# that installs. Safe on 2026-09-18 only because the disposable is the oldest
# device on this machine; one `simctl delete` away from installing onto Alex's.
#
# So the rule is not "do not hardcode a UDID" — it is that ONE function resolves
# a device for the whole rig. A second picker is a second policy, and a second
# policy is the bug, whatever devices it happens to return today.
#
# THE PREDICATE IS `head`, NOT `simctl`, AND THAT IS DELIBERATE. My first form
# here was "lists devices and then pipes to head/sed/awk", and it fired on
# `native-uitest.sh` and `ios_native_gate.sh`, both of which are CORRECT: they
# list devices to turn a UDID the caller already chose into a display name, and
# to refuse an ambiguous NAME. Taking the FIRST device is what "choosing" looks
# like; reading a device you were handed is not. A guard that fires on the
# innocent case gets deleted by the next person, so it has to tell them apart.
# Line continuations are joined first — the pick can be written across lines.
PICKERS=0
for f in $ENTRYPOINTS scripts/ios_native_gate.sh; do
  if /usr/bin/sed -e :a -e '/\\$/N; s/\\\n//; ta' "$f" \
     | /usr/bin/grep -qE 'simctl list devices.*\| *head'; then
    fail "$f takes the FIRST device itself instead of calling bl_default_shoot_sim"
    PICKERS=$((PICKERS+1))
  fi
done
[ "$PICKERS" -eq 0 ] && ok "$(echo $ENTRYPOINTS | wc -w | tr -d ' ') entrypoints + the gate, 0 bespoke pickers"
# The control. A scan that cannot fail reads exactly like a clean tree, and this
# one is scanning for an idiom rather than a constant, so it is the easier of
# the two to write inert. The strawman is the deleted line, verbatim.
printf 'SIMLINE=$(xcrun simctl list devices available | grep -E "iPhone " | head -1)\n' \
  > /tmp/reserved-sim-picker-strawman.sh
if /usr/bin/grep -qE 'simctl list devices.*\| *head' /tmp/reserved-sim-picker-strawman.sh; then
  ok "strawman: the picker scan does fire on a reintroduced pick"
else
  fail "the picker scan cannot detect a bespoke pick — it proves nothing"
fi
rm -f /tmp/reserved-sim-picker-strawman.sh

echo "11. every rig tool that drives a simulator is IN the list above"
# THE ASSERTION THE OTHER TEN CANNOT MAKE. Every one of them iterates
# $ENTRYPOINTS, so a tool missing from that string is not judged clean — it is
# not judged at all, and the run prints the same "ok" either way. That is how
# `native-gates.sh` (2026-09-18) and `native-firstcard.sh` (2026-09-19) both sat
# unguarded under a green selftest. So the list stops being the authority on who
# is covered: the filesystem is. A tool that calls `simctl` drives a device, and
# a tool that drives a device is in scope, whether or not anyone remembered it.
UNLISTED=0
for f in tools/native*.sh; do
  [ -f "$f" ] || continue
  /usr/bin/grep -q "simctl" "$f" || continue
  case " $ENTRYPOINTS " in
    *" $f "*) ;;
    *) fail "$f drives a simulator and is NOT in ENTRYPOINTS — nothing above judged it"
       UNLISTED=$((UNLISTED+1)) ;;
  esac
done
[ "$UNLISTED" -eq 0 ] && ok "every simctl-driving tool under tools/ is judged by this file"
# The control. This scan's failure mode is silence, exactly like the gap it
# closes, so it has to be shown firing on a tool that is deliberately absent.
printf '#!/bin/sh\nxcrun simctl boot "$1"\n' > tools/native-zz-strawman.sh
case " $ENTRYPOINTS " in
  *" tools/native-zz-strawman.sh "*) fail "the strawman is in the list; the control proves nothing" ;;
  *) if /usr/bin/grep -q "simctl" tools/native-zz-strawman.sh; then
       ok "strawman: an unlisted simctl tool is detectable"
     else
       fail "the scan cannot see an unlisted simctl tool — it proves nothing"
     fi ;;
esac
rm -f tools/native-zz-strawman.sh

echo "12. no entrypoint aims at the literal target 'booted'"
# `simctl <verb> booted` is a device selector that resolves to whatever is
# running, so it reads as "no device argument" while being one. It passes
# assertions 5, 7 and 10 — it hardcodes no UDID, names no scalar, and takes no
# `head` of a device list — and it is precisely how native-firstcard.sh came to
# point at Alex's phone. The shared picker is the only sanctioned resolution.
BOOTED=0
for f in $ENTRYPOINTS scripts/ios_native_gate.sh; do
  if /usr/bin/grep -qE 'simctl +[a-z_]+ +booted' "$f"; then
    fail "$f targets the literal 'booted' instead of a resolved UDID"
    BOOTED=$((BOOTED+1))
  fi
done
[ "$BOOTED" -eq 0 ] && ok "$(echo $ENTRYPOINTS | wc -w | tr -d ' ') entrypoints + the gate, 0 aimed at 'booted'"
printf 'xcrun simctl launch booted com.example\n' > /tmp/reserved-sim-booted-strawman.sh
if /usr/bin/grep -qE 'simctl +[a-z_]+ +booted' /tmp/reserved-sim-booted-strawman.sh; then
  ok "strawman: the 'booted' scan does fire"
else
  fail "the 'booted' scan cannot detect a literal target — it proves nothing"
fi
rm -f /tmp/reserved-sim-booted-strawman.sh

echo
if [ "$FAILED" -eq 0 ]; then echo "RESERVED-SIM GUARD SELFTEST: CLEAN"; exit 0; fi
echo "RESERVED-SIM GUARD SELFTEST: $FAILED FAILED" >&2
exit 1
