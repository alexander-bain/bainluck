set -u
SRC="frontend/lib/eventConceptDisplay.ts"; BAK=/tmp/8223b.bak; cp "$SRC" "$BAK"
run(){ n="$1"; shift; b=$(shasum "$SRC"|cut -d' ' -f1); "$@"; a=$(shasum "$SRC"|cut -d' ' -f1)
 if [ "$b" = "$a" ]; then echo "UNLANDED  $n"; return; fi
 (cd frontend && npx jest --testPathPatterns=boutDateLabelYear8223 >/tmp/mut.txt 2>&1); rc=$?
 if /usr/bin/grep -q "SyntaxError\|Cannot find module" /tmp/mut.txt; then echo "INVALID   $n"
 elif [ $rc -ne 0 ]; then echo "KILLED    $n"; else echo "SURVIVED  $n"; fi; cp "$BAK" "$SRC"; }

m1(){ perl -0pi -e 's/renderedYear\(d\) !== renderedYear\(now\)/renderedYear(d) === renderedYear(now)/' "$SRC"; }
m2(){ perl -0pi -e 's/\Q...(renderedYear(d) !== renderedYear(now) ? { year: "numeric" as const } : {}),\E//' "$SRC"; }
m3(){ perl -0pi -e 's/renderedYear\(d\) !== renderedYear\(now\) \? \{ year: "numeric" as const \} : \{\}/{ year: "numeric" as const }/' "$SRC"; }
m4(){ perl -0pi -e 's/\Qx.toLocaleDateString(locale, { year: "numeric" })\E/x.toLocaleDateString(locale, { year: "numeric", timeZone: "UTC" })/' "$SRC"; }
m5(){ perl -0pi -e 's/(data\.headline_bout\?\.commence_time \?\? data\.start_date,\s*\n\s*locale,\s*\n)\s*now,\s*\n/$1/' "$SRC"; }
m6(){ perl -0pi -e 's/renderedYear\(now\)/renderedYear(d)/' "$SRC"; }
m7(){ perl -0pi -e 's/if \(Number\.isNaN\(d\.getTime\(\)\)\) return null;\n(\s*\/\/ The year AS)/$1/' "$SRC"; }

run "M1 invert the year test (!== -> ===)"            m1
run "M2 delete the year spread (pre-fix revert)"      m2
run "M3 always print the year"                        m3
run "M4 oracle pinned to UTC (the tidy-up trap)"      m4
run "M5 wrapper stops threading now"                  m5
run "M6 compare the bout's year to itself"            m6
run "M7 drop the unparseable-date guard"              m7
cp "$BAK" "$SRC"; echo "--- restored $(shasum "$SRC"|cut -d' ' -f1) ---"
