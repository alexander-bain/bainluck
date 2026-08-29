#!/usr/bin/env bash
# CAL-P123 — mutation check for test_calibration_family_fold_p123.py
#
# Every mutation is applied to the INSTRUMENT, verified to have actually
# changed the file (a mutation that fails to apply reports green and is the
# single most common way a mutation harness lies), then the guard suite must go
# RED. Baseline is restored and re-verified green at the end.
set -u
cd "$(dirname "$0")/../.." || exit 2
SRC=backend/scripts/calibration_family_fold.py
SUITE=backend/tests/test_calibration_family_fold_p123.py
BAK=$(mktemp)
cp "$SRC" "$BAK"

pass=0; fail=0; n=0

mutate() {  # name, sed-expression
  n=$((n + 1))
  cp "$BAK" "$SRC"
  sed -i '' "$2" "$SRC"
  if cmp -s "$BAK" "$SRC"; then
    echo "  M$n $1 -- ⚠️  DID NOT APPLY (harness bug, not a pass)"
    fail=$((fail + 1)); return
  fi
  if (cd backend && python3 -m pytest "../$SUITE" -q >/dev/null 2>&1); then
    echo "  M$n $1 -- ❌ SURVIVED (guard is blind)"
    fail=$((fail + 1))
  else
    echo "  M$n $1 -- ✅ killed"
    pass=$((pass + 1))
  fi
}

echo "MUTATIONS"
mutate "greedy '^.* - ' -> lazy '^.*? - '"        "s/'\^\.\* - '/'^.*? - '/"
mutate "digit normalisation dropped"              "s/'\[0-9\]+', '#', 'g'/'', '', 'g'/"
mutate "no-dash arm renamed to match_line"        "s/z_no_dash_suffix/a_match_line/g"
mutate "field_1win test loosened to mw >= 1"      "s/sh.mn >= 3 AND sh.mw = 1 AND ms.msum/sh.mn >= 3 AND sh.mw >= 1 AND ms.msum/"
mutate "partition threshold 1.15 -> 1.50"         "s/ms.msum <= 1.15/ms.msum <= 1.50/"
mutate "NULL price sum falls through to clean"    "s/ms.msum IS NOT NULL AND //"
mutate "lone_outcome arm moved after undiff"      "s/WHEN onm.on_n = 1 THEN 'd_lone_outcome'//"
mutate "partly_duplicated tested before full"     "s/WHEN onm.on_d = 1 THEN 'a_undifferentiated'//"
mutate "z_unknown folded into c_distinct"         "s/WHEN onm.on_n IS NULL THEN 'z_unknown'//"
mutate "distinctness swapped for a LIKE test"     "s/COUNT(DISTINCT fo4.name)/COUNT(*) FILTER (WHERE fo4.name LIKE '%')/"
mutate "planner hint dropped from the new join"   "s/WHERE fo4.market_id IN (SELECT market_id FROM market_info)//"
mutate "LEFT JOIN -> INNER JOIN on outcome names" "s/^LEFT JOIN ($/JOIN (/"
mutate "setdefault -> subscript assignment"       "s/cce.DIMENSIONS.setdefault(_name, _spec)/cce.DIMENSIONS[_name] = _spec/"
mutate "loader re-registers in sys.modules"       "s/    spec.loader.exec_module(mod)/    sys.modules[name] = mod\n    spec.loader.exec_module(mod)/"
mutate "explicit --by is overridden"              "s/if not any(a == \"--by\" or a.startswith(\"--by=\") for a in sys.argv\[1:\]):/if True:/"

cp "$BAK" "$SRC"; rm -f "$BAK"
echo
echo "baseline restored:"
(cd backend && python3 -m pytest "../$SUITE" -q 2>&1 | tail -1)
echo
echo "RESULT  $pass killed / $n mutations   ($fail not killed)"
[ "$fail" -eq 0 ] || exit 1
