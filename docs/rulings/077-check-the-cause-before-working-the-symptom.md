# RULING 077 — a symptom filed as its own issue must be checked against the open issue list for its CAUSE before it is worked, and the first place to look is the label the symptom already carries

date: 2026-08-17
author: latency lane (LAT-P064), on its own near-miss
issues: #1922, #1609, #1545

**Supersedes:** nothing. **Related:** ruling 050 (register before you work), ruling 069 (measure a
bar, never re-quote it), gotcha #53.

---

## The ruling

Before working an issue, search the open issue list for its **mechanism** — and search under the
issue's own `area:` / `program:` labels first, because a cause filed by the same programme is the
most likely thing to already exist and the least likely thing to be looked for.

Three obligations, all cheap:

1. **Look.** `gh issue list --state open`, filtered by the symptom's own labels, for the layer
   underneath it. This costs one command and belongs in Phase 0.
2. **Route the evidence to the cause, not the symptom.** When the cause is already filed, mark the
   symptom **blocked on** it and comment the measurements **onto the cause**, where the acceptance
   criteria live. A fix proposed on the symptom's issue is a fix aimed at the symptom.
3. **Exhaust the reachable evidence before requesting the unreachable.** A sandbox limit is a reason
   to look harder locally before it is a reason to escalate. A favour asked and then not needed
   still spends someone's attention.

## The specimen

**#1922** — *"`warm_typeahead` stalls for minutes at a time — the head goes fully cold (4/24)"* — was
filed by LAT-P063 as a warmer defect, staged as LAT-P064's headline item, and given a three-branch
diagnostic plan (S1/S2/S3). The plan's own note said the distinguishing evidence lived in the worker
log, that **`heroku logs` is EPERM-blocked from an agent sandbox**, and that the fallback was to ask
Alex or the Integrator to run one command.

**#1609** — *"Celery background queue ~490 deep (10× threshold), beat tasks lapping themselves —
starves is_winner coverage precompute into 'no data'"* — was filed **2026-08-09**, is **p1**, and
carries **`program:latency`**: the same label the window was executing under. It had named the
queue-level cause **nine days earlier**, and its acceptance #2 (*"no periodic task has more than one
instance enqueued at a time"*) describes the exact burst signature #1922 measured.

Two admin reads settled the mechanism, and neither was exotic:

* `GET /api/admin/ops-snapshot` → `background: 295`, `realtime: 0`, `heavy: 0`. CLAUDE.md's own
  threshold is **">50 → purge + investigate."**
* `heroku ps` → `worker-background: --concurrency=2`, against residents whose measured p50s are
  **334.9 s** (`prediction_market_match`, 48 of 50 runs > 120 s) and **320.2 s**
  (`poll_kalshi_markets`), while `warm_typeahead` needs a slot every ~35 s.

**The log slice was never needed.**

## Why this is worth a ruling rather than a note

**The cost of not looking is not a duplicate issue.** A duplicate is cheap and obvious. The real cost
is a **fix aimed at the symptom**: a warmer-side change — reroute it, shrink its head, widen its
concurrency — would have made the stalls quieter, closed #1922 on measured improvement, and left
#1609 open with one fewer piece of evidence pointing at it. **That downgrades a p1 without anyone
deciding to**, and it does so through a sequence in which every individual step looks like good work.

The failure is structurally invisible from inside the symptom's issue, because a symptom's issue
contains everything needed to work it and nothing that says it shouldn't be. Only the *other* issue
knows. That is what makes it a Phase-0 obligation rather than a matter of judgment.

## The counter-case, so this is not read as "never fix a symptom"

Sometimes the symptom deserves its own fix: when the cause is genuinely unowned, when the symptom's
blast radius is worse than the cause's, or when the cause's remedy is expensive and the symptom's is
free and non-masking. **The obligation is to make that call knowingly.** #1922's remedy (worker
capacity or a queue split) has a monthly cost attached and belongs to Alex and the Integrator; the
lane's job was to hand them the numbers, not to spend the cheaper option on the lane's own behalf.

LAT-P064 did register a narrow warmer-side change — `"expires": 30` on the beat entry — and
**deliberately did not ship it**, with its registered prediction stating that **hole frequency would
be UNCHANGED**. That is the shape this ruling permits: a symptom-side change whose own prediction
says it does not fix the symptom, so it cannot be mistaken for the cure.
