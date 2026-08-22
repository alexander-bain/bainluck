#!/usr/bin/env bash
# UX-P119 item 3 — `/tmp/cal.json` baseline vs a fresh re-curl.
#
# ## What this is for
#
# UX-P118 shipped a DISCLOSURE on the calibration page, not a change to any
# number. So the post-deploy question is precisely: **did any published figure
# move?** If one did, the disclosure is describing a different payload from the
# one it was derived against, and the whole point of that work — "every sentence
# is computed from the SAME inputs the number is computed from" — is void.
#
# It is also the cheap way to tell a real regression from the two things that
# routinely masquerade as one:
#
#   - `/api/calibration` **503s for 1–4 minutes after every release** and then
#     self-heals. `api_get` retries, so a release-window 503 costs a wait, not a
#     false alarm.
#   - The payload is regenerated on a schedule, so `generated_at` and the row
#     counts move on their own. Movement is REPORTED, never asserted against;
#     the only hard check is on the SHAPE (keys present, categories present),
#     because a missing key is ours and a drifting count is the world's.
#
# Baseline capture and comparison are the same script, so the baseline cannot be
# taken with a different query than the comparison uses.
#
#   tools/postdeploy/compare-calibration-baseline.sh --capture   # before deploy
#   tools/postdeploy/compare-calibration-baseline.sh             # after deploy

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

BASELINE="${CAL_BASELINE:-/tmp/cal.json}"
FRESH="${CAL_FRESH:-/tmp/cal-recurl.json}"

if [ "${1:-}" = "--capture" ]; then
  hdr "calibration baseline capture -> $BASELINE"
  api_get "/api/calibration" "$BASELINE" || { verdict "baseline" "UNKNOWN — unreachable"; exit $RC_TRANSPORT; }
  python3 -c "
import json
d = json.load(open('$BASELINE'))
print('   generated_at:', d.get('generated_at'))
print('   buckets:', len(d.get('buckets') or []), ' by_category:', len(d.get('by_category') or []))
print('   population_version:', d.get('population_version'))
print('   fingerprint:', d.get('population_predicate_fingerprint'))
"
  say "   captured. Re-run WITHOUT --capture after the deploy."
  exit 0
fi

hdr "calibration baseline vs re-curl"

if [ ! -s "$BASELINE" ]; then
  verdict "calibration" "UNKNOWN — no baseline at $BASELINE (run with --capture first)"
  exit $RC_UNKNOWN
fi

api_get "/api/calibration" "$FRESH" || { verdict "calibration" "UNKNOWN — re-curl failed"; exit $RC_TRANSPORT; }

python3 - "$BASELINE" "$FRESH" <<'PY'
import json, sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))

print(f"   baseline generated_at: {a.get('generated_at')}")
print(f"   fresh    generated_at: {b.get('generated_at')}")
print(f"   population_version:    {a.get('population_version')} -> {b.get('population_version')}")
print(f"   predicate fingerprint: {a.get('population_predicate_fingerprint')} -> "
      f"{b.get('population_predicate_fingerprint')}")

fails, notes = [], []

# --- SHAPE: ours. A key that disappears is a regression, always. -------------
missing = sorted(set(a.keys()) - set(b.keys()))
added = sorted(set(b.keys()) - set(a.keys()))
if missing:
    fails.append(f"top-level keys DISAPPEARED: {missing}")
if added:
    notes.append(f"top-level keys added: {added}")

for k in ("buckets", "by_category"):
    if not (b.get(k) or []):
        fails.append(f"`{k}` is empty in the fresh payload (baseline had "
                     f"{len(a.get(k) or [])})")

# --- CATEGORY COVERAGE: a published category vanishing is ours ---------------
acats = {c["category"]: c for c in (a.get("by_category") or []) if c.get("category")}
bcats = {c["category"]: c for c in (b.get("by_category") or []) if c.get("category")}
gone = sorted(set(acats) - set(bcats))
new = sorted(set(bcats) - set(acats))
if gone:
    fails.append(f"published categories DISAPPEARED: {gone}")
if new:
    notes.append(f"published categories appeared: {new}")

# --- VALUES: the world's. Reported with a magnitude, never asserted. ---------
moved = []
for name in sorted(set(acats) & set(bcats)):
    ea, eb = acats[name].get("ece"), bcats[name].get("ece")
    na, nb = acats[name].get("n"), bcats[name].get("n")
    if ea is None or eb is None:
        moved.append((name, ea, eb, na, nb, None))
        continue
    d = round(eb - ea, 3)
    if abs(d) >= 0.05 or na != nb:
        moved.append((name, ea, eb, na, nb, d))

print(f"   published categories: {len(acats)} -> {len(bcats)}   moved: {len(moved)}")
if moved:
    print("   ── movement (ECE pp, n) ──")
    for name, ea, eb, na, nb, d in moved[:40]:
        dd = "n/a" if d is None else f"{d:+.2f}"
        print(f"   {name:34} {str(ea):>6} -> {str(eb):<6} ({dd})   n {na} -> {nb}")
    if len(moved) > 40:
        print(f"   … and {len(moved) - 40} more")

for n in notes:
    print("   note: " + n)

if fails:
    print("calibration: FAIL")
    for f in fails:
        print("   - " + f)
    raise SystemExit(1)

if a.get("generated_at") == b.get("generated_at"):
    print("calibration: PASS — identical payload (same `generated_at`); the cached")
    print("             producer has not re-run, so nothing could have moved.")
else:
    print("calibration: PASS (shape) — every baseline key and every published category")
    print("             is still present. Value movement above is the producer")
    print("             re-running, not a regression, and is reported for the reader")
    print("             to judge rather than asserted away.")
PY
rc=$?
echo "EXIT CODE: $rc"
exit $rc
