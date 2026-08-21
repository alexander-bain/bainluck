# RULING 115 — A missing `status:` is MALFORMED, not not-ready

date: 2026-08-21
author: Fable (INT-103 directive; proposal from the Integrator, adopted verbatim)
issues: #1621, #1933, #2020, #671

**The READY sweep FAILS LOUD on a token with no `status:` field. MALFORMED is a report line, never
a silent `False`. `is_ready(None)` raises; it does not answer.**

A token that never states a status has not said "no". It has said nothing, and a parser that maps
*the field is absent* onto the same value as *the field says merged* has destroyed the one
distinction the reader needs. `is_ready` returning `False` for both is not a conservative default —
it is a confident answer to a question nobody asked, rendered in the same bytes as a real one.

## The charter case is this cycle, measured

INT-103's Phase 0 ran the canonical sweep against 178 token files and returned **3 LIVE-READY**.
Six branches were genuinely being offered for merge:

| offer | token | seen by the sweep? |
|---|---|---|
| `program/ux-98` | `READY-ux-98.md`, well-formed | ✅ |
| `program/latency-70` | `READY-latency-LAT-P077.md`, well-formed | ✅ |
| `program/calibration-79` | `READY-calibration-79.md`, well-formed | ✅ |
| `program/ux-99` | `READY-ux-99.md` — **no `status:`** | ❌ invisible |
| PR #2062 `lane1/q386-rail` | `READY-lane1-386.md` — **no `status:`** | ❌ invisible to the token half |
| PR #2063 `lane1/q386-admin-identity` | **no token at all** | ❌ invisible to the token half |

**The sweep was 50% blind and said so nowhere.** Its output contained no line reading "3 of 6"; it
contained a confident list of three.

`program/ux-99` is the specimen that matters, because it is invisible to **both** of ruling 113's
sources at once: its token is malformed, and it has no PR to fall back on. It carries three commits
including the `graded_card` rename's only consumer, it is the ordering constraint the whole
directive is built around, and the only thing that surfaced it was Fable naming it by hand. That is
precisely the failure ruling 113 was written to end, recurring one layer below the fix.

## Why a report line addressed to a human was already tried, and failed

This is the **fifth instance in five cycles**, and the fourth cycle in which somebody wrote it down:

* `READY-calibration-75.md` shipped with no `status:` over gate-clean unmerged work and was invisible
  for a full cycle — named in ruling 113's own charter case.
* `READY-lane1-372.md` wrote `status: ready` and was invisible to a literal grep; the short form is
  now accepted, and `READY_VALUES` carries a comment explaining why.
* `READY-lane1-382.md` carried its branches under `## Branch 1` headings and parsed as
  `branch: None`.
* `NOTE-TO-UX-FROM-INT088.md` counted `READY-ux-99`'s defect as *"the 14th token in this family"* —
  a count someone maintained by hand.
* **INT-102 wrote the fix request into its own queue file**: *"PR #2062 needs a `status:` field on
  `READY-lane1-386.md` before the sweep can see it."* One cycle later the field is still absent and
  #2062 was still invisible to the token sweep.

So the remedy is not another instruction to lanes. Lanes are not careless; the token is a
hand-written assertion and hand-written assertions have defect rates. **The reader is the only party
present at every sweep, so the reader is where the check goes** — ruling 109's move ("a list a human
consults is a list a human forgets") and ruling 113's move ("also check PRs" is prose, so it will be
forgotten; a section in the sweep's own output is code, so it will be run"), applied a third time to
the same instrument.

## Why loud, rather than lenient

The tempting alternative — infer ready from the filename, since the file is literally called
`READY-*.md` — is refused for the reason ruling 113's sweep already documents: it would make every
one of the 178 historical tokens in that directory live again. Absence cannot be resolved by
guessing which way it points. It can only be **reported as absence**.

Nor is MALFORMED merely cosmetic. A malformed token over spent work is bookkeeping; a malformed
token over a branch with real unmerged commits is a lane's work sitting unmerged with nobody
looking. The sweep therefore resolves a malformed token's branch anyway and reports what it *would*
have been, so the two cases are distinguishable at a glance and only the second one blocks.

## What the sweep must do

1. `is_ready(None)` — and an empty or whitespace-only status — **raises `MalformedToken`**. There is
   no boolean answer available and the function must not manufacture one. `parse_token` leaves
   `status` at `None` for both an absent field and a present-but-empty one, so this is the single
   choke point.
2. A token that raises is included in the report with verdict **MALFORMED**, never dropped. It is
   resolved against git like any other, and carries the verdict it *would* have had as
   `underlying`.
3. MALFORMED renders **first**, above VOID, because a token that cannot be read is a prior question
   to a token that can. Rows whose `underlying` is LIVE-READY or MOVED-HEAD are flagged
   `⚠ REAL WORK, INVISIBLE`.
4. The header states coverage as a ratio — `N of M tokens carry a readable status` — so a blind
   sweep can never again print only what it could see.
5. `--strict` exits 1 when a MALFORMED token sits over unmerged work. A defect that cannot red a
   gate is a defect that gets written down for five cycles (ruling 108's obligation, and #2020's).

Nothing is removed. A well-formed token behaves exactly as before, and ruling 034 still governs
whichever source surfaced the branch: **confirm by content before merging.**

## The general clause

**Absence is a value, and a parser that folds it into a negative has answered a question it was
never asked.** Gotcha #53 says an empty 200 is a response shape rather than an absence; this is the
same error one level in, where an absent field and a field saying "no" arrive at the reader as the
same byte. Whenever code converts a possibly-missing input into a two-valued answer, the missing
case needs its own third value — or it will be reported, in perfect confidence, as the safer one.
