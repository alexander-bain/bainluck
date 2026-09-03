#!/bin/bash
# felt-table.sh — publish the felt table from production, one surface at a time, inside the budget.
#
# WHY THIS EXISTS RATHER THAN A FOR-LOOP IN A TRANSCRIPT. Three things kept going wrong by hand and
# each of them silently changes the numbers rather than failing:
#
#  1. **The 60/min cap is shared by the whole machine.** An `/events/{id}` cold load fires ~22
#     requests. Eight surfaces back to back at the rig's default 3 s pace runs at roughly twice the
#     budget, so the tail of the table measures its own 429s — and until LAT-P218 added a status
#     column there was no way to see that had happened. This paces to the budget and then PROVES it
#     by refusing to publish a row whose `throttledRuns` is not zero.
#  2. **The unattended #2724 watcher shares that cap.** If `tools/watch-release-window.sh` is
#     sampling a release window, an attended table run corrupts the one verdict nobody can re-take.
#     So this WAITS on the watcher's `active-window` marker. The watcher never waits for this.
#  3. **A run with no valid rows still writes a plausible-looking JSON.** Each surface is checked and
#     named in the summary as VALID / THROTTLED / EMPTY, so a zero-yield run is loud.
#
# Usage:
#   bash tools/felt-table.sh <outdir> [surfaces...]
#   FELT_THROTTLE=slow4g FELT_CPU=4 RUNS=5 bash tools/felt-table.sh /tmp/felt-after
#
# Defaults measure the desktop-class cold table. Set FELT_THROTTLE=slow4g FELT_CPU=4 for the phone
# rows — those are the rows Alex reads.

OUT="${1:?usage: felt-table.sh <outdir> [surfaces...]}"; shift
SURFACES=("$@")
[ ${#SURFACES[@]} -eq 0 ] && SURFACES=(discover sports usopen event search politics profile calibration)

REPO="${REPO:-/Users/bain/bainluck-dev/latency}"
NODE="${NODE:-/opt/homebrew/bin/node}"
WATCH_WORK="${WATCH_WORK:-/tmp/lat-2724-watch}"
RUNS="${RUNS:-5}"
# 20 s is the measured-safe pace for the heaviest surface (~22 requests): 3 loads/min = ~66 req/min
# worst case, and the lighter surfaces sit well under. Below this the Event row measures throttling.
export FELT_PACE_MS="${FELT_PACE_MS:-20000}"
export FELT_MODE="${FELT_MODE:-cold}"

mkdir -p "$OUT"
echo "felt-table: out=$OUT runs=$RUNS pace=${FELT_PACE_MS}ms throttle=${FELT_THROTTLE:-none} cpu=${FELT_CPU:-1}"

wait_for_quiet() {
  local waited=0
  while [ -f "$WATCH_WORK/active-window" ]; do
    if [ "$waited" = 0 ]; then
      echo "  ⏸  a release window is being sampled ($(cat "$WATCH_WORK/active-window" 2>/dev/null)) — waiting; the unattended verdict outranks this table"
    fi
    sleep 15; waited=$(( waited + 15 ))
    # A marker older than the watcher's own max window is stale (the watcher was killed mid-window).
    # Waiting forever on a dead process would be a worse failure than one contended reading.
    if [ "$waited" -ge "${MAX_WAIT_S:-3000}" ]; then
      echo "  ⚠️  marker still present after ${waited}s — proceeding; treat any throttled row as contended"
      return
    fi
  done
  [ "$waited" -gt 0 ] && echo "  ▶️  window closed after ${waited}s — resuming"
}

# 🔴 ONE RUN PER INVOCATION, NOT $RUNS (measured, not reasoned). The first version called
# `felt-load.mjs <surface> $RUNS` and checked the watcher's marker once per SURFACE. A release window
# then opened between run 4 and run 5 of Discover and that run came back at 7,540 ms against a 2,912 ms
# p50 — a real number for a reader loading during a deploy, and a lie in a table headed "steady state".
# With n=5 the p95 IS the worst run, so one deploy would have published Discover's p95 as 7.5 s.
# Driving the runs from here means the marker is checked BETWEEN EVERY RUN, and the merge below keeps
# the output file shape identical so nothing downstream has to know.
one_run() {
  local s="$1" i="$2"
  ( cd "$REPO" && FELT_PACE_MS=0 "$NODE" tools/felt-load.mjs "$s" 1 "$OUT/.$s.run$i.json" >/dev/null )
}

declare -a LINES
for s in "${SURFACES[@]}"; do
  echo "── $s ──"
  for i in $(seq 1 "$RUNS"); do
    wait_for_quiet
    one_run "$s" "$i"
    [ "$i" -lt "$RUNS" ] && sleep $(( FELT_PACE_MS / 1000 ))
  done
  # Merge the per-run files into the one summary shape the rest of the pipeline reads, recomputing the
  # percentiles over the pooled runs rather than averaging five separate p50s (which is not a p50).
  "$NODE" -e '
    const fs=require("fs"), [out,surface,runs]=process.argv.slice(1);
    const results=[]; let base=null;
    for(let i=1;i<=Number(runs);i++){
      const f=`${out}/.${surface}.run${i}.json`;
      try{ const j=JSON.parse(fs.readFileSync(f,"utf8"));
        base=base||j.summary; for(const r of j.results){ r.run=results.length+1; results.push(r); }
        fs.unlinkSync(f);
      }catch(e){}
    }
    if(!base){ console.error(`   🔴 ${surface}: no run produced JSON`); process.exit(0); }
    const ok=results.filter(r=>r.valid&&!r.throttled);
    const pct=(xs,p)=>{const a=xs.filter(x=>typeof x==="number"&&isFinite(x)).sort((x,y)=>x-y);
      return a.length?a[Math.max(0,Math.min(a.length-1,Math.ceil(p/100*a.length)-1))]:null;};
    const summ=k=>({p50:pct(ok.map(r=>r[k]),50),p95:pct(ok.map(r=>r[k]),95),worst:pct(ok.map(r=>r[k]),100)});
    const summary={...base, runs:results.length, valid:ok.length,
      throttledRuns:results.filter(r=>r.throttled).length,
      medianApiCalls:pct(results.map(r=>r.apiCount),50),
      shell:summ("shell"), first:summ("first"), firstNumber:summ("firstNumber"), fold:summ("fold"),
      hero:summ("hero"), heroRuns:ok.filter(r=>typeof r.hero==="number").length,
      heroPresentRuns:ok.filter(r=>r.heroPresent>0).length,
      medianFoldCards:pct(ok.map(r=>r.foldCards),50)};
    fs.writeFileSync(`${out}/${surface}.json`, JSON.stringify({summary,results},null,2));
  ' "$OUT" "$s" "$RUNS"
  LINES+=("$("$NODE" -e '
    const fs=require("fs");
    let j; try{ j=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); }catch(e){
      console.log(`| ${process.argv[2]} | **RIG FAILED — no JSON** | | | | | |`); process.exit(0); }
    const S=j.summary, n=x=>x==null?"—":Math.round(x);
    // The row states its own trustworthiness. A throttled or empty row must never be quotable as a
    // felt number, so it says so in the cell the reader looks at first.
    const state = S.throttledRuns>0 ? `🔴 THROTTLED ${S.throttledRuns}/${S.runs}`
                : S.valid===0       ? "🔴 EMPTY 0 valid"
                : `${S.valid}/${S.runs}`;
    console.log(`| ${S.surface} | ${state} | ${n(S.shell?.p50)} | ${n(S.first?.p50)} | ${n(S.first?.p95)} | ${S.heroPresentRuns?n(S.hero?.p50):"absent"} | ${n(S.medianApiCalls)} |`);
  ' "$OUT/$s.json" "$s")")
done

TABLE="$OUT/TABLE.md"
{
  echo "# felt table — ${FELT_MODE} · ${FELT_THROTTLE:-no throttle} · cpu ${FELT_CPU:-1}x · $RUNS runs/surface"
  echo
  echo "Measured $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M %Z') from production, hero-based rig."
  echo "\`hero\` is the element the reader came for; \`first\` is the first real card of any kind."
  echo
  echo "| surface | valid | shell p50 | first p50 | first p95 | hero p50 | api calls |"
  echo "|---|---|---:|---:|---:|---:|---:|"
  printf '%s\n' "${LINES[@]}"
} > "$TABLE"
cat "$TABLE"
echo
echo "wrote $TABLE"
grep -q "🔴" "$TABLE" && { echo "🔴 at least one row is THROTTLED or EMPTY — that row is about the battery, not the site. Do not publish it."; exit 1; }
exit 0
