#!/usr/bin/env bash
# UX-P119 item 3 — a frozen pre-deploy baseline vs a fresh re-curl.
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
#   tools/postdeploy/compare-calibration-baseline.sh --capture --force  # overwrite
#   tools/postdeploy/compare-calibration-baseline.sh             # after deploy
#
# ## #2120 defect 1 — THE BASELINE OWNS ITS OWN DIRECTORY
#
# This script used to default to `/tmp/cal.json`, and so did two other tools in
# this repo — but those two `curl -o` into it while this one treats it as a
# FROZEN pre-deploy artifact. UX-P121 watched the collision report
# `calibration: FAIL — keys DISAPPEARED` against a payload that had not changed:
# a sibling tool had overwritten the baseline five seconds before the comparison
# read it, so the "baseline" was newer than the "fresh" fetch. The tell was an
# mtime, not a value, which is why it cost a cycle to see.
#
# So the baseline lives under `/tmp/cal-baseline/`, nothing else writes there,
# and `--capture` REFUSES to overwrite an existing baseline without `--force`.
# The refusal is the point: silently re-capturing is how a comparison ends up
# measuring a payload against itself and reporting PASS.
#
# ## #2120 defect 2 — THE DEGRADED WINDOW
#
# `/api/calibration` has tiers. A healthy answer carries `producer`, `staged` and
# `availability`; a DATED answer (last-good copy, previous population version)
# additionally carries `cache`, emitted only by the degraded-serving paths. So a
# baseline captured while the producer was stalled has a top-level key the
# healthy re-curl does not — and the shape check read that as
# `keys DISAPPEARED: ['cache']` and FAILED, on a payload that had RECOVERED.
#
# Two fixes, and they are different:
#   - `cache` is CONDITIONAL. Its coming and going is a note about which tier
#     answered, never a shape regression.
#   - if EITHER side is not `availability: fresh`, the value comparison cannot
#     answer the question this script exists to ask. A last-good copy did not
#     "not move"; it was not re-measured. That is UNKNOWN, not PASS.

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

BASELINE_DIR="${CAL_BASELINE_DIR:-/tmp/cal-baseline}"
BASELINE="${CAL_BASELINE:-$BASELINE_DIR/baseline.json}"
FRESH="${CAL_FRESH:-$BASELINE_DIR/recurl.json}"
STAMP="${CAL_BASELINE_STAMP:-$BASELINE.stamp}"
mkdir -p "$(dirname "$BASELINE")" "$(dirname "$FRESH")"

if [ "${1:-}" = "--capture" ]; then
  hdr "calibration baseline capture -> $BASELINE"
  if [ -s "$BASELINE" ] && [ "${2:-}" != "--force" ] && [ "${CAL_BASELINE_FORCE:-}" != "1" ]; then
    say "   REFUSING to overwrite an existing baseline."
    say "   existing: $(ls -l "$BASELINE" | awk '{print $6, $7, $8}')  ($BASELINE)"
    [ -s "$STAMP" ] && sed 's/^/   stamp: /' "$STAMP"
    say "   A baseline is a frozen pre-deploy artifact. Re-capturing it mid-run is"
    say "   how a comparison ends up measuring a payload against itself. Pass"
    say "   --force (or CAL_BASELINE_FORCE=1) if you really mean to re-take it."
    verdict "baseline" "UNKNOWN — refused (already captured)"
    exit $RC_UNKNOWN
  fi
  api_get "/api/calibration" "$BASELINE" || { verdict "baseline" "UNKNOWN — unreachable"; exit $RC_TRANSPORT; }
  # Stamp WHAT WAS DEPLOYED when the baseline was taken. Without it, a stale
  # baseline from a previous deploy is indistinguishable from this one's, and
  # the whole comparison silently answers a question nobody asked.
  {
    printf 'captured_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'repo_head=%s\n' "$(git -C "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    printf 'deployed_sha=%s\n' "$(deployed_sha 2>/dev/null || echo unknown)"
  } > "$STAMP"
  python3 -c "
import json
d = json.load(open('$BASELINE'))
print('   generated_at:', d.get('generated_at'))
print('   buckets:', len(d.get('buckets') or []), ' by_category:', len(d.get('by_category') or []))
print('   population_version:', d.get('population_version'))
print('   fingerprint:', d.get('population_predicate_fingerprint'))
print('   availability:', d.get('availability'), ' cache:', (d.get('cache') or {}).get('status', '—'))
"
  sed 's/^/   /' "$STAMP"
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

# --- #2120: THE DEGRADED WINDOW ---------------------------------------------
#
# `/api/calibration` serves tiers. Only the DEGRADED paths (`_degraded`,
# `_previous_version`) emit `cache`; every answer emits `producer`, `staged` and
# `availability`. So the set of top-level keys is a function of WHICH TIER
# answered, and comparing it as if it were a fixed schema turns a recovery into
# a FAIL — `keys DISAPPEARED: ['cache']` on a payload that got better.
#
# `cache` is therefore conditional. Anything else vanishing is still ours.
CONDITIONAL_KEYS = {"cache"}

def tier(d):
    av = d.get("availability")
    c = (d.get("cache") or {}).get("status")
    stalled = ((d.get("producer") or {}).get("stalled"))
    return av, c, stalled

av_a, cache_a, stall_a = tier(a)
av_b, cache_b, stall_b = tier(b)
print(f"   availability:          {av_a} -> {av_b}"
      f"   (cache {cache_a or '—'} -> {cache_b or '—'};"
      f" producer stalled {stall_a} -> {stall_b})")

# A dated copy did not "not move" — it was not re-measured. Value comparison
# across a degraded window answers a question nobody asked, so say UNKNOWN
# rather than manufacture a PASS or a FAIL out of it.
degraded_side = [
    name for name, av in (("baseline", av_a), ("fresh", av_b))
    if av not in (None, "fresh")
]

# --- SHAPE: ours, minus the keys the tier owns -------------------------------
missing = sorted(set(a.keys()) - set(b.keys()) - CONDITIONAL_KEYS)
added = sorted(set(b.keys()) - set(a.keys()) - CONDITIONAL_KEYS)
cond_moved = sorted(
    k for k in CONDITIONAL_KEYS if (k in a) != (k in b)
)
if missing:
    fails.append(f"top-level keys DISAPPEARED: {missing}")
if added:
    notes.append(f"top-level keys added: {added}")
if cond_moved:
    notes.append(
        f"tier-conditional keys changed presence: {cond_moved} — which serving "
        f"tier answered, not a shape regression"
    )

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

if degraded_side:
    print("calibration: UNKNOWN — served from a DEGRADED tier on the "
          + " and ".join(degraded_side) + " side")
    print(f"             availability {av_a} -> {av_b}. A dated last-good copy was")
    print("             not re-measured, so 'no movement' is not a finding about the")
    print("             numbers — it is a finding about which tier answered. The")
    print("             SHAPE checks above did pass. Re-run once availability is")
    print("             `fresh` on both sides.")
    raise SystemExit(3)

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
