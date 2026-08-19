# RULING 092 — A deriver may not emit a credential it cannot cite

date: 2026-08-19
author: Fable
issues: #1981 · #1979 · #1947

**Code that derives a reviewed object must not stamp it with a human approval. If a field
would assert a ruling, an approval, or a sign-off the deriver cannot cite, OMIT THE FIELD.
An inherited template credential is a forged one.**

## Why

`create_events_from_truth` wrote `"ruling": "Alex 2026-08-17 — attended CREATE from venue
truth, approved"` into the context of every plan it built. For population 2 that sentence was
true. Population 3 was minted a window later, with four games Alex had never seen, and
inherited it — so an artifact carrying zero human review presented an approval, in Alex's name,
with a date.

A missing credential is self-correcting: it prompts the question, and somebody goes and gets
the approval. A forged one *answers* the question, and the auditor moves on. This is why the
rule is omission rather than a better-worded default — any default is a sentence the next
population will inherit, and the failure mode is silent by construction.

The distinction that keeps this workable: **a ruling NUMBER is a citation; an approval is a
claim about a person's decision.** `"050 — armed control, declared BEFORE the recompute"`
points at a file anyone can read and stays true wherever it is copied. `"Alex approved"` is
true only of the rows it was written for.

**Provenance is recorded on the artifact by whoever takes the MC** — the date, the mechanism,
the rows it covers, and who recorded it. Not by the code that built the plan, which cannot
know any of it.

Corollary, and the reason this is cheap: content addresses cover ROWS, not context. Recording
an approval later never re-addresses a reviewed plan, and dropping a fabricated field never
did either. There is no cost to omitting it and no cost to adding the truth afterwards.
