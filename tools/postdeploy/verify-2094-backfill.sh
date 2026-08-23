#!/usr/bin/env bash
# UX-P119 item 3 — post-deploy verification for #2094 (UX-P118, `program/ux-105`).
#
# ## What this is verifying
#
# `POST /api/admin/repairs/label-defect-routes` re-runs `defect_route()` over
# `ranking_judgments` and writes `label_metadata.fixable_interest` where it is
# absent, so the 71 already-tagged negatives — **35 of them `stale`**, the most
# used tag at 40% of an 88-row corpus — stop being dropped complaints. Before it
# runs, `/fixable-interest/clusters` has returned an EMPTY LIST for the life of
# the store.
#
# ## Why the dry run is the interesting half, and why the cluster count is
#
# "71 rows routed" and "the cluster list is no longer empty" are DIFFERENT
# claims. `item_key` falls back to `item_type:market_id`, so N complaints about N
# distinct markets are **N clusters of one** — a routed backlog that still shows
# a reader nothing groupable. The dry run therefore projects the resulting
# cluster list through the route's OWN `_cluster_identity` / `_cluster_id`, and
# reports `projected_clusters` + `largest_cluster` so that is known BEFORE
# applying rather than hoped.
#
# This script is READ-ONLY by default: it runs `apply=false` and prints the
# census. `--apply` is a separate, explicit flag, and it re-reads the dry run
# afterwards so the before/after is one artifact.
#
#   tools/postdeploy/verify-2094-backfill.sh            # dry run + projection
#   tools/postdeploy/verify-2094-backfill.sh --apply    # commit, then re-census

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

REF="${REF:-program/ux-105}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

hdr "#2094 — defect-route backfill dry run ($REF)"

require_deployed "$REF"; rc=$?
[ $rc -ne 0 ] && exit $rc

DRY=/tmp/verify-2094-dry.json
api_post_admin "/api/admin/repairs/label-defect-routes?apply=false" "$DRY" || {
  verdict "#2094" "UNKNOWN — dry run did not return 200"
  head -c 400 "$DRY" 2>/dev/null; echo
  exit $RC_TRANSPORT
}

python3 - "$DRY" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
def g(k, default="?"): return c.get(k, default)
print("   ── dry-run census ──")
for k in ("negative_rows_total", "untagged_no_complaint", "tagged_negatives",
          "already_routed_left_alone", "unroutable_no_defect_tag", "writable"):
    print(f"   {k:28} {g(k)}")
print(f"   {'by_fix_type':28} {g('by_fix_type', {})}")
print(f"   {'projected_clusters':28} {g('projected_clusters')}   <- the claim that matters")
print(f"   {'largest_cluster':28} {g('largest_cluster')}")
if c.get("unroutable_ids"):
    print(f"   unroutable ids (first 50): {c['unroutable_ids']}")

w = c.get("writable")
pc = c.get("projected_clusters")
lc = c.get("largest_cluster")
if w in (None, 0):
    print("#2094: UNKNOWN — dry run plans 0 writes. Either the backfill already ran")
    print("        (check `already_routed_left_alone`) or no negative row carries a")
    print("        routable tag. An empty plan is not a success.")
    raise SystemExit(3)
print(f"#2094: DRY RUN OK — {w} rows writable, projecting {pc} clusters "
      f"(largest {lc}).")
if isinstance(pc, int) and isinstance(w, int) and pc == w:
    print("       ⚠️ projected_clusters == writable: every cluster would hold exactly")
    print("          ONE row. The list stops being empty but shows nothing groupable —")
    print("          that is the `item_type:market_id` fallback, and it is the reason")
    print("          this projection exists. Read it before applying.")
PY
rc=$?
echo "DRY RUN EXIT CODE: $rc"
[ $rc -ne 0 ] && exit $rc

if [ $APPLY -eq 0 ]; then
  say ""
  say "   read-only. Re-run with --apply to commit, once the projection above reads sane."
  exit 0
fi

hdr "#2094 — APPLYING"
LIVE=/tmp/verify-2094-apply.json
api_post_admin "/api/admin/repairs/label-defect-routes?apply=true" "$LIVE" || {
  verdict "#2094" "FAIL — apply did not return 200"
  head -c 400 "$LIVE"; echo
  exit $RC_FAIL
}
python3 -c "
import json
c = json.load(open('$LIVE'))
print('   applied:', c.get('applied'), ' written:', c.get('written', c.get('writable')))
print('   projected_clusters:', c.get('projected_clusters'), ' largest:', c.get('largest_cluster'))
"

# Idempotence: a second dry run must now plan ZERO writes. A repair that is not
# idempotent is a repair nobody can safely re-run, and the `label-store-converge`
# precedent this was built on states idempotence as part of its contract.
hdr "#2094 — re-census (idempotence)"
RE=/tmp/verify-2094-recensus.json
api_post_admin "/api/admin/repairs/label-defect-routes?apply=false" "$RE" || {
  verdict "#2094" "UNKNOWN — re-census did not return 200"; exit $RC_UNKNOWN; }
python3 - "$RE" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
w = c.get("writable")
print(f"   writable after apply: {w}   already_routed_left_alone: "
      f"{c.get('already_routed_left_alone')}")
if w:
    print(f"#2094: FAIL — {w} rows STILL writable after apply; the repair is not "
          f"idempotent or did not commit")
    raise SystemExit(1)
print("#2094: PASS — applied and idempotent (second dry run plans 0 writes)")
print("       NEXT: GET /api/admin/fixable-interest/clusters must now return a "
      "non-empty list.")
PY
rc=$?
echo "EXIT CODE: $rc"
exit $rc
