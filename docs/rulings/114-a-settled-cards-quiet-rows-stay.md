# RULING 114 — A settled card's quiet rows stay: no tail, no drop

date: 2026-08-21
author: Alex
issues: #2060

**The boundary case is ruled, so that it stops re-litigating itself.**

On a settled card, some rows have nothing to say — an outcome that never moved, a
prop that was never in doubt, a leg that sat at its opening number until it
graded. Two tidying instincts keep being proposed for them, and **both are
refused**:

- **No tail.** Do not fold the quiet rows into a "and N others" summary line.
- **No drop.** Do not remove them from the card.

They render exactly as they are.

## Why

**A settled card is a record, and a record with the boring parts removed is not a
shorter record — it is a different one.** The whole point of *settled means
settled* is that the card shows what happened. A row that never moved is a fact
about the question: it says nobody doubted this. Summarising it into a tail
converts a fact into a count, and dropping it asserts the row never existed.

**The reader cannot tell a suppressed row from an absent one.** This is the same
shape as gotcha #53 and ruling 086: absence and "nothing to report" are different
facts, and a surface that renders them identically has destroyed the difference
for everyone downstream. A card that quietly hides its quiet rows looks exactly
like a card whose data is incomplete — which is the failure the settled work was
done to end.

**And the cost being optimised away is not real.** The tail and the drop are both
arguments about visual tidiness on a card the reader has already chosen to open.
There is no latency claim here and no correctness claim; there is a preference for
a shorter card. That does not outrank the record.

## Scope

This governs the SETTLED card specifically. It is not a general statement that no
surface may ever cap a list — live and pre-game surfaces rank and cap for good
reasons, and the diversity caps keep their guards in both directions (gotcha #43).
The settled card is different because it has stopped being a ranking and started
being a result.

## Standing instruction

Do not re-open this as a design question. If a future queue proposes a tail or a
drop on the settled card, the answer is this file. A boundary case that is ruled
and then re-argued every cycle costs more than the case is worth, which is the
reason it is written down rather than left as a decision someone remembers.
