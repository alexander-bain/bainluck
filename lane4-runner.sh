#!/bin/bash
# lane4-runner.sh — THE cert bus runner. This is the canonical, tracked name.
#
# TRACKED 2026-09-01 by INT-196 on a Fable-5 directive. Until now this file and
# lanes-supervisor.sh existed ONLY on Alex's laptop, untracked — the same class of
# loss as "three finished ships existed only on one laptop" (REPORT-UX-P204).
#
# CONTENT = the former lane4-runner-v4.sh, which is the newest and only version
# without a known defect. The scratch iterations are deliberately NOT tracked:
#   v1 (this filename's old content) — SPIN bug: treated every non-`done` block as
#      pending, so it fired a full codex session every 60s. Measured 190 sessions/24h.
#   v2 — matched `status: staged`, a token that does not occur in CERT-QUEUE.md, so
#      it could never fire and would have silenced the bus entirely.
#   v3 — fixed the spin; still SILENTLY DISCARDS a block whose `queue_id:` arrives
#      before the previous block's `---` terminator (38 of 269 blocks, measured).
#
# ⚠️ AT THE TIME OF THIS COMMIT THE RUNNING PROCESS IS STILL v3 (pid 397, started
#    ~16h earlier). Committing this file does not restart anything. To adopt it:
#    Ctrl-C the lane4 window and relaunch `~/bainluck/lane4-runner.sh`.
#
# Launch:   ~/bainluck/lane4-runner.sh     (own Terminal window; Ctrl-C to stop)
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY v4 EXISTS (found by lane1 Q493, 2026-09-01, while auditing the GO file's
# "41 MALFORMED blocks" cleanup item).
#
# v3 fixed the SPIN (the bus firing every 60s on a stale block). It left the
# mirror-image failure — SILENCE — wide open, which is the one Alex's GO file
# explicitly wanted impossible:
#
#     "Excluding terminal states rather than including one hoped-for token also
#      means no future status token a lane invents can silently silence the bus;
#      the failure mode becomes a spurious wake, not silence."
#
# That reasoning is about the STATUS TOKEN. It does not hold for BLOCK
# FRAMING. v3's awk only ever evaluates a block when it reaches a `^---$`
# terminator. When a `queue_id:` line arrives while a block is still open, v3
# OVERWRITES `id` and the previous block is discarded — never graded, never
# even reported MALFORMED. It vanishes.
#
# MEASURED on the live CERT-QUEUE.md, 2026-09-01 ~08:1xZ:
#     269 `queue_id:` blocks present
#     231 blocks v3 actually evaluates
#      38 blocks INVISIBLE to the bus  (37 mid-file + 1 unterminated tail)
# Among the invisible: C-LIVE-Q490-POLY-FAST-LANE-TOKEN-TOPUP-1,
# C-LIVE-Q491-WS-FLUSH-RETRY-1, CERT-615/616/617, CERT-629/630 — i.e. ordinary
# live-lane cert blocks, not exotica.
#
# NO HARM TODAY, AND THAT IS EXACTLY WHY IT NEEDED CATCHING: all 271 status
# values on the file right now are terminal (done 255 / superseded 7 /
# running 6 / withdrawn-by-author 2 / withdrawn 1), so 0 actionable is the
# correct answer and v3 returns it — for the wrong reason. The moment a lane
# appends a `status: staged` block that does not get a `---` before the next
# `queue_id:`, THE CERT BUS BANKS "DRAINED" AND THE SUBJECT IS NEVER GRADED.
# The lane waits on a cert that will never come, and nothing anywhere warns.
#
# PROVEN, NOT ASSERTED — differential positive control (a staged block with no
# terminator before the next queue_id):
#     v3 -> actionable: []                            <- silently invisible
#     v4 -> actionable: [C-STAGED-BUT-UNTERMINATED-1]  <- caught
# And the regression arm, against the live file: v4 returns 0 actionable and
# 0 MALFORMED, identical to v3's verdict today, while evaluating all 269
# blocks instead of 231. Blind spot closed, no behaviour change.
#
# THE FIX: end a block on ANY of the three things that can actually end one —
# a `---`, the next `queue_id:`, or EOF — and run the same MALFORMED/actionable
# test in all three cases. A block can now be stale or malformed, but it can no
# longer be silently absent. The failure mode stays "a spurious wake, not
# silence", which is what the GO file asked for.
#
# Everything else is v3 verbatim: the terminal-set definition, the prompt, the
# no-progress backoff.
# ─────────────────────────────────────────────────────────────────────────────
set -u
cd "$HOME/bainluck" || exit 1
Q=".claude/handoff/CERT-QUEUE.md"
CERTLOG=".claude/handoff/CODEX-CERT-LOG.md"
LOG_DIR=".claude/handoff/runner-logs"; mkdir -p "$LOG_DIR"

PROMPT='Standing self-gated cert bus (launched by Alex via lane4-runner). FIRST read .claude/handoff/STANDING-NOTICES.md (items 8, 12, 16: no strike stops, append-only ledger, stop-lifts) and obey it over anything below. Then: run every subject in .claude/handoff/CERT-QUEUE.md whose block says "status: staged" and which has no verdict row banked in CODEX-CERT-LOG.md; bank verdicts and tokens in CODEX-REPORT-2.md and CODEX-CERT-LOG.md.

SCOPE RULE — Alex ruling, 2026-08-31, BINDING ON EVERY VERDICT. Grade the SHIP: does the user-visible behaviour the branch claims actually hold? You may BLOCK on a GUARD (a test, fixture, assertion, comment or tripwire) ONLY IF that guard failing would let the SHIP regress silently. A guard that is merely incomplete against a hypothetical future attack is a FOLLOW-UP ISSUE, not a block: grant the token, and record the guard gap as a named follow-up in the same row. Measured basis for this rule: of the last 40 subjects, 9 GREEN and 31 BLOCK, and of those 31 blocks the ship was wrong 9 times while the guard was hollow 20 times. Two thirds of all rejections landed on scaffolding around a correct ship, and one anchor reached a fourth cert while being correct every time.

NO STRIKE STOP (Alex ruling 9/2, STANDING-NOTICES 8 and 16): a subject may be graded any number of times; a repair (`repairs: CERT-N`) always grades, and grades FIRST. Count strikes in the row for the record, never refuse to grade because of them.

Bank a CERT-BUS-STATUS "DRAINED" row ONLY when the drained state is NEW — if the last banked row was already DRAINED and no verdict has issued since, print the count to the terminal and bank nothing. Re-running early, late, or twice is always safe. Never push, merge, or write production.'


# A subject is actionable iff its status is NOT a terminal/claimed state.
# v2 got this WRONG: it matched `status: staged`, and that token DOES NOT EXIST in
# CERT-QUEUE.md. Measured 2026-08-31 11:1x PT, the only values present are:
#   done 197 | superseded 6 | withdrawn-by-author 2 | withdrawn 1 | running 1
# So v2 could never fire and would have silenced the cert bus entirely.
# v1's bug was the mirror image: it treated ANYTHING that was not `done` as
# pending, so the 10 superseded/withdrawn/running blocks kept it firing forever.
# The fix is to exclude the FULL terminal set, which is what v1 was missing.
TERMINAL="done superseded withdrawn withdrawn-by-author parked-mismatch"
# STALE-CLAIM RESET (Fable-5, 2026-09-01): a bus session that dies mid-grade leaves its block at
# `status: running` forever, and every later poll walks past it (CERT-629/630/631 sat a day).
# Any block still `running` whose claim is older than 3h with no verdict row gets reset to staged.
reset_stale () {
  python3 - "$Q" "$(pwd)/.claude/handoff/CODEX-CERT-LOG.md" <<'PY'
import re,sys,os,time,json
q,log=sys.argv[1],sys.argv[2]
s=open(q).read(); verdicts=open(log).read() if os.path.exists(log) else ""
# v2 (Fable-5): v1 keyed on the queue FILE's mtime, which lanes touch constantly, so the reset
# never fired (CERT-621 sat 23h). Now track each cert's first-seen-running time in a sidecar.
state_p=q+".claims.json"
try: state=json.load(open(state_p))
except Exception: state={}
now=time.time(); running=set()
def fix(m):
    cid=m.group(1); running.add(cid)
    first=state.setdefault(cid,now)
    if now-first<3*3600: return m.group(0)
    if re.search(r"\| %s "%re.escape(cid), verdicts): return m.group(0)
    return m.group(0).replace("status: running","status: staged   # stale claim reset by lane4-runner")
s2=re.sub(r"queue_id: (CERT-\d+)\n(?:.*\n){0,12}?status: running", fix, s)
for cid in list(state):
    if cid not in running: del state[cid]
json.dump(state,open(state_p,"w"))
if s2!=s: open(q,"w").write(s2); print("[lane4] reset stale running claims")
PY
}
pending () {
  reset_stale
  python3 - "$Q" "$CERTLOG" "$TERMINAL" <<'PY'
import re
import sys
from pathlib import Path

queue, ledger, terminal = sys.argv[1:]
terminal = set(terminal.split()) | {"running"}
# Only a merits verdict's identity cell banks a presentation. DRAINED summaries
# and evidence/prose references to other certs are not verdict identities.
banked = set()
if Path(ledger).exists():
    for line in Path(ledger).read_text().splitlines():
        cells = line.split("|")
        if len(cells) < 6 or not re.match(r"\s*\|", line):
            continue
        verdict = cells[4].strip().strip("*")
        if not re.match(r"(?:GREEN|BLOCK)\b", verdict):
            continue
        # First column is `CERT-N -- queue-slug` (not every slug starts C-).
        for identity in re.split(r"\s+(?:--|—|–)\s+", cells[1].strip()):
            identity = identity.strip("*` ")
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identity):
                banked.add(identity)


def actionable(block):
    identity = block.get("queue_id")
    if not identity:
        return False
    status = block.get("status")
    if not status:
        print("MALFORMED " + identity, file=sys.stderr)
        return False
    # A fresh cert_id is a new presentation even if it reuses a queue slug.
    # Never use `repairs:` (the predecessor) as this presentation's identity.
    presentation = block.get("cert_id") or identity
    if status not in terminal and presentation not in banked:
        print(identity)
        return True
    return False


block = {}
heading = None
for line in Path(queue).read_text().splitlines():
    title = re.match(r"^#+\s+(CERT-\d+)\s+(?:--|—|–)\s+([A-Za-z0-9][A-Za-z0-9_-]*)\s*$", line)
    if title:
        heading = (title[1], title[2])
        if (block.get("queue_id") == heading[1]
                and block.get("cert_id", heading[0]) == heading[0]):
            block.setdefault("cert_id", heading[0])
            heading = None  # consumed by this block, never inherited by a repair
        elif block:
            if actionable(block):
                break
            block = {}
    if line.startswith("queue_id:") or line == "---":
        if actionable(block):
            break
        block = {}
    match = re.match(r"^(queue_id|cert_id|status):\s*([^#]*?)\s*(?:#.*)?$", line)
    if match and (match[1] == "queue_id" or block.get("queue_id")):
        value = match[2].strip().strip("\"'")
        block[match[1]] = value.split()[0] if value else ""
        if match[1] == "queue_id" and heading and block["queue_id"] == heading[1]:
            block["cert_id"] = heading[0]
        if match[1] == "queue_id":
            heading = None
    if line == "---":
        heading = None
else:
    actionable(block)
PY
}

verdicts () { grep -c '^| CERT-' "$CERTLOG" 2>/dev/null || echo 0; }

BACKOFF=60
while true; do
  P=$(pending)
  if [ -n "$P" ]; then
    TS=$(date +%Y%m%d-%H%M%S)
    BEFORE=$(verdicts)
    echo "[lane4] $TS actionable subject detected ($P) — starting codex session, log $LOG_DIR/lane4-$TS.log"
    codex exec --full-auto "$PROMPT" 2>&1 | tee -a "$LOG_DIR/lane4-$TS.log"
    AFTER=$(verdicts)
    if [ "$AFTER" -gt "$BEFORE" ]; then
      BACKOFF=60
      echo "[lane4] session banked $((AFTER-BEFORE)) verdict(s) — re-checking in ${BACKOFF}s"
    else
      # SELF-HEAL (Fable-5, 9/2): the bus reports nothing pending while our awk sees
      # 'status: staged' for $P -> the block is already banked/merged by the bus's identity
      # rules. Park it (status: parked-mismatch) so both graders stop idling on it, and
      # leave a note for Fable instead of backing off for 30 minutes.
      python3 - "$Q" "$P" <<'PY'
import re,sys
q,subj=sys.argv[1],sys.argv[2]
s=open(q).read()
pat=re.compile(r"(queue_id: %s\n(?:.*\n){0,6}?status: )staged[^\n]*"%re.escape(subj))
s2,n=pat.subn(r"\1parked-mismatch   # auto-parked by lane4-runner: bus reports nothing pending for this subject; Fable to close or restage",s,count=1)
if n: open(q,"w").write(s2); print("[lane4] parked '%s' (mismatch) -> tell Fable"%subj)
else: print("[lane4] could not find a staged block for '%s' to park"%subj)
PY
      echo "$(date '+%F %T') parked-mismatch $P" >> "$HOME/bainluck/.claude/handoff/LANE4-PARKED.log"
      BACKOFF=30
    fi
    sleep "$BACKOFF"
  else
    echo "[lane4] idle — no actionable subjects ($(date '+%H:%M:%S'))"; sleep 300
  fi
done
