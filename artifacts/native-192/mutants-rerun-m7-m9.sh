set -u
ROOT=/Users/bain/bainluck-dev/native
JEST="$ROOT/frontend/__tests__/ios/periodLabelSingleSource.test.ts"
BAK=$(mktemp -d); cp "$JEST" "$BAK/j.ts"
restore(){ cp "$BAK/j.ts" "$JEST"; }
trap 'restore; exit 130' INT TERM
run(){ ( cd "$ROOT/frontend" && npx jest --testPathPatterns=periodLabelSingleSource > "$1" 2>&1 ); }
apply(){ python3 - "$1" "$2" "$3" <<'PY'
import sys
p,n,r=sys.argv[1],sys.argv[2],sys.argv[3]
s=open(p).read()
assert n in s, "NEEDLE NOT FOUND"
open(p,'w').write(s.replace(n,r,1))
PY
}
echo "M7 (rerun) — the renamed-join tell is deleted from the scan"
apply "$JEST" '  if (RAW_JOIN_RENAMED.some((re) => re.test(code))) {' '  if (false && RAW_JOIN_RENAMED.some((re) => re.test(code))) {' && {
  L=$(mktemp); run "$L"; RC=$?
  if [ $RC -ne 0 ]; then echo "   KILLED (jest rc=$RC)"; /usr/bin/grep -E '✕' "$L" | head -3 | sed 's/^/     /'; else echo "   *** SURVIVED ***"; fi
  rm -f "$L"; }
restore
echo "M9 (rerun) — GamePlayCardView drops off the named pair-printer list"
apply "$JEST" '  [join(IOS_ROOT, "Components/GamePlayCardView.swift"), "the play card under the chart"],' '' && {
  L=$(mktemp); run "$L"; RC=$?
  if [ $RC -ne 0 ]; then echo "   KILLED (jest rc=$RC)"; /usr/bin/grep -E '✕' "$L" | head -3 | sed 's/^/     /'; else echo "   *** SURVIVED ***"; fi
  rm -f "$L"; }
restore
echo "CONTROL"
L=$(mktemp); run "$L"; RC=$?
[ $RC -eq 0 ] && { echo "   SURVIVED (correct)"; /usr/bin/grep -E '^Tests:' "$L" | sed 's/^/     /'; } || echo "   *** CONTROL FAILED ***"
rm -f "$L"
diff -q "$BAK/j.ts" "$JEST" >/dev/null && echo "tree restored: IDENTICAL" || echo "*** DIFFERS ***"
rm -rf "$BAK"
