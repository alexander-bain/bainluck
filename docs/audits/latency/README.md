# The latency lane's report convention

Everything in this directory is a latency-lane report, pre-registration record or
raw artifact. This file is the convention those reports follow. It is here, next
to them, because a convention kept only in a ruling index is a convention a
session discovers after it has already written the report.

Three standing rulings own the content; this file owns nothing of its own and
adds no authority. It exists so that all three are visible in one place at the
moment they apply.

## 1. Every report OPENS with the cold path a user walks

Ruling 137 (which amends ruling 127 §1). Alex's words:

> "stop bragging about warm searches — a tiny fraction of searches will be warm.
> What matters most: Discover load time, the load time of the other tabs, and
> COLD search load. That's what a user experiences in volume."

The opening rows are Discover / Sports / Browse / My Stuff first load and cold
search, produced by **`backend/scripts/cold_path_snapshot.py`**. Warm numbers
are demoted, not deleted — `done_bar_snapshot.py` keeps its series, and a
warm-hit win may never open a report or lead a claim.

## 2. Every report ENDS with the NEEDLE line

`.claude/handoff/NEEDLE-SPEC.md` (Alex, 2026-08-28). Alex's DONE section shows
ONE number per lane, and **the lane computes and emits it — Fable only copies.**
So a report that does not carry the line has not produced the lane's number,
whatever else it measured.

The last line of every latency report, verbatim in this shape:

    NEEDLE: latency <ms> ms @ <ISO-8601 UTC timestamp>

Do not hand-compute it. Run:

```bash
source ~/.claude/.env
python3 backend/scripts/needle_latency.py --label "<queue-id>" \
    --stats-before /tmp/stats-before.json --out /tmp/needle.json
```

The script prints the line itself; copy its last line into the report. Its
defaults are the frozen sampling depth, and it labels any run that departs from
them as non-canonical so a smoke read is never quoted as a point in the series.

**If the number did not move, print it unmoved.** Never substitute a different
metric on a bad day — per the spec, the metric changes only by Alex ruling.

**If the run refuses (exit 1, "POOL TOO THIN"), the report says the needle was
not obtainable and why.** That is a null, and a null is not a fast number. It
does not license reporting the previous cycle's value as current.

### The two hazards that will bite the next session

**1. You cannot take two readings back to back.** The needle is cold-only. The
graded shapes are pre-warmed on a schedule and are also republished by this
instrument's own anonymous-principal samples, so a second run inside the anon
response TTL measures what the first run warmed. Measured 2026-08-28: a read
taken ~1 minute after a 22-cold-sample read returned 0 cold samples on 6 of 7
member paths and correctly refused to publish. Leave a real gap between runs.

**2. Read the balanced cross-check before you attribute a move.** The raw pool
is composition-sensitive. Measured 2026-08-28 on identical code, same slug, ten
minutes apart: the needle went 711 ms → 536 ms (−25 %) while the balanced
cross-check went 882 ms → 873 ms (−1 %) and Discover's own cold p50 *doubled*.
The published statistic is the raw pool (that is what the spec ratified), but a
report that quotes a move without checking the cross-check and the per-path cold
counts is reporting a cache-mix change as a product change. Say which it is.

## 3. The instrument clauses of ruling 127 carry over

Unchanged and not restated here: the organic-first census read (take
`/api/admin/latency-stats` BEFORE probing and pass it as `--stats-before`),
observer subtraction, contamination declaration, the derived transport floor,
and the frozen term set. The instruments enforce these mechanically rather than
by memory — that is why they are scripts and not a checklist.

## 4. Instrument work must name the decision it unblocks

Ruling 127 §2, and CLAUDE.md's PROGRESS-NOT-MEASUREMENT section above it. A
measurement that unblocks nothing right now is **parked**, not dropped:
`.claude/handoff/PARKED-MEASUREMENTS.md`.
