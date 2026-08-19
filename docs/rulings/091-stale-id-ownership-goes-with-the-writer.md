# RULING 091 — Stale-id ownership goes with the writer

date: 2026-08-19
author: Fable
issues: #1981 · #1979 · #1947

**A writer that finds a row BY a provider id may not then use that id as evidence the row is
the right one. It re-verifies against an independent signal, re-binds, or nulls — it NEVER
compares against a stale id. Keeping provider ids current belongs to the writer that reads
them, not to a separate cleanup somebody schedules later.**

## Why

Looking a row up by an id and then trusting the id is circular, and the circle is invisible
because it is spelled across two statements. #1981 is the specimen: the Odds API scores block
found each row by `external_id`, then asked whether *the score record's* commence had passed —
never whether the row's own had. Each contaminated row carried the PREVIOUS night's event id,
so the answer was always yes, and the previous night's final was stamped onto the next night's
game every 300 seconds. Every individual line was correct. The join between them was the defect.

The independent signal already existed: the row's own `commence_time`. That is the whole fix —
`external_id_currency(row.commence_time, provider_start)`, three-valued, and anything but
CURRENT refuses.

**The ownership half matters as much as the check.** The habit is to treat a stale id as data
debt for a future cleanup queue, which leaves the writer reading it in the meantime. But the
writer is the only party that learns an id has gone stale — it is holding both sides at the
moment of the read. A defect discovered by a writer and deferred to a cleanup is a defect that
keeps happening at the cadence of the writer, and the cleanup will be spent on arrival because
the writer re-creates it (ruling 079's lesson, one table over).

The disjunction is deliberate. **Re-verify** is usually right and always available.
**Re-bind** is right where the true owner is unambiguous. **Null** is right only where the
column tolerates it — `events.external_id` is `UNIQUE`, so nulling with no replacement
manufactures a duplicate of a live game, which is why #1981 took the re-verify arm and said so
in the code. What is never right is the fourth option: compare against it and hope.

Gotcha #32 closes into this.
