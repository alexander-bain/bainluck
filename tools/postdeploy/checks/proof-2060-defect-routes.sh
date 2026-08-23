#!/usr/bin/env bash
# UX-P122 item B — post-deploy proof for #2060 (UX-P117, `program/ux-104`).
#
# ## Why this file exists
#
# `program/ux-104` merged and deployed on 2026-08-22, and the harness had **no
# proof for it at all**. Five scripts, four branches — 101, 102, 103, 105 — and
# a hole where the branch in the middle should be. `run-all.sh` printed a clean
# summary over that hole, which is the failure mode the harness was built to
# prevent, reproduced by the harness itself: a set of green rows is read as
# "everything is verified", and nothing in it says which branches it does not
# cover. A harness that silently omits a branch is worse than one nobody runs.
#
# ## What #2060 actually shipped, and which half is provable without Alex
#
# UX-P117 measured this on production 2026-08-21 and it is the whole point:
#
#     ranking_judgments                                88 rows
#       carrying `label_metadata.fixable_interest`      0
#       label IN (bad, kill) WITH >= 1 reason_tag      71
#       ...of those, routed to a defect cluster         0
#
# `/fixable-interest/clusters` had returned `[]` for the entire life of the
# store. `defect_route()` fixed that FORWARD ONLY — no stored row was rewritten
# (the backfill is #2094). So the routing half of #2060 cannot be proven by
# looking at the corpus; it can only be proven by a row written AFTER the
# deploy, and only Alex writes those.
#
# That splits the proof cleanly, and the split is the design:
#
#   **PROVABLE NOW** — the gold meter (item 4) and the rails' reachability.
#     The meter's substantive claim is that its day bucket is PACIFIC, not UTC,
#     because a UTC day rolls over at 5pm PT and Alex labels in the evening. That
#     is a DISCRIMINATING assertion whenever the two buckets disagree, and today
#     they do: one real row at `2026-08-20 00:08Z` files as 08-19 Pacific, so the
#     corpus is 7 Pacific days and 6 UTC days. The endpoint must say 7. A `distinct_days`
#     of 6 would be the exact bug item 4 was written against, and this check
#     would catch it.
#
#   **GATED ON A WRITE** — the defect route itself. Zero eligible rows have been
#     written since deploy, so every routing assertion reports UNKNOWN with its
#     denominator and names what discharges it. It never reports PASS over an
#     empty population (gotcha #53), and it never reports FAIL either: "nobody
#     has labelled anything since Saturday" is not a defect in `defect_route`.
#
# ## The routable tag set is IMPORTED, never retyped
#
# `label_reasons.py` exists because its first draft shipped a second fold table
# that disagreed with the canonical one in three places, inside twenty lines of
# a comment condemning exactly that. A proof script that hard-codes the routable
# tags would be the third copy, and the one whose drift nothing detects — it
# would keep passing precisely when the table it claims to verify had changed.
# So the SQL predicate below is BUILT at run time from `REASON_FIX_TYPE`,
# `NEGATIVE_LABELS` and `REASON_TAG_ALIASES` as the deployed code defines them.
#
#   tools/postdeploy/checks/proof-2060-defect-routes.sh [--force|--self-test]

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../lib.sh"

# `--self-test` drives `verdict-2060.py` over synthetic fixtures and asserts
# every branch, including the ones production cannot currently reach. It takes
# no network and no database, so it is the only part of this file that stays
# runnable when the corpus is empty — which is exactly when the routing
# assertions are unverifiable and most likely to rot.
if [ "${1:-}" = "--self-test" ]; then
  exec python3 "$HERE/selftest-2060.py"
fi

REF="${REF:-program/ux-104}"
PROG_OUT=/tmp/proof-2060-progress.json
CLUS_OUT=/tmp/proof-2060-clusters.json
REPAIR_OUT=/tmp/proof-2060-repair.json
DAYS_OUT=/tmp/proof-2060-days.json
ROWS_OUT=/tmp/proof-2060-rows.json

hdr "#2060 — native labelling: defect routes + gold meter ($REF)"

if [ "${1:-}" != "--force" ]; then
  require_deployed "$REF"; rc=$?
  [ $rc -ne 0 ] && exit $rc
else
  say "   --force: deploy gate SKIPPED (this is a baseline read, not a proof)"
fi

if [ -z "${ADMIN_TOKEN:-}" ]; then
  verdict "#2060" "UNKNOWN — ADMIN_TOKEN unset; every endpoint here is admin-only"
  exit $RC_TRANSPORT
fi

# ── the deploy cutoff, derived rather than typed ─────────────────────────────
#
# "Post-deploy" needs a timestamp, and a hand-written date would be wrong the
# next time this branch's merge is re-dated. The first commit on the DEPLOYED
# history that contains $REF is the earliest moment the code could have been
# running; its committer date is the cutoff. Anchored on the deployed commit,
# not on `origin/master`, because master moves under this script.
LIVE="$(deployed_sha)"
FIRST_ON_MASTER="$(git -C "$REPO_ROOT" rev-list --ancestry-path "$REF..$LIVE" 2>/dev/null | tail -1)"
if [ -z "$FIRST_ON_MASTER" ]; then
  verdict "#2060" "UNKNOWN — could not locate the merge of $REF into the deployed history"
  exit $RC_UNKNOWN
fi
CUTOFF="$(git -C "$REPO_ROOT" log -1 --format=%cI "$FIRST_ON_MASTER")"
say "   $REF merged at $FIRST_ON_MASTER ($CUTOFF) — the post-deploy cutoff"

adm() {  # adm <path> <outfile>
  local code
  code=$(curl -s --max-time 90 -o "$2" -w '%{http_code}' \
    -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API$1")
  [ "$code" = "200" ] && return 0
  say "   HTTP $code on GET $1"
  return 1
}

dbq() {  # dbq <sql-file> <outfile>
  local code
  python3 - "$1" > /tmp/proof-2060-body.json <<'PY'
import json, sys
print(json.dumps({"sql": " ".join(open(sys.argv[1]).read().split()), "limit": 200}))
PY
  code=$(curl -s --max-time 90 -o "$2" -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
    --data @/tmp/proof-2060-body.json "$BAINLUCK_API/api/admin/db-query")
  [ "$code" = "200" ] && return 0
  say "   HTTP $code on db-query"
  return 1
}

# ── build the routable predicate FROM THE SHIPPED SOURCE ─────────────────────
python3 - "$CUTOFF" > /tmp/proof-2060-rows.sql <<'PY'
import os, sys

sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "backend"))
from app.utils.discover_reason_tags import REASON_TAG_ALIASES
from app.utils.label_reasons import NEGATIVE_LABELS, REASON_FIX_TYPE

cutoff = sys.argv[1]

# Canonical routable tags, PLUS every alias that folds onto one. A row written
# before the alias landed stores `boring`; `reason_fix_type` canonicalises on
# read, so both spellings are genuinely routable and the predicate must accept
# both or it will under-count its own denominator.
routable = sorted(
    set(REASON_FIX_TYPE)
    | {raw for raw, canon in REASON_TAG_ALIASES.items() if canon in REASON_FIX_TYPE}
)
negatives = sorted(NEGATIVE_LABELS)

# Aliases that a POST-DEPLOY row must never store: the canonicaliser runs on
# every write now, so an alias appearing on a fresh row means the write path
# skipped it.
stale_spellings = sorted(
    raw for raw, canon in REASON_TAG_ALIASES.items() if raw != canon
)


def lit(vals):
    return ",".join("'" + v.replace("'", "''") + "'" for v in vals)


# No `;` anywhere and no `grant` as a word: `assert_read_only` is a substring
# check over the whole statement, literals and comments included.
print(
    f"""
SELECT
  count(*) FILTER (WHERE created_at > '{cutoff}') AS post_rows,
  count(*) FILTER (WHERE created_at > '{cutoff}'
                     AND lower(label) IN ({lit(negatives)})
                     AND reason_tags::text[] && array[{lit(routable)}]) AS post_eligible,
  count(*) FILTER (WHERE created_at > '{cutoff}'
                     AND lower(label) IN ({lit(negatives)})
                     AND reason_tags::text[] && array[{lit(routable)}]
                     AND label_metadata -> 'fixable_interest' ->> 'fix_type' IS NOT NULL) AS post_routed,
  count(*) FILTER (WHERE created_at > '{cutoff}'
                     AND label_metadata -> 'fixable_interest' ->> 'derived_from' = 'reason_tags') AS post_derived_ok,
  count(*) FILTER (WHERE created_at > '{cutoff}'
                     AND (label_metadata -> 'fixable_interest' -> 'create_issue_candidate')::text = 'true') AS post_auto_candidate,
  count(*) FILTER (WHERE created_at > '{cutoff}'
                     AND reason_tags::text[] && array[{lit(stale_spellings)}]) AS post_stale_spelling,
  count(*) AS all_rows,
  count(*) FILTER (WHERE label_metadata ? 'fixable_interest') AS all_with_fi
FROM ranking_judgments
""".strip()
)
PY
rc=$?
if [ $rc -ne 0 ]; then
  verdict "#2060" "UNKNOWN — could not build the predicate from app.utils.label_reasons (rc=$rc)"
  exit $RC_UNKNOWN
fi

cat > /tmp/proof-2060-days.sql <<'SQL'
SELECT
  count(DISTINCT to_char(timezone('America/Los_Angeles', created_at),'YYYY-MM-DD')) AS pt_days,
  count(DISTINCT to_char(created_at,'YYYY-MM-DD')) AS utc_days,
  count(*) AS total
FROM ranking_judgments
SQL

dbq /tmp/proof-2060-rows.sql "$ROWS_OUT" || { verdict "#2060" "UNKNOWN — row census unreachable"; exit $RC_TRANSPORT; }
dbq /tmp/proof-2060-days.sql "$DAYS_OUT" || { verdict "#2060" "UNKNOWN — day census unreachable"; exit $RC_TRANSPORT; }
adm "/api/admin/ranking-judgments/progress" "$PROG_OUT" || { verdict "#2060" "UNKNOWN — /progress unreachable"; exit $RC_TRANSPORT; }
adm "/api/admin/ranking-judgments/fixable-interest/clusters" "$CLUS_OUT" || { verdict "#2060" "UNKNOWN — /fixable-interest/clusters unreachable"; exit $RC_TRANSPORT; }
adm "/api/admin/ranking-judgments/repair-clusters" "$REPAIR_OUT" || { verdict "#2060" "UNKNOWN — /repair-clusters unreachable"; exit $RC_TRANSPORT; }

CUTOFF="$CUTOFF" python3 "$HERE/verdict-2060.py" "$ROWS_OUT" "$DAYS_OUT" "$PROG_OUT" "$CLUS_OUT" "$REPAIR_OUT"
rc=$?
echo "EXIT CODE: $rc"
exit $rc
