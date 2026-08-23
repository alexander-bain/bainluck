#!/usr/bin/env bash
# UX-P120 item 4 — turn Alex's post-capture notification tap into an instant
# fixed/broken verdict for #2109.
#
#   tools/push-verdict/run.sh                    # self-test, then the real verdict
#   FLOOR=2026-08-25 tools/push-verdict/run.sh   # certify a session on a later day
#   tools/push-verdict/run.sh --selftest-only
#   tools/push-verdict/run.sh --verdict-only
#
# ── WHY THIS IS NOT `SELECT count(*) FROM device_tokens WHERE platform='ios'` ──
#
# #2109's whole difficulty is that today the "fixed" state and the "still broken"
# state are BOTH zero rows — gotcha #53's empty-200 in table form. Three things
# follow, and each is a line of this script rather than a note in a doc:
#
#   1. The query ALWAYS returns exactly one row, because every counter is an
#      aggregate with a FILTER rather than a WHERE. A predicate that can return
#      no rows cannot distinguish "nothing to report" from "the check did not
#      run", which is the same shape as the four harness bugs UX-P119 found by
#      executing its own proofs.
#   2. `macos_control` is in the output on purpose. It is 2 today, and its job is
#      to make a zero legible: ios=0 alongside macos=2 is a real absence, while
#      ios=0 alongside macos=0 means the query is not seeing the table it thinks
#      it is.
#   3. There is a TIME FLOOR. Without it, the first ios row that ever lands
#      certifies every later session forever — scenario `2_stale` in
#      fixtures.sql exists to hold that line.
#
# ── THE SELF-TEST IS THE POINT ──
#
# The verdict ladder has six branches and production can only ever exercise the
# one it is in. `--selftest-only` runs the SAME `verdict-core.sql` over synthetic
# rows (a pure VALUES list — it never touches the table) and asserts all six.
# Scenarios `3_mislabeled` and `4_fixed` deliberately produce IDENTICAL counters;
# only the token-shape regex separates them, so a count-based check would call a
# broken push rail fixed.
#
# ── db-query TRAPS, ALL THREE MET WHILE BUILDING THIS ──
#
# `assert_read_only` (app/utils/sql_read_guard.py) is a substring check over the
# WHOLE statement, string literals and comments included. It refused this query
# three times:
#   - a `;` inside a verdict STRING     -> "Multi-statement queries not allowed"
#   - a `;` inside a `--` COMMENT       -> same
#   - the word "grant" in a verdict     -> "Only SELECT queries are allowed"
#                                          (\bGRANT\b, matched in prose)
# So: no semicolons anywhere, and no INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/
# CREATE/GRANT/REVOKE/COPY as English words either. `preflight()` below re-checks
# both before spending a request, and comments are stripped from the fixture
# before substitution.
#
# Gotcha #54: never pipe a gate. Exit code is read from `$?` on its own line.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The floor baked into verdict-core.sql, and the one fixtures.sql is written
# against. `render` rewrites it; the self-test always uses this value.
PINNED_FLOOR="2026-08-23"
FLOOR="${FLOOR:-$PINNED_FLOOR}"
MODE="${1:-all}"

# shellcheck disable=SC1090
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
: "${BAINLUCK_API:=https://api.bainluck.com}"
if [ -z "${ADMIN_TOKEN:-}" ]; then
  echo "[verdict] ADMIN_TOKEN unset - source ~/.claude/.env first"
  exit 2
fi

render() {  # render <prefix_select> <source_expr_file|-> <group_clause>
  HERE="$HERE" FLOOR="$FLOOR" PREFIX="$1" SRC="$2" GRP="$3" python3 - <<'PY'
import os, re, json, sys
here, floor = os.environ["HERE"], os.environ["FLOOR"]
tpl = open(os.path.join(here, "verdict-core.sql")).read()
src = os.environ["SRC"]
if src == "device_tokens":
    source = "device_tokens"
else:
    raw = open(os.path.join(here, src)).read()
    # Strip FULL-LINE `--` comments before substitution. Not a general SQL
    # comment stripper: it deliberately leaves anything after code on a line
    # alone, because a naive strip would eat a `--` inside a string literal.
    source = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("--")).strip()
sql = (tpl.replace("{{PREFIX_SELECT}}", os.environ["PREFIX"])
          .replace("{{SOURCE}}", source)
          .replace("{{GROUP}}", os.environ["GRP"])
          .replace("2026-08-23 00:00:00+00", floor + " 00:00:00+00")).strip()
bad = re.findall(r"(?i)\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy)\b", sql)
if bad or ";" in sql:
    sys.stderr.write(f"[verdict] PREFLIGHT FAILED keywords={sorted(set(b.lower() for b in bad))} semicolons={sql.count(';')}\n")
    raise SystemExit(3)
json.dump({"sql": sql, "limit": 20}, sys.stdout)
PY
}

ask() {  # ask <payload_file> <out_file>
  curl -s -X POST \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    "$BAINLUCK_API/api/admin/db-query" \
    -d @"$1" -o "$2" -w '[verdict] HTTP %{http_code}\n'
}

rc_total=0

if [ "$MODE" != "--verdict-only" ]; then
  # The self-test ALWAYS runs at the pinned floor, never at $FLOOR. The fixture
  # timestamps are chosen relative to it — `2_stale`'s ios rows sit at
  # 2026-08-01, just below 2026-08-23 — so running the fixtures at a caller's
  # floor turns a correct ladder red. Measured: `FLOOR=2026-08-01` flips
  # `2_stale` from STALE to FIXED, which is the substitution working, not the
  # ladder breaking. The floor is a parameter of the LIVE question ("did THIS
  # session register"), not of the proof that the ladder can answer it.
  echo "=== SELF-TEST: all six branches over synthetic rows (pinned floor $PINNED_FLOOR) ==="
  FLOOR="$PINNED_FLOOR" render $'\n  scenario,' fixtures.sql $'\nGROUP BY scenario\nORDER BY scenario' > /tmp/pv-selftest.json
  rc=$?
  if [ $rc -ne 0 ]; then echo "[verdict] render failed rc=$rc"; exit $rc; fi
  ask /tmp/pv-selftest.json /tmp/pv-selftest-out.json
  python3 - <<'PY'
import json, sys
EXPECT = {
    "1_broken": "BROKEN", "2_stale": "STALE", "3_mislabeled": "MISLABELED",
    "4_fixed": "FIXED", "5_partial_apns": "PARTIAL", "6_partial_fcm": "PARTIAL",
}
d = json.load(open("/tmp/pv-selftest-out.json"))
if "rows" not in d:
    print("[verdict] SELF-TEST could not run:", d); raise SystemExit(3)
got = {r[0]: r[1].split(" -")[0] for r in d["rows"]}
bad = [k for k, v in EXPECT.items() if got.get(k) != v]
for k in sorted(EXPECT):
    mark = "ok " if got.get(k) == EXPECT[k] else "BAD"
    print(f"  [{mark}] {k:16} expected {EXPECT[k]:11} got {got.get(k)}")
missing = set(EXPECT) - set(got)
if missing: print("  MISSING SCENARIOS:", sorted(missing))
print("SELF-TEST:", "PASS 6/6" if not bad and not missing else f"FAIL ({len(bad)+len(missing)})")
raise SystemExit(0 if not bad and not missing else 1)
PY
  rc=$?
  echo "SELF-TEST EXIT CODE: $rc"
  rc_total=$((rc_total + rc))
fi

if [ "$MODE" != "--selftest-only" ]; then
  echo
  echo "=== VERDICT: live device_tokens (floor $FLOOR) ==="
  render "" device_tokens "" > /tmp/pv-verdict.json
  rc=$?
  if [ $rc -ne 0 ]; then echo "[verdict] render failed rc=$rc"; exit $rc; fi
  ask /tmp/pv-verdict.json /tmp/pv-verdict-out.json
  python3 - <<'PY'
import json
d = json.load(open("/tmp/pv-verdict-out.json"))
if "rows" not in d:
    print("[verdict] VERDICT could not run:", d); raise SystemExit(3)
cols, row = d["columns"], d["rows"][0]
v = dict(zip(cols, row))
print()
print("  " + v["verdict"])
print()
for k in cols[1:]:
    print(f"    {k:16} {v[k]}")
PY
  rc=$?
  echo "VERDICT EXIT CODE: $rc"
  rc_total=$((rc_total + rc))
fi

echo
echo "TOTAL EXIT CODE: $rc_total"
exit $rc_total
