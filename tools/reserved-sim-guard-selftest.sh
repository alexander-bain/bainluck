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
set -u
cd "$(dirname "$0")/.."
RESERVED=76D961F0-8575-479F-ABCE-652D8A79DBF9
FAILED=0
ok()   { echo "  ok   — $1"; }
fail() { echo "  FAIL — $1" >&2; FAILED=$((FAILED+1)); }

# The entrypoints that select or accept a simulator. Adding a rig tool that
# takes a device means adding it here.
ENTRYPOINTS="tools/native-shoot.sh tools/native_live_shoot.sh tools/native-g1-shoot.sh tools/native-uitest.sh tools/native-walk.sh"

echo "1. the guard refuses the reserved device with exit 7"
( . tools/reserved-sim-guard.sh; bl_refuse_reserved_sim "$RESERVED" selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "exit 7" || fail "expected exit 7"

echo "2. the guard passes a disposable device"
( . tools/reserved-sim-guard.sh; bl_refuse_reserved_sim 00000000-0000-0000-0000-000000000000 selftest ) >/dev/null 2>&1
[ $? -eq 0 ] && ok "exit 0" || fail "a non-reserved udid must not be refused"

echo "3. BAINLUCK_RESERVED_SIMULATOR moves what is protected"
( BAINLUCK_RESERVED_SIMULATOR=DEADBEEF . tools/reserved-sim-guard.sh
  bl_refuse_reserved_sim "$RESERVED" selftest ) >/dev/null 2>&1
[ $? -eq 0 ] && ok "override honoured" || fail "override not honoured"
( BAINLUCK_RESERVED_SIMULATOR=DEADBEEF . tools/reserved-sim-guard.sh
  bl_refuse_reserved_sim DEADBEEF selftest ) >/dev/null 2>&1
[ $? -eq 7 ] && ok "override still protects" || fail "override protected nothing"

echo "4. the resolved default is never the reserved device"
. tools/reserved-sim-guard.sh
PICK=$(bl_default_shoot_sim)
if [ -z "$PICK" ]; then
  ok "no iPhone on this machine — vacuously clean, and the callers :? on it"
elif [ "$PICK" = "$RESERVED" ]; then
  fail "bl_default_shoot_sim returned the RESERVED device"
else
  ok "picked $PICK"
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

echo
if [ "$FAILED" -eq 0 ]; then echo "RESERVED-SIM GUARD SELFTEST: CLEAN"; exit 0; fi
echo "RESERVED-SIM GUARD SELFTEST: $FAILED FAILED" >&2
exit 1
