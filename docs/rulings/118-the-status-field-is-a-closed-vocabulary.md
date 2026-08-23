# RULING 118 — The `status:` field is a CLOSED VOCABULARY

date: 2026-08-22
author: Fable (INT-109 directive, pasted and reviewed by Alex; banked and enforced by the Integrator)
issues: #1621, #2020
amends: extends ruling 115 to the case it left open

**A READY token's `status:` may only take a value from a closed, published vocabulary. The sweep
FAILS LOUD on anything else — `UNKNOWN-STATUS`, reported, and `--strict` reds on all of it. Human
prose lives in a separate `note:` field, which the sweep parses and prints.**

Ruling 115 closed the case where a token says **nothing**. This closes the case it left open: a
token that says something **no reader understands**. They are the same defect one layer along, and
they failed through the same line of code.

## Why they are the same defect

The sweep's readiness test was `status.strip().lower() in READY_VALUES`. Every unrecognised value
therefore behaved **identically to a missing one**: it answered `False`, and `False` dropped the
token at the `continue` that discards an honestly-merged token. Not deprioritised — *unseen*. Absent
from every verdict group, absent from the coverage ratio, absent from `--strict`.

Ruling 115's own words apply without a change of subject: folding an uninterpretable value into a
negative "renders silence in the same bytes as a decision."

## The charter case, measured the day it was banked

194 tokens in `.claude/handoff`. **14 carried a status outside any vocabulary**, wearing 11 distinct
hand-written values:

```
'⛔ STILL VISIBLE, NOT MERGE-ELIGIBLE — no ready_for_integration token.'
'BOUNCED by INT-087 — merged as 72b7ed7a, REVERTED as e61ef179.'
'merged + DDL HALF NOW DISCHARGED — INT-075, 2026-08-17. All three indexes are VALID:'
'⛔ SUPERSEDED — DO NOT MERGE FROM THIS FILE (marked by INT-071, 2026-08-15)'
'superseded-by-READY-lane1-1991'   'BLOCKED_codex_C-SEN-1'   'BLOCKED_RENUMBER'
'partially_merged'   'BOUNCED…'   'SUPERSEDED'   'NEVER-MERGE'
```

Fourteen artisanal statuses invisible to every grep is the missing-status defect wearing costumes.

**Two of them sat over UNMERGED work and were invisible to every prior sweep** — found by the
enforcement on its first run, which is the only reason they are in this file:

| token | branch | verdict it should have had |
|---|---|---|
| `READY-lane1-q353-process.md` — `BLOCKED_RENUMBER` | `lane1/q353-process` @ `4de6e262` | **LIVE-READY** |
| `READY-calibration-38.md` — `⛔ STILL VISIBLE, NOT MERGE-ELIGIBLE…` | `program/calibration-38` @ `c8c56144` | **MOVED-HEAD** |

### The specimen that settles the design

`merged + DDL HALF NOW DISCHARGED — INT-075, 2026-08-17…` **starts** with a vocabulary word and is
not equal to one. A literal-bytes grep for `status: merged` — which is how a human audits 194 files —
skips it. So the sweep must **refuse** the value rather than normalise it down to its first word:
repairing it in the reader would fix the report while leaving the prose in the machine field, and the
prose in the machine field is the whole defect. Pinned by
`test_a_status_that_merely_STARTS_with_a_vocabulary_word_is_still_unknown`.

The prose is not the problem. The prose being in the **machine field** is. That is why the remedy
ships a `note:` field in the same change: a place to put the sentence removes the reason to smuggle
it into `status:`, and a field the tool ignores is a field nobody fills in, so the sweep prints it.

## The vocabulary

Kept deliberately small. A value earns a place only if a reader must BRANCH on it; everything else
is a defined value plus a `note:`.

`ready_for_integration` · `ready` (short form, accepted and reported) · `merged` ·
`partially_merged` · `bounced` · `void` · `superseded` · `withdrawn` · `blocked` · `held` ·
`never_merge` / `never-merge` · `excused`

Three of these are not cosmetic. **`bounced`** cannot be folded into `merged`: ancestry survives a
revert and content does not (cal-43/#2076 — an ancestor of master that never landed). **`blocked`**
takes its reason in `note:`, which is what dissolves `BLOCKED_RENUMBER` and `BLOCKED_codex_C-SEN-1`
into one greppable value. **`excused`** is new, and it is the ruling's second half.

## `excused` is a status, because "omit the field" was the only way to say it

`READY-calibration-52.md` deliberately carries no `status:`, documented at
`PROGRAM-CALIBRATION-QUEUE.md:2294`: visible, not merge-eligible. That intent is real and correct,
and ruling 115 correctly calls its expression *silence*. The lane was not being sloppy — **there was
no word for what it meant.**

So the vocabulary supplies one. `excused` says "deliberately not a merge offer" out loud, and the
token stops depending on a reader knowing which absences were intentional.

Until the lane writes it, `READY-calibration-52.md` is excused **by name**, in a one-entry allowlist
that prints its own reason in the report. By name and never by shape: "the sweep decided this
omission looked intentional" is exactly the guess ruling 115 forbids. The allowlist is a bridge that
should shrink to empty, not a place to add a line per lane.

And an excusal is still **printed**. An excusal nobody can see is indistinguishable from an
oversight.

## Enforcement, and one deliberate asymmetry

`scripts/sweep_ready_tokens.py`, beside the fail-loud rules of 109/113/115 — the same instrument for
the fourth time, because prose is forgotten and a section of the sweep's own output is run.

1. `is_ready` raises `UnknownStatus` (**not** a subclass of `MalformedToken` — different facts,
   different fixes, and an existing `except MalformedToken` would otherwise swallow this the day it
   shipped; pinned by a test).
2. `UNKNOWN-STATUS` is its own verdict group, ranked directly after MALFORMED, and the offending
   value is **quoted** in the report rather than summarised.
3. Unknown tokens are still resolved against git and carry the verdict they WOULD have had, so
   "unknown over spent work" (bookkeeping) stays distinguishable from "unknown over live commits".
4. Coverage counts an uninterpretable status against the same ratio as an absent one.
5. `note:` is parsed and printed.
6. **`--strict` reds on every UNKNOWN-STATUS, not only those over live work.** This differs from
   MALFORMED on purpose: a missing status is often an ancient merged token nobody will touch again,
   so gating on all 12 would make `--strict` permanently red and therefore ignored. An unknown status
   was *typed* by someone and is fixed by one word plus a `note:` line — the set is small, closed and
   drainable, which is the only honest reason to gate on all of it.

**9 new tests, and all nine fail against the pre-change script** (ruling 108 — enforcement proved
red before it is trusted). Four *pre-existing* tests matched the same `-k` filter and passed, which
is correct: they cover the ruling-115 cases this ruling deliberately leaves alone. The script was
restored afterwards and verified by `shasum -c`.

## General clause → doctrine

**A closed vocabulary is what makes a field readable by anything other than its author.** An open
string field in a machine-read record does not fail when someone writes prose into it — it succeeds,
silently, into a reader that has no branch for the value, and the writer gets no signal because
writing it *felt* like recording the fact. Ruling 115 says absence is a value; this adds that an
unrecognised value is also an absence, and that the fix is never "tell people the convention" —
conventions are advisory to the writer and invisible to the reader. The reader is the only party
present at every read.
