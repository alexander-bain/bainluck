# RULING 083 — A guard that cannot tell two cases apart is given EVIDENCE, not a wider band; and the version bump that buys time for that is the last one that may mean "time passed"

date: 2026-08-18
author: Fable
issues: #1955, #1680, #1544
supersedes: none — amends the SCOPE of ruling 009 for exactly one commit

## The ruling

CAL-P070 ships **one commit**: `CALIBRATION_POPULATION_VERSION` q267 → q268 **plus** #1955's
durable fix. **Ruling 009's freeze on `precompute_calibration.py` lifts for exactly this commit
and closes behind it.** The staged bank is spent by the bump and that spend is authorised: the
bank is unpublishable by construction, so spending it on the permanent fix is spending nothing.

Two standing clauses come out of it.

### 1. Evidence, not a wider band

When a guard refuses because it **cannot distinguish** two situations, the fix is to give it the
missing evidence. Widening the band it refused with is not a fix — it deletes the question and
keeps the answer. This is ruling 079's clause, restated for a threshold rather than a population,
and it is the test any future "the gate is too strict" argument has to pass.

The concrete shape here: the publish gate could not tell *"we changed which rows qualify"* from
*"the build took sixteen days"*, because both arrive as a population delta and a count cannot say
why it moved. The answer was not a bigger tolerance. It was for the artifact to **state its
predicate** — `population_predicate_fingerprint`, a digest of the population CTEs' own source — so
the two cases stop looking alike. The ±5% band is untouched for a shrink, untouched when either
side is silent, and relaxed only where the code has *proved* the qualifying rule did not move.

**Note what this forbids.** "The guard keeps refusing, so raise the limit" remains refused. "The
guard keeps refusing, and here is the evidence that separates the case it is catching from the
case it is not" is the only accepted argument.

### 2. A version bump is an OPERATOR ACT, and it must carry its own rollover

`population_version` names a methodology. Spending it to acknowledge ordinary data growth drains
it of meaning, so **q268 is the last bump that may mean "time passed"** — after this commit,
growth on an unchanged predicate publishes with no bump at all, and a bump that claims no
methodology change has no remaining excuse.

Every future bump additionally carries its own rollover declaration or accepts a dark page:

* If the previous artifact is **provably comparable** (the methodology did not move), the outgoing
  version goes in `COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` and the page serves it *dated,
  degraded, provenanced and read-only* until the first build under the new version publishes —
  the ratified `deploy-before-candidate` disposition, which existed as a green contract with no
  implementation while production would have gone dark.
* If the methodology **did** move, that list ships EMPTY. A banner over numbers that mean
  something else is the thing CAL-P017 forbade, and this does not touch that.

The entry bar is a proof, not a preference. Both clients widen in the same commit, because a
client narrower than the server refuses the very payload that keeps the surface lit.

## Why

Three things had to be true at once, and only one commit could make them true.

**The build was not wrong.** It completed every phase for the first time since 2026-08-02 and came
in +17.9% (706,290 → 832,650) because sixteen days of season backfill and never-graded drains had
landed underneath it — baseball_mlb 4,596 → 24,811, basketball_nba 2,284 → 12,470, icehockey_nhl
1,958 → 10,616. The gate refused it once an hour, thirteen times and counting (#1954, #1956,
#1959–#1969), and the refusal grew **more** certain the longer the build ran. A guard whose
false-refusal rate rises with build duration is not conservative; it is a ratchet.

**The obvious fixes were each wrong in an instructive way.** Recounting the baseline's predicate at
compare time is the correct idea and unaffordable — that count is exactly the aggregate that times
out. Age-scaled tolerance needs a growth slope nobody can derive honestly from one observation.
And a composition-delta rule — the approach #1955 itself judged most promising — **would have
refused this very build**, because backfill growth is not compositionally neutral. Three plausible
answers, all of them new ways to say no. The discriminator had to be the code, not the data.

**The bump could not ship alone.** A bare bump has been unshippable since 2026-08-02, when one took
/calibration dark and was reverted inside the hour; two separate tests existed only to stop anyone
repeating it, and both cited the outage rather than an invariant. Ordering the bump without
closing that hole would have shipped a known P0 on the page #1517 exists to keep lit. So the
authorisation carries the obligation: the operator act is allowed, and it is the operator's job to
make it survivable.

## What this cost, recorded so nobody re-litigates it

* The 128-unit staged bank, discarded — the version is an input to `_main_input_fingerprint`. It
  was worth little: 119 of its 125 checkable units were censuses of an older population, so
  publishing it would have published a sixteen-day smear.
* iOS builds already on devices read q268 as incompatible until their owners update. Inherent to
  any bump; it is why the rollout order is clients-first whenever there is a choice.
