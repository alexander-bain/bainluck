# RULING 049 — An acceptance criterion that cannot fail after the fix is not evidence

date: 2026-08-14
author: Fable
issues: #1586, #1818, #1544

Two moves in the CAL-P052 report are ratified into the record. They are one
ruling because they are one discipline seen from two sides: **the record has to
be able to contradict you.**

## 1. A criterion that the fix makes unfalsifiable has stopped being a criterion

#1818's acceptance criterion 3 was `settled_by_result_only < 50` for two
consecutive sweeps. That counter lived as a `COUNT(*) FILTER (WHERE status IS
DISTINCT FROM 'resolved')` **inside** a population defined by `status =
'resolved'`. The moment the settled predicate narrowed to that population, the
filter could only return 0 — not because the defect was gone, but because the
predicate had made the question unaskable.

The counter would have read 0 forever. The issue would have closed on it. And
nothing about the world would have been measured.

**So the counter was promoted out into its own statement**, capable of returning
something else, and the zero it reports is a fact again.

The rule this settles, and it applies to every alarm, gate and acceptance box in
this repo:

> **Before accepting a criterion, ask what would have to be true in the world
> for it to FAIL. If the answer is "nothing, now that the fix has shipped", it is
> not evidence — it is arithmetic wearing evidence's clothes.**

The same discipline the lane already applied to zeros (*a zero is a claim about
the world only if the instrument could have said otherwise* — gotcha #53's
lesson, #683's ten weeks of green SUCCESS over total loss) applied one level up,
to the criterion rather than to the reading.

This sentence goes into the cohort-health sentinel's spec too, because a grid of
per-cell verdicts is the largest surface this failure has ever had: **every cell
verdict needs a test proving the cell could have come out the other way.** A
`NOT-PROVABLE` state computed from a predicate that can never fire reproduces
the defect at grid scale, and reads as coverage while providing none.

### The corollary, which is the part that costs something

A fix that zeroes its own metric is the **most** suspicious outcome, not the most
satisfying one. Two questions before banking it:

1. Did the number move because the world moved, or because the predicate moved?
2. Can the instrument still report the defect's RETURN?

CAL-P052 answered both, and the answer to the second was no until the counter
was moved. That is the work; the green number was never the work.

## 2. A claim you have already committed is corrected IN the record

CAL-P052 committed a "two-instrument agreement" claim, then found — mid-window,
from codex C-RV-4 — that two of the three counters were structurally incapable
of returning non-zero. Their zeros were arithmetic. The "agreement" was one
instrument and two decorations.

The lane committed a **correction against its own already-committed claim**
rather than letting it stand, and rather than quietly not repeating it.

> **A wrong claim in the record is repaired by a further entry in the record.**
> Not by silence, not by an edit that erases the original, and not by declining
> to mention it in the next report. The correction cites what it corrects.

Silence is the tempting option because nobody is reading closely enough to catch
it — which is exactly the condition under which the record has to be
self-correcting. A record that only ever accumulates claims that survived
scrutiny is a record of scrutiny, not of facts.

Two properties make a correction load-bearing:

* **It names the original.** "An earlier claim in this queue said X; X is wrong,
  because Y." A correction nobody can trace to what it corrects is a new claim.
* **It survives the fix.** The corrected version stays in the docstring, the
  commit message and the report even after the defect is repaired — because the
  next reader's question is not "is it broken now", it is "how did this get
  believed for a cycle".

## Named failures behind this ruling

| move | what it caught |
|---|---|
| the promotion | #1818's criterion 3 would have been satisfied by arithmetic; the counter that watches for the defect's return would have been silent by construction |
| the correction | a committed "two instruments agree" claim that was one instrument, two structural zeros — quoted as evidence in a queue report before it was caught |

## What this does NOT license

It does not license re-opening settled acceptance every time a number looks
convenient. The test is narrow and mechanical: *could this criterion fail?* A
criterion that can fail and happens to pass is evidence. That is most of them.

Related: [[044-rendered-green-is-not-communicates-green]] — the same shape one
layer out, where a rendering gate cannot fail on a communication defect and so
cannot be that defect's acceptance.
