# RULING 101 — Group, don't cull; and a travelled bar may not end anywhere but the resolution

date: 2026-08-19
author: Alex (relayed by Fable, mid-cycle-101)
issues: #1958 (adjacent), props program

Issued on the four cycle-99 expand captures of the event detail view, banked to
master at `7be90eab` (`docs/screenshots/detail.fold.desktop.desktop.png`,
`detail.expanded.readable.desktop.png`, `detail.expanded.mobile.mobile.png`,
`detail.expanded.fullpage.desktop.png`).

These were the shots the props program was blocked on. All three parts below are
binding; **none of them is cycle-101 shipped code** — parts 1 and 2 are mocks
first, back to Alex for one more look.

## 1. Density fails — and the remedy is grouping, not hiding

Verbatim:

> a comical number of rows. There HAS to be a better way to group and show this.
> FAR too many rows, but the answer shouldn't just be to nuke or hide valuable
> outcomes.

The second sentence is the constraint, and it is the one that is easy to lose.
The cheap fix for "too many rows" is a cap, and a cap deletes outcomes that
someone came to the page for. **Zero outcomes may be removed.** The row count
comes down by grouping:

- **Ladders collapse to ONE row per player+stat**, with the rungs rendered
  inside that row. This is the #1639 dedupe learning arriving as UI: the same
  observation that a ladder is one question wearing many names, applied to the
  screen instead of to the feed.
- **Rows group by market family / player, with per-group expand** — progressive
  disclosure, so depth is available on demand rather than paid for on arrival.
- **The fold stays.** Alex did not object to off-script-first, so that ordering
  is ratified by silence and should not be relitigated in the mock.

## 2. The post-game travelled bar is wrong, and it exposed a data question

Verbatim:

> shouldn't it always finish at 0% or 100%? … post-game it doesn't make any
> sense.

He is right, and the reason is that the bar's endpoint is the **last traded
price**, not the **resolution**. A market that settles YES but whose final trade
printed at 0.82 draws a bar ending at 82% on a question whose answer is now
known with certainty. That is the *settled means settled* ruling being violated
by a chart: the page has the answer and is still showing the guess.

**POST-GAME: no travel bar.** Render the pregame mark and the resolved outcome:

```
18% → HIT          71% → MISSED
```

with **surprise = |resolution − pregame mark|**. The sentence treatment survives
for the big surprises. The red/green line does not.

**IN-GAME: the travelled bar is explicitly approved.** *"maybe this red-green
view would work in-game"* is taken as the green light — it lives in live states
and only there, where there is no resolution to end at and the journey is the
whole content.

### The gate before any of that is built — DISCHARGED, same cycle

**First, verify whether the endpoint-not-resolution is presentational or a
payload gap.** If the rows reaching the client carry no resolution, this is not
a UI defect at all — it routes to grading, and a presentational fix would ship a
bar that still cannot reach 0/100 because nothing ever told it where 0/100 is.

**Answered: PRESENTATIONAL.** Measured on production 2026-08-19 (#2011). Among
rows that actually reach the travelled bar, `hit` is typed on **39/41 (95%)** on
event 15199902 and **4/4** on 15194472. `frontend/lib/propDivergence.ts` builds
every row from `over_probability` and `pregame_mark` and contains **zero**
references to `hit`, `actual`, `is_winner` or `resolution_source` — it does not
import `propGrade.ts` at all, though the rows it receives already carry those
fields and a sibling module already parses them for the prop cards.

The diagnosis also found something the screenshot could not show, and it is the
stronger reason to fix this: **the rail ranks by travel**, and post-game travel
is computed from the last traded price. So `Ozzie Albies: Home Runs O/U 0.5` —
pregame 8.5%, resolved HIT, a 91.5-point surprise — draws a FLAT bar and ranks
**dead last**, while a prop that merely drifted ranks first. Post-game, THE
DIVERGENCE is sorting the biggest surprises to the bottom of the page.

So `surprise = |resolution − pregameMark|` replaces `travel` as the post-game
**ranking key**, not merely as the number printed on the row.

Residual that does route to grading, and it is small: `WITHHOLD` rows (2 of 41
on the larger event) carry no typed verdict, must render
`SETTLED_NO_GRADE_LABEL` with no bar and no surprise number, and must not be
ranked by a fabricated surprise of 0.

## 3. Screenshot durability — option 2 ratified

Rendered evidence belongs on master, committed by the **integrator on its next
master write**, not by the program branch and not left untracked in the shared
tree (gotcha #52 — orphan WIP is not neutral parking, and rescue-branching real
evidence puts it somewhere nobody looks).

The UX branch stays untouched; `program/ux-90` remained at `c4155c15` with its
READY intact. Executed the same day at `7be90eab`.

## Why this is banked rather than built

Cycle 101's queue stands as issued. The grouping mock and the post-game state
are the **props program's next deliverables**, and Alex asked for mocks before
build with one more look before code. Banking the verdict now is what stops the
next window rediscovering it from a screenshot.
