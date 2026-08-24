"""The #2060 verdict, as a pure function of five JSON documents.

Split out of `proof-2060-defect-routes.sh` for one reason: **production can only
ever exercise the branch production is in.** Today the corpus has zero
post-deploy rows, so every routing assertion in here is unreachable from a live
run — and an unreachable assertion is indistinguishable from a deleted one. The
same precedent that produced `tools/push-verdict/verdict-core.sql`: run the real
decision logic over synthetic inputs and assert every branch, because a check
whose FAIL path has never fired is a check nobody has tested.

`proof-2060-defect-routes.sh --self-test` drives exactly this file over ten
fixtures. It takes no network and no database.

Inputs, in argv order: the row census, the day census, `/progress`,
`/fixable-interest/clusters`, `/repair-clusters`. `CUTOFF` comes from the env
because it is provenance for the message, not an input to any decision.

Exit codes follow the harness vocabulary: PASS(0) FAIL(1) UNKNOWN(3).
"""
import json, os, sys


def one(path):
    d = json.load(open(path))
    cols = d.get("columns") or []
    rows = d.get("rows") or []
    if not rows:
        return {}
    return dict(zip(cols, rows[0]))


rows = one(sys.argv[1])
days = one(sys.argv[2])
prog = json.load(open(sys.argv[3]))
clus = json.load(open(sys.argv[4]))
repair = json.load(open(sys.argv[5]))
cutoff = os.environ["CUTOFF"]

fails: list[str] = []
unproven: list[str] = []

print("")
print("   ── the corpus ──")
print(f"   rows total {rows.get('all_rows')} · carrying fixable_interest {rows.get('all_with_fi')}")
print(f"   written after {cutoff}: {rows.get('post_rows')}")
print(f"     ...negative label with a routable tag: {rows.get('post_eligible')}")
print(f"     ...of those, routed:                   {rows.get('post_routed')}")

# ── PROVABLE NOW: the gold meter's Pacific day bucket (item 4) ───────────────
pt, utc = days.get("pt_days"), days.get("utc_days")
reported = prog.get("distinct_days")
print("")
print("   ── gold meter (item 4) ──")
print(f"   SQL: {pt} Pacific days · {utc} UTC days · {days.get('total')} rows")
print(f"   /progress: distinct_days={reported} total={prog.get('total')} "
      f"timezone={prog.get('timezone')!r} streak={prog.get('streak')}")

if prog.get("timezone") != "America/Los_Angeles":
    fails.append(f"/progress reports timezone={prog.get('timezone')!r}, not America/Los_Angeles")

if prog.get("total") != days.get("total"):
    fails.append(f"/progress total {prog.get('total')} != {days.get('total')} rows in the table")

if pt == utc:
    unproven.append(
        f"the Pacific-vs-UTC bucket cannot be discriminated today: both are {pt}. "
        f"The endpoint agreeing with Pacific proves nothing while the two agree."
    )
    if reported != pt:
        fails.append(f"/progress distinct_days={reported} matches neither bucket ({pt})")
elif reported == pt:
    print(f"   ✓ distinct_days={reported} is the PACIFIC bucket, and it differs from UTC ({utc}) "
          f"— the item-4 claim is discriminated and holds")
elif reported == utc:
    fails.append(
        f"/progress distinct_days={reported} is the UTC bucket (Pacific is {pt}) — "
        f"exactly the bug item 4 was written against: a UTC day rolls over at 5pm PT, "
        f"so an evening session files as tomorrow"
    )
else:
    fails.append(f"/progress distinct_days={reported} is neither bucket (PT {pt}, UTC {utc})")

for leg in ("total_target", "daily_target", "spread_target", "streak", "first_day", "last_day"):
    if leg not in prog:
        fails.append(f"/progress is missing the meter leg {leg!r}")

# ── PROVABLE NOW: the rails are reachable ───────────────────────────────────
print("")
print("   ── the defect rails ──")
print(f"   /fixable-interest/clusters: total={clus.get('total')} status={clus.get('status')!r}")
print(f"   /repair-clusters:           total={repair.get('total')}")
for name, payload in (("fixable-interest/clusters", clus), ("repair-clusters", repair)):
    if "clusters" not in payload:
        fails.append(f"/{name} did not return a `clusters` key")

# ── GATED ON A WRITE: the defect route itself ───────────────────────────────
eligible = rows.get("post_eligible") or 0
routed = rows.get("post_routed") or 0
print("")
print("   ── the defect route (item 1) ──")
if eligible == 0:
    unproven.append(
        f"ZERO eligible rows written since the deploy ({rows.get('post_rows')} rows of any kind). "
        f"`defect_route` is forward-only by design — #2094 owns the backfill — so the "
        f"{rows.get('all_with_fi')}-of-{rows.get('all_rows')} coverage below is the PRE-fix corpus and "
        f"says nothing about the fix. DISCHARGED BY: Alex tapping Bad + one reason chip "
        f"on the native labelling surface once. Then re-run."
    )
    print("   UNPROVEN — no input yet. This is not a FAIL: an empty population is a")
    print("   response shape, not a fact about the code (gotcha #53).")
else:
    print(f"   {routed}/{eligible} eligible post-deploy rows carry a fix_type")
    if routed != eligible:
        fails.append(
            f"only {routed} of {eligible} eligible post-deploy rows routed — "
            f"`defect_route` is applied inside `structured_label_metadata`, which BOTH "
            f"write paths share, so a partial rate means one path bypasses the envelope"
        )
    if (rows.get("post_derived_ok") or 0) != routed:
        fails.append(
            f"{routed} routed rows but {rows.get('post_derived_ok')} carry "
            f"derived_from='reason_tags' — provenance must distinguish a chip tap from a "
            f"human ReviewTab choice"
        )
    if (rows.get("post_auto_candidate") or 0) > 0:
        fails.append(
            f"{rows.get('post_auto_candidate')} post-deploy rows carry "
            f"create_issue_candidate=true — that flag means a HUMAN decided, and inferring "
            f"it is the 71-auto-candidates cried-wolf failure the route was written to avoid"
        )
    if clus.get("total", 0) == 0:
        fails.append(
            f"{routed} rows routed but /fixable-interest/clusters is still empty — "
            f"the rail that #2060 exists to fill is still not filling"
        )

stale = rows.get("post_stale_spelling") or 0
if rows.get("post_rows"):
    print(f"   post-deploy rows storing a non-canonical spelling: {stale}")
    if stale:
        fails.append(
            f"{stale} post-deploy rows store an un-folded alias (e.g. `boring` for "
            f"`low_stakes`) — the canonicaliser runs on every write, so this means a "
            f"write path skipped it and one complaint is being tallied under two names"
        )

print("")
for u in unproven:
    print("   ⚠️ UNPROVEN: " + u)

if fails:
    print("")
    print("#2060: FAIL")
    for f in fails:
        print("   - " + f)
    raise SystemExit(1)

if unproven:
    print("")
    print("#2060: UNKNOWN — everything checkable without a fresh label PASSES (the gold")
    print("        meter's Pacific bucket, the meter legs, both defect rails reachable),")
    print("        but the routing half has had no input and is NOT claimed as passing.")
    raise SystemExit(3)

print("")
print("#2060: PASS — gold meter on the Pacific bucket, both rails reachable, and every")
print("       eligible post-deploy row routed to a defect cluster.")
