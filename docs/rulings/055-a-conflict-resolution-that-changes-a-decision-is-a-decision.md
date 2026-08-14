# RULING 055 — A conflict resolution that changes a decision is a decision, and is recorded like one

date: 2026-08-14
author: Alex
issues: #1620, #1854

When resolving a merge conflict requires **overturning a prior deliberate
decision**, the lane overturns it **in the open**:

1. **Name the decision being overturned** and where it was recorded.
2. **Cite the later-and-specific ruling** that overrides it. Later alone is not
   enough, and specific alone is not enough.
3. **Post the reversal to the thread that carries the original**, so the person
   who made that decision finds out from the record rather than from a surprise.
4. **Hand the Integrator the recipe** — the resolution, not just the verdict.

Never resolve it quietly and let the reversal ride in as a merge artifact.

Named as **the standard**: UX-P077's handling of `app/routes/events.py`, where a
mechanical-looking conflict sat on top of Q333's deliberate KEEP. It was
overturned openly, the later-and-specific ruling was cited, the reversal was
posted to #1620, and the Integrator received the recipe.

## Corollary — a duplicate NUMBER renumbers, never keep-both

`gotcha 130 renumbers, never keep-both.`

**This does not contradict ruling 037.** The two govern different objects, and
conflating them is the error this corollary exists to prevent:

| | 037 — KEEP BOTH | 055 — RENUMBER |
|---|---|---|
| the object | adjacent **text**: two distinct entries whose prose abuts | a repeated **number** |
| why | both entries are real; a certified gate run is not voided to resolve an adjacency | one number cannot name two entries |
| result | both survive, both keep their identity | both survive, one changes its number |

In both cases **nothing is dropped**. A duplicate number is not two entries — it
is one identifier claiming to be two, and two live cross-references reading
`See gotcha #130.` would point ambiguously at either. `backend/tests/test_gotcha_numbering.py`
asserts uniqueness precisely because KEEP BOTH is the reflex and it is the wrong
reflex here.

Which side renumbers is settled by `.claude/handoff/RULING-CLAIMS.md`: whichever
entry is already on `master` keeps the number; among unmerged branches, the lane
that **claimed the number in the ledger** keeps it and the one that took it
without claiming moves. That rule has now run in both directions on this lane —
UX-P069 read the ledger and lost anyway (2026-08-13), and UX-P074 skipped the
ledger and must move (2026-08-14).

## WHY

**A conflict marker is a question about text; overturning a decision is a
question about judgment, and git presents them identically.** That is the whole
hazard. The resolver is under time pressure, holding a red tree, looking at two
hunks — and the cheapest correct-looking action silently retires somebody's
reasoning. Nothing errors. The tests go green. The decision is simply gone, and
the only record that it was ever made is a comment the resolution deleted.

So the rule is not "be careful in conflicts". It is: **a conflict that requires
judgment has left the mechanical category, and leaves it loudly.** If resolving
it means citing a ruling, it means writing the citation down where the reversed
party will read it.
