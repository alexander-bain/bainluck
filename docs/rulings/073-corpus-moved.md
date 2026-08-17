# RULING 073 — CORPUS-MOVED: a disposition change with no code change is a corpus event, not a ranking result

date: 2026-08-17
author: Fable
issues: #993, #1545

## Provenance note, stated first because it bears on the word "verbatim"

The LAT-P060 directive instructed this lane to bank Fable's ruling text **verbatim**, and located
that text "in this paste's preamble". **No preamble block arrived in the paste this window
received** — what arrived was the directive's own item 1, which states the ruling in three clauses.
Those three clauses are reproduced below **word for word** and are the operative text; the
surrounding exposition is this lane's, and is marked as such. If a fuller Fable text exists, it
supersedes the exposition, never the clauses.

## The ruling — Fable's three clauses, verbatim

> per-probe eligible-pool fingerprints; unchanged-code disposition changes quarantine as
> CORPUS-MOVED; baseline moves only by explicit re-baseline naming the expired specimens.

Unpacked into the three obligations they create:

1. **Every gold probe carries an eligible-pool fingerprint.** A read that cannot say *what corpus it
   ran against* cannot be compared to another read, and comparability is the entire value of a
   frozen gold set.
2. **Unchanged code + moved dispositions ⇒ quarantine as `CORPUS-MOVED`.** The delta is reported,
   named, and **excluded from the score**. It is not a regression and — this is the half that had
   never been tested until LAT-P059 — it is **not an improvement either.**
3. **The banked baseline moves only by an explicit re-baseline that NAMES the expired specimens.**
   A baseline that drifts because the world moved is not a baseline.

**Banked baseline stays 39/44, MRR 0.8913043478260869. The 41/44 / 0.9347826086956522 read is
QUARANTINED**, not banked.

## Why — occurrence four, and the first one that flattered us

LAT-P059 re-ran the armed null control against production with **no code change whatsoever**: the
same producer blob `61de6598`, 46 of 46 specimens, fidelity `exact`. Three of forty-six dispositions
changed, all in the same direction:

| | before | after |
|---|---|---|
| passes | 39/44 | **41/44** |
| MRR | 0.8913043478260869 | **0.9347826086956522** |
| regressions | 0 | **0** |

Read at face value that is *"+2 passes, zero regressions"* — a clean win, and one that a lane under
any pressure at all would bank and then attribute to whatever it had most recently shipped.

The cause was established rather than guessed, and it was none of that. **All three of the old
top-ranked entities had left the eligible pool:**

- *"FedEx St. Jude Championship Winner"* — **resolved.** It had been out-ranking the Fed Chair
  market on the token `fed`.
- *"Stanley Cup … Carolina **Hurricane**s"* — **resolved.** It had been out-ranking the hurricane
  market on the token `hurricane`.
- `event:15191951` — **closed 2026-08-15**, i.e. *between the two reads.*

The ranking function did not get better. **The distractors resolved.** The score moved because the
corpus moved underneath a frozen probe set, and the probe had no way to say so.

**This is the fourth occurrence of "specimens pinned to live markets expire" and the first in the
flattering direction** — which is exactly why it needed a ruling. The three earlier instances all
made the numbers look worse, and a number that looks worse gets investigated. A number that looks
better gets banked. The asymmetry is in the reader, not in the data, so the guard has to be
mechanical.

## The mechanism this makes mandatory

The fingerprint must be **per probe**, not per run. A run-level corpus hash answers *"did anything
anywhere change?"* — which is always yes, on a live market corpus, and therefore says nothing. The
question that has to be answerable is *"did the pool THIS probe ranks over change, and which
members left?"* Only the per-probe form can produce the sentence the ruling requires: **"these named
specimens expired."**

So, per probe and stored with the result:

- the **eligible-pool fingerprint** — a stable digest over the identities of the candidates the
  probe could have ranked;
- the **pool size**, so a shrink is visible even when a digest comparison is unavailable;
- the **expected entity's own eligibility**, because a probe whose target left the pool is not
  failing, it is void.

A disposition change is then classified, not just counted:

| code changed | pool fingerprint changed | verdict |
|---|---|---|
| no | no | **REAL** — a genuine ranking movement, and an alarming one |
| no | yes | **CORPUS-MOVED** — quarantined, excluded from the score |
| yes | no | **REAL** — the change did this |
| yes | yes | **CONFOUNDED** — report both; attribute neither |

The fourth row is not decoration. It is the common case for any lane that ships a ranking change on
a Tuesday and reads it on a Thursday, and the honest verdict there is that the read is not
attributable — not that it is a win.

## What this does NOT say

It does not say the gold set is broken, and it does not license re-pinning the probes to dodge the
problem. A probe pinned to a live market is a **correct** probe — user-facing ranking runs over live
markets, so a gold set over frozen synthetic ones would measure a surface nobody uses. The defect
was never the pinning; it was that the pinning was **invisible in the output**, so an expiry and an
improvement produced the identical row.

Nor does it forbid re-baselining. It requires that a re-baseline be an **act with an author and a
list** — "re-baselined to 41/44, expiring FedEx St. Jude Championship Winner, Carolina Hurricanes,
event:15191951" — rather than a number that quietly became true.

## Family

Sibling of **#53** (an empty 200 is a response shape, not an absence), **ruling 060** (never grow a
graded cohort in place), **ruling 061** (a derived figure is an interim with an expiry) and **ruling
072** (a fixture that agrees with the bug is the bug). Every one of them is the same defect wearing
different clothes: **an instrument reporting confidently about something it never measured.**
