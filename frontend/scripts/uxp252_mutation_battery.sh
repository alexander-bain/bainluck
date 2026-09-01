#!/usr/bin/env bash
# UX-P252 — mutation battery for the "for you" cue render-path guard (CERT-678
# repair). CERT-678 named the absence of a battery; this is it.
#
# ── HOW THIS AVOIDS THE KNOWN WAYS A BATTERY LIES ───────────────────────────
#   * Runs in an rsync COPY, never the live worktree (a killed mutant left
#     behind is a shipped defect).
#   * Every mutation ASSERTS ITS NEEDLE COUNT before writing. A needle that
#     matches 0 sites means the mutation never applied and the "kill" is the
#     suite passing on unmutated source; a needle that matches N>expected means
#     a blind replace hit siblings and the run measured something else.
#   * Every restore is verified by md5 against the pre-mutation file.
#   * Two mutants (I and K) attack the ENUMERATION rather than a call site —
#     they add a NEW uncovered render path and a NEW personalizable item type.
#     Those are the mutants that prove the guard generalises, which is the whole
#     content of the CERT-678 block. A battery of "delete a chip I already wrote
#     a test for" would be self-confirming.
set -uo pipefail

# Repo root: this script lives at frontend/scripts/, alongside the six prior ux
# batteries. Tracked deliberately — a battery that lives only in an untracked
# artifacts dir is invisible to the cert bus, which reads the branch.
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d /tmp/uxp252-mutation.XXXXXX)"
trap 'echo "[work tree kept at $WORK]"' EXIT

echo "== staging an rsync copy of the tree =="
mkdir -p "$WORK/frontend" "$WORK/backend"
rsync -a --exclude node_modules --exclude .next --exclude .git "$SRC/frontend/" "$WORK/frontend/"
rsync -a --exclude __pycache__ "$SRC/backend/app/" "$WORK/backend/app/"
ln -s "$SRC/frontend/node_modules" "$WORK/frontend/node_modules"

FC="$WORK/frontend/components/discover/FuturesCard.tsx"
CC="$WORK/frontend/components/discover/ComparisonCard.tsx"
GC="$WORK/frontend/components/discover/GuessCard.tsx"
CUE="$WORK/frontend/lib/discover/forYouCue.ts"
FEED="$WORK/backend/app/routes/feed.py"

run_suite() {
  (cd "$WORK/frontend" && npx jest --testPathPatterns=forYouCue --silent) > "$WORK/last.txt" 2>&1
  echo $?
}

echo "== control: the unmutated copy must be GREEN =="
CONTROL=$(run_suite)
if [ "$CONTROL" != "0" ]; then
  echo "🔴 CONTROL FAILED (exit $CONTROL) — the battery measured nothing. Last 40 lines:"
  tail -40 "$WORK/last.txt"
  exit 1
fi
echo "control: exit 0 ✅"

PASSED=0; KILLED=0; SURVIVED=0

# mutate <id> <description> <file> <expected-needle-count> <needle> <replacement>
mutate() {
  local id="$1" desc="$2" file="$3" want="$4" needle="$5" repl="$6"
  local before after n exit_code
  before=$(md5 -q "$file")
  cp "$file" "$file.uxp252.bak"
  n=$(python3 - "$file" "$needle" <<'PY'
import sys
src = open(sys.argv[1]).read()
print(src.count(sys.argv[2]))
PY
)
  if [ "$n" != "$want" ]; then
    echo "🔴 $id NEEDLE COUNT $n, EXPECTED $want — refusing to apply. Not a result."
    SURVIVED=$((SURVIVED+1)); return
  fi
  python3 - "$file" "$needle" "$repl" <<'PY'
import sys
p, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(p).read()
open(p, "w").write(src.replace(needle, repl))
PY
  after=$(md5 -q "$file")
  if [ "$before" = "$after" ]; then
    echo "🔴 $id FILE UNCHANGED after replace — the mutation did not apply."
    SURVIVED=$((SURVIVED+1)); return
  fi
  exit_code=$(run_suite)
  # Restore from a byte copy taken before the write, not by reverse-replace: a
  # deletion mutant has an EMPTY replacement, and `src.replace("", needle)`
  # inserts the needle between every character. Caught by the md5 check on
  # mutant B's first run, which is what the md5 check is for.
  cp "$file.uxp252.bak" "$file"
  if [ "$(md5 -q "$file")" != "$before" ]; then
    echo "🔴 $id RESTORE FAILED (md5 mismatch) — every later mutant is contaminated."
    exit 1
  fi
  rm -f "$file.uxp252.bak"
  if [ "$exit_code" = "0" ]; then
    echo "🔴 $id SURVIVED — $desc"
    SURVIVED=$((SURVIVED+1))
  else
    echo "🟢 $id killed  — $desc"
    KILLED=$((KILLED+1))
  fi
  PASSED=$((PASSED+1))
}

echo
echo "== A-F: each call site removed in turn (the four paths CERT-678 named, plus two it did not) =="

mutate A "FuturesCard Variant B loses the chip" "$FC" 1 \
'              CERT-678: Variant B is the no-image half of the A/B split, so which
              of the two a reader got was a coin flip on a hash of their session
              id and the market id — and only one of them said anything. */}
          <ForYouChip cue={cue} />' \
'              CERT-678: Variant B is the no-image half of the A/B split, so which
              of the two a reader got was a coin flip on a hash of their session
              id and the market id — and only one of them said anything. */}'

mutate B "FuturesCard threshold heatmap loses the chip" "$FC" 1 \
'          {cue && <div className="mb-4"><ForYouChip cue={cue} /></div>}' ''

mutate C "FuturesCard leaderboard loses the chip" "$FC" 1 \
'          {cue && <div className="mt-1.5"><ForYouChip cue={cue} /></div>}' ''

mutate D "ComparisonCard loses the chip" "$CC" 1 \
'        <ForYouChip cue={cue} />' ''

mutate E "GuessCard loses the chip" "$GC" 1 \
'        {cue && <div className="mb-3"><ForYouChip cue={cue} /></div>}' ''

mutate F "FuturesCompactRow loses the chip" "$FC" 1 \
'        {rowCue && <div className="mt-1"><ForYouChip cue={rowCue} /></div>}' ''

echo
echo "== G-H: the DECISION reverts to the defect the ship exists to fix =="

mutate G "the multiplier gate is deleted — 'for you' on downranked cards again" "$CUE" 1 \
'  if (typeof item.multiplier !== "number" || !(item.multiplier > 1)) return null;' \
'  // MUTANT: the naive version, which is the original defect.'

mutate H "the gate loosens from > 1 to >= 1 — a card nothing moved says we moved it" "$CUE" 1 \
'!(item.multiplier > 1)' '!(item.multiplier >= 1)'

echo
echo "== I: a NEW card variant appears with no cue (does the enumeration enumerate?) =="

mutate I "a fifth <article> root is added to FuturesCard with no chip" "$FC" 1 \
'  // ── Variant A: image-led (refined current treatment) ──
  return (' \
'  if (data.outcome_count === 999) {
    return (
      <article data-card-variant="C" aria-label={data.name}>
        <h3>{data.name}</h3>
      </article>
    );
  }

  // ── Variant A: image-led (refined current treatment) ──
  return ('

echo
echo "== J: the cross-stack vocabulary check =="

mutate J "a vocabulary id stops matching what the backend emits" "$CUE" 1 \
'{ id: "alma_mater", label: "Your alma mater" },' \
'{ id: "alma_mater_renamed", label: "Your alma mater" },'

echo
echo "== K: the BACKEND personalizes a new item type nobody covered =="

# ⚠️ The needle here is 12-space indented and the other two attachment sites are
# 16-space indented. The obvious needle matched 2 of the 3 sites and the
# occurrence assert REFUSED to apply — a blind replace would have mutated both
# and the result would have been read as a measurement of one.
mutate K "feed.py marks a 'tournament' item personalized" "$FEED" 1 \
'        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score' \
'        _mutant_item = {
            "type": "tournament",
        }
        _mutant_item["personalized"] = True
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score'

echo
echo "════════════════════════════════════════════"
echo "applied: $PASSED   killed: $KILLED   SURVIVED: $SURVIVED"
echo "════════════════════════════════════════════"
[ "$SURVIVED" = "0" ] || exit 1
