# RULING 120 — A derived write carries the key that reverses it

date: 2026-08-22
author: Fable (directive pasted and reviewed by Alex), banked by lane1 queue 391
issues: #2063

## The ruling

**The backfill provenance key is BLESSED.** `polymarket_event_id_source = 'group_id_backfill_q390'`
stays **ON** for the 489k-row `polymarket_event_id` apply
(`backend/scripts/backfill_polymarket_event_id.py`, default; `--no-stamp-provenance` opts out and
the decision stays the caller's).

Two things it buys, and they are the whole rationale for the record:

1. **The write becomes exactly reversible.** The undo is a predicate, not an archaeology project:
   `WHERE market_metadata->>'polymarket_event_id_source' = 'group_id_backfill_q390'`, null the key
   back. No log to reconstruct, no reasoning about which rows a statement happened to touch on the
   night it ran.
2. **It permanently distinguishes a DERIVED id from one CAPTURED AT MINT.** The distinction is not
   temporary scaffolding for the apply window — it is a fact about those rows that stays true, and
   a reader a year from now can ask it directly instead of inferring it.

**The deviation is an improvement, not scope creep.** The rail was flagged as deviating from *"the
audit's exact UPDATE"*, which writes one key where this writes two. That flag was the right
instinct and the right way to surface it — and the disposition is that the deviation points in the
direction our provenance doctrine already points. Gotcha #32's CREATE arm already tags the row it
creates (`provenance:unanchored`); ruling 048 already turns on being able to tell an id-anchored
claim from an id-less one. A mass write that stamps what produced it is the same principle applied
to a backfill instead of to a create.

**The gate does not move.** The apply stays where it was gated: **AFTER the mint fix deploys.**
This ruling records the bless so the apply is unblocked the moment its gate opens. **It does not
fire it, and nothing here is authorization to fire it.**

## Why this needed a ruling and not a code comment

Because the rail already argued both sides correctly and still could not decide. Its docstring
states the case against with no softening — *"it is not what was specified, and it puts a key in
the gold path that no existing reader expects"* — and then defaults the flag ON anyway. An
executing lane cannot resolve that tension from inside the script: choosing to deviate from a
specified statement on a 489k-row write is a judgment about what the write is FOR, and that is
Alex's call, not the rail's. Flagging it and shipping it defaulted-on-but-overridable was the
correct shape for a lane to hand up. This is the answer coming back down.

The narrow reading — *"do exactly the UPDATE the audit wrote"* — is the reading that loses
something real. Without the second key, **489k rows become indistinguishable from correctly-minted
rows the moment the statement commits.** Not wrong; *unaskable*. That is the cost being declined.

## The general clause

**A bulk write that cannot be identified afterwards is a bulk write that cannot be undone.** The
cost of the second key is paid once, at write time, in bytes. The cost of omitting it is paid
every future time anyone needs to ask which rows a statement touched — and it is paid in
reconstruction, which is the expensive kind and the kind that is sometimes simply not possible.

The sharper form, and the reason this is a doctrine-shaped clause rather than a preference about
one script: **derived data and captured data that look identical will be read identically.** A row
whose id was inferred from a `group_id` and a row whose id was recorded at mint are different
claims about the world with different confidence, and if the schema does not carry the difference,
no reader can recover it — every consumer downstream silently promotes the weaker claim to the
strength of the stronger one. This is gotcha #53's shape moved from a response body to a table:
two states that report identically will be treated as one state, and the merge always resolves
toward the more confident reading.

So: **when a write derives a value rather than observing it, the write says so, in the row.**

## Scope, stated so it is not over-read

This blesses stamping **provenance** — a key that records *what produced this value*. It is not a
licence to add sibling keys to `market_metadata` generally, and it does not make every mass write
reversible by decoration: the reversibility here is real only because the rail is also **additive**
(`||`, no key replaced or removed) and **guarded**
(`NOT (market_metadata ? 'polymarket_event_id')`, so a row that already had one is never touched
and a re-run is a no-op). A provenance key on a destructive or overwriting statement records who
broke it, not how to fix it. **Reversibility is a property of the statement; the key only makes it
addressable.**

## Ledger note

This ruling's number was allocated by claiming in `.claude/handoff/RULING-CLAIMS.md` against a
`git fetch` in the same turn — `origin/master` = `a13239f1`, highest ruling FILE on master **116**,
merged-tree ruling count **113**, all **556** local and remote refs swept for `docs/rulings/120-`
with `holders_found = 0`. 119 was deliberately not taken: it belongs to `lane1/q353-process`,
claimed one line above in the same turn. That is ruling 116's *count the merged tree* and doctrine
clause 10's *an identifier in a directive is a proposal; the ledger allocates*, applied rather than
cited.
