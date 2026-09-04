#!/bin/bash
# bus-runner.sh — THE measurement-bus runner. Sibling of lane4-runner.sh.
#
# WHY THIS EXISTS (integrator/135, Fable-5, 2026-09-04, Alex away noon Fri → Mon).
# The cert graders have been headless since lane4-runner.sh; the MEASUREMENT bus
# never was. It ran only when Alex pasted a prompt into a window by hand, and it
# shows: the recurring M-R set banked buckets 04, 13 and 17 on 9/4 and nothing in
# between. Over a weekend with nobody at the keyboard that is not a thin record,
# it is no record — and the M-R set is the instrument the heartbeats read.
#
# Launch:   ~/bainluck/bus-runner.sh        (own Terminal window; Ctrl-C to stop)
# Normally started for you by start-lanes.sh, like the graders.
#
# SAME CLI AS THE GRADERS, and it is genuinely non-interactive: `codex exec` is
# documented as "Run Codex non-interactively", and lane4-runner.sh has been
# driving it unattended in production for days. So integrator/135's condition
# ("ONLY if that CLI supports non-interactive runs") is satisfied — no caveat.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE DESIGN CONSTRAINT THAT SHAPES EVERYTHING BELOW
#
# Fable's 2026-08-31 amendment to CODEX-QUEUE.md killed the original hourly
# bucket, in these words: *"A queue designed so it can never be empty is a queue
# that outcompetes shipping for lane time by construction."* An hourly runner is
# exactly the machine that ruling was written against, so this one is built to be
# able to REACH EMPTY and then be quiet:
#
#   * It fires only when a named artifact for the CURRENT bucket is MISSING.
#     Drained means asleep until the next hour, not a re-count. (lane4-runner's
#     v1 defect was the mirror of this: it treated every non-terminal block as
#     pending and fired a session every 60s — 190 sessions in 24h, measured.)
#   * Every mission carries its own cadence, and the ones with an end date stop
#     asking on that date. M-R-USOPEN through 9/13 is the live case: without the
#     guard, 9/14 is a bucket that can never drain and the bus spins forever on
#     a tournament that is over.
#   * A bucket gets at most MAX_TRIES sessions. If codex banks nothing three
#     times running, the hour is abandoned with a loud line rather than retried
#     until the heat death of the laptop. A missing hour is cheap; a wedged bus
#     burning tokens all weekend is not.
#
# It is read-only measurement and says so in the prompt: never push, never merge,
# never write production. That is the measurement lane's whole charter
# (CLAUDE.md, LANE ROLES).
# ─────────────────────────────────────────────────────────────────────────────
set -u
cd "$HOME/bainluck" || exit 1
# Overridable so the guard test can point the whole runner at a scratch handoff
# tree — same reason and same shape as lane-runner.sh's LANE_HANDOFF. Production
# never sets it.
H="${BUS_HANDOFF:-.claude/handoff}"
Q="$H/CODEX-QUEUE.md"
LEDGER="$H/ARTIFACT-M-R-AUTHORITY-LEDGER.md"
LOG_DIR="$H/runner-logs"; mkdir -p "$LOG_DIR"
STATE="$H/.bus-runner-attempts"

[ -f "$Q" ] || { echo "[bus] missing $Q — nothing to run"; exit 1; }

MAX_TRIES="${BUS_MAX_TRIES:-3}"        # sessions per bucket before abandoning the hour
USOPEN_THROUGH="${BUS_USOPEN_THROUGH:-20260913}"   # M-R-USOPEN's own end date

# The bucketed M-R missions, in CODEX-QUEUE.md's own order. Each banks
# ARTIFACT-M-R-<NAME>-<YYYYMMDD-HH>.md. M-R-AUTHORITY is deliberately NOT here:
# it is daily and appends to a LEDGER instead of a bucket file, so it has its own
# test below. Adding a mission to the set = adding its name to this list.
MISSIONS="NEEDLES PRECERT DEFECTS CLAIMS STRANDED BOARD USOPEN ATTACH CHARTS FRESH"

bucket ()     { date -u +%Y%m%d-%H; }
bucket_day () { date -u +%Y%m%d; }
today_iso ()  { date -u +%Y-%m-%d; }

# Which of this hour's artifacts are absent? Prints one mission name per line.
# This is the whole gate: present artifact == mission done for the bucket.
missing () {
  local B="$1" M
  for M in $MISSIONS; do
    # M-R-USOPEN is scoped to the tournament. Past its end date it is not
    # missing, it is over — otherwise every bucket from 9/14 on is undrainable.
    if [ "$M" = USOPEN ] && [ "$(bucket_day)" -gt "$USOPEN_THROUGH" ]; then continue; fi
    [ -f "$H/ARTIFACT-M-R-$M-$B.md" ] || echo "$M"
  done
  # M-R-AUTHORITY: once per day, at the first bucket at/after 14Z (its brief).
  # Done-test is a day heading in the append-only ledger, not a bucket file.
  if [ "$(date -u +%H)" -ge 14 ] && ! grep -q "^## $(today_iso)" "$LEDGER" 2>/dev/null; then
    echo "AUTHORITY"
  fi
}

# Attempts are tracked per bucket so the count resets on its own every hour and
# no cleanup is ever owed. One line: "<bucket> <count>".
tries_for () {
  local B="$1" line
  line=$(cat "$STATE" 2>/dev/null)
  case "$line" in "$B "*) echo "${line#"$B" }" ;; *) echo 0 ;; esac
}
record_try () { echo "$1 $2" > "$STATE"; }

prompt_for () {
  local B="$1" WANT="$2"
  cat <<EOF
Standing self-gated MEASUREMENT bus (launched by Alex via bus-runner.sh). FIRST read
.claude/handoff/STANDING-NOTICES.md and obey it over anything below — in particular notice 26
(MEASURE THE VENUE, NOT OUR MIRROR: answer "does the venue list X?" against the venue's own API by
series/tag discovery, never from our ingest tables and never from a guessed ticker, and say the
method in the first line; a measurement that contradicts what Alex saw with his own eyes is
presumed wrong until a SECOND method reproduces it; artifact names carry the mission's own slug).

Run the M-R set for the CURRENT hour bucket, then STOP. The bucket is $B (UTC date-hour).
The missions whose artifact for this bucket is MISSING, and the only ones you should run:

$WANT

Their briefs are in .claude/handoff/CODEX-QUEUE.md — locate each with
\`grep -n 'M-R-<NAME>' .claude/handoff/CODEX-QUEUE.md\` and read the slice. READ BUDGET: bounded
reads only, never read CODEX-QUEUE.md whole (it is ~149k chars); keep startup reads under 20k.

Bank each one as .claude/handoff/ARTIFACT-M-R-<NAME>-$B.md — that exact filename is what marks
the mission done for this hour, so a mission you actually ran must always end with its file
written, and a mission you did NOT run must NOT get one. A short honest artifact beats a long
guess: if something is UNMEASURABLE, write the artifact and say UNMEASURABLE and why. If a
mission's correct answer is one line ("no staged subjects"), that one line IS the artifact.
M-R-AUTHORITY is the exception: it appends one row per sport under a "## $(today_iso)" heading in
.claude/handoff/ARTIFACT-M-R-AUTHORITY-LEDGER.md (append-only) instead of a bucket file, and it
reads GET /api/admin/statpal/authority-agreement rather than re-deriving verdicts.

Do not run missions outside the list above. Do not invent a finer bucket. Do not file a delta
artifact because something moved. When every mission in the list has its artifact, you are done —
stop, do not look for more work.

READ-ONLY. Never push, never merge, never write production, never edit code. You are the
measurement lane; findings go to artifacts and to CODEX-REPORT-2.md, and anything needing a
decision goes to .claude/handoff/alex-inbox/ in plain English (the word "cert" may not appear
there — say "review").
EOF
}

echo "[bus] measurement bus up. missions: $MISSIONS (+AUTHORITY daily ≥14Z)"
echo "[bus] artifacts: $H/ARTIFACT-M-R-<NAME>-<bucket>.md   logs: $LOG_DIR/"

while true; do
  B=$(bucket)
  WANT=$(missing "$B")

  if [ -z "$WANT" ]; then
    # Drained. Sleep to the top of the next hour rather than re-polling: there is
    # nothing that can become due before the bucket rolls, so a shorter sleep can
    # only produce noise.
    NOW=$(date +%s); NAP=$(( 3600 - NOW % 3600 )); [ "$NAP" -lt 60 ] && NAP=60
    echo "[bus] $B drained — all M-R artifacts present ($(date '+%H:%M:%S') local). Next bucket in ${NAP}s."
    sleep "$NAP"
    continue
  fi

  N=$(tries_for "$B")
  if [ "$N" -ge "$MAX_TRIES" ]; then
    NOW=$(date +%s); NAP=$(( 3600 - NOW % 3600 )); [ "$NAP" -lt 60 ] && NAP=60
    echo "[bus] ***************************************************************"
    echo "[bus] ABANDONING bucket $B after $N sessions that banked nothing."
    echo "[bus] Still missing: $(echo $WANT | tr '\n' ' ')"
    echo "[bus] Not retried — waiting ${NAP}s for the next bucket. If this repeats"
    echo "[bus] every hour the bus is wedged: read $LOG_DIR/bus-*.log and tell Fable."
    echo "[bus] ***************************************************************"
    sleep "$NAP"
    continue
  fi

  TS=$(date +%Y%m%d-%H%M%S)
  BEFORE=$(missing "$B" | wc -l | tr -d ' ')
  echo "[bus] $TS bucket $B — $BEFORE mission(s) unbanked ($(echo $WANT | tr '\n' ' ')) — starting codex session, log $LOG_DIR/bus-$TS.log"
  record_try "$B" "$((N + 1))"
  codex exec --full-auto "$(prompt_for "$B" "$WANT")" 2>&1 | tee -a "$LOG_DIR/bus-$TS.log"
  AFTER=$(missing "$B" | wc -l | tr -d ' ')

  if [ "$AFTER" -lt "$BEFORE" ]; then
    # Progress: reset the strike count. A session that banks some but not all of
    # the set is normal and gets a fresh budget to finish the rest.
    record_try "$B" 0
    echo "[bus] session banked $((BEFORE - AFTER)) artifact(s); $AFTER still missing in $B"
  else
    echo "[bus] session banked NOTHING for $B (attempt $((N + 1))/$MAX_TRIES)"
    sleep 60
  fi
done
