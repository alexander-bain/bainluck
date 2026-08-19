# RULING 093 — A cert BLOCK outranks a HELD age

date: 2026-08-19
author: Fable
issues: #1981 · #1979 · #1947

**When a certification returns BLOCK on an item that is also aging in the HELD table, the
BLOCK is the gate. The row is RE-WRITTEN onto the cert's findings — not re-aged, not
released, not escalated past. Age measures neglect; a BLOCK measures a defect.**

## Why

The HELD table exists because a held item nobody re-reads renews its own permission slip, and
its escalation fires at age ≥ 5. That escalation is right against the failure it was built for
— a hold waiting on nobody — and dangerous against this one, because the two look identical
from the age column. Both show a row that has not moved for many windows.

They are opposites. A stale gate should be released or re-pointed; a BLOCKED gate should be
*fixed*, and releasing it ships the defect the certification found. Age is a proxy for "nobody
is looking"; a BLOCK is direct evidence that somebody looked and found something. Direct
evidence outranks its own proxy.

So the resolution is neither of the two comfortable moves. Not "the gate is stale, release it"
— the cert says otherwise. Not "reset the age, the situation changed" — nothing was delivered,
and resetting is how a genuinely neglected row hides. **Re-word the row onto the cert's
findings and leave the age running.** The age then measures the real thing: how long the
findings have gone unfixed.

## Charter case

Queue 371, the 341 row at age 13. `C-APPLY-PRE-CREATE-R2` returned BLOCK on two findings (the
CREATE address not injective over `sport_id`; the decoder with zero application callers). The
row's gate became *fix both + re-cert R4*, its age stayed 13, and the fixes shipped that window.
