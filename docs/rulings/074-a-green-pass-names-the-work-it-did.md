# RULING 074 — a green pass names the WORK IT DID, never the time it took; and a bar is set under a re-derived ceiling, never above a quoted one

date: 2026-08-17
author: Fable
issues: #1866, #1545

## The ruling — Fable's two clauses, verbatim

Issued as item 1 of the FABLE DIRECTIVE of 2026-08-17, on the LAT-P060 acceptance:

> The refresh-ahead hole (warm hits that extend nothing while reporting warmed: 40/40) is banked
> into the instruments-that-lie taxonomy. The ceiling re-derivation is the house standard: a bar
> four under a real ceiling beats one four above a phantom.

Two clauses, and they are one ruling because they are the two halves of the same discipline: the
first governs what an instrument may claim it did, the second governs what you are allowed to
compare that claim against.

## Clause 1 — the refresh-ahead hole joins the taxonomy

`/typeahead`'s warmer ran a full 40-query pass, reported `terminal: complete, warmed: 40/40`, and
**rebuilt nothing**. The mechanism is three lines of control flow: `routes/events.py` returns the
cached body at `:4038` *before* it reaches its own `setex` at `:4780`, so a cache entry lives 45 s
from its last **REBUILD** and a warm read resets no clock. A warming pass that HITS is therefore a
no-op that cannot tell it was one — every query it asked for came back, so by its own definition it
succeeded.

Measured at LAT-P060 over 50 invocations / 1,438 s: **12 beats ran a complete 40-query pass in
~0.65 s** and extended nothing. `warmed: 40/40` was true. It was also worthless.

**The obligation this creates: a completion metric counts WORK PERFORMED, not requests answered.**
`warmed` was a count of calls that returned. The replacement — `rebuilt` and `fresh` as separate
fields — is a count of cache entries whose TTL actually moved. An instrument that cannot distinguish
"I did the thing" from "the thing did not need doing and I also did not do it" is reporting on its
own control flow, not on the world.

Sibling of the family it now joins, and the same inference in every one — **a real, well-formed,
honestly-produced signal handed to the reader in exactly the place the answer belongs, and it is the
wrong signal**:

- **#49** — a Sentry `count` is LIFETIME, read as recent.
- **#53** — an empty 200 is a response shape, not an absence; Kalshi answers `trades: []` identically
  for "purged" and "never traded". Ten weeks of a recovery rail recorded SUCCESS on 500 fetched /
  0 created.
- **#54** — `cmd | tail` reports TAIL's exit code, so a gate that never ran reports success.
- **#124** — `$?` belongs to the last thing that ran.
- **#135** — a truncated `xcodebuild test` reads exactly like a pass; a missing verdict read as a
  negative finding.
- **Ruling 071** — a malformed lock reads as HELD; an instrument reporting two incompatible things
  at once is not partially informative, it is uninformative.
- **Ruling 072** — a fixture that agrees with the bug is the bug.

## Clause 1's third obligation, found by LAT-P061 within one window of the ruling being issued

This is not exposition. It is a live specimen, and it would have produced a false PASS on the very
prediction table this ruling was issued to protect.

LAT-P060's §8 registered prediction row 4 reads: **"no-op 0.6–0.9 s band 12 → 0; a surviving band ⇒
threshold too low."** The band was written down as a **duration interval**, because that is how the
no-op passes presented themselves when they were discovered.

LAT-P061 re-read the same pre-fix production task, code **unchanged**, 50 invocations / 1,418 s:

| band | LAT-P060 (pre-fix) | LAT-P061 (pre-fix, same code) |
|---|---|---|
| lock skips `<100 ms` | 25 | **12** |
| **no-op `0.6–0.9 s`** | **12** | **0** |
| **no-op `~300–400 ms`** | — | **13** |
| real passes `>1 s` | 13 | **25** |

**Row 4 grades PASS on code that never changed.** The no-op band did not disappear; it MOVED, because
its duration is 40 sequential Redis GETs and that is a latency measurement of Redis, not a property
of the warmer. A grader reading row 4 literally in the next window would have scored the
refresh-ahead fix as working before it was deployed.

**So the obligation generalises: a behaviour is defined by what it DID, never by how long it took.**
A band, a threshold or a bucket that stands in for a behaviour is a proxy, and a proxy drifts under
every load condition that was not present when it was calibrated. Row 4's correct form is
`rebuilt == 0 on a pass reporting complete` — a predicate over work performed, which cannot move
when Redis gets faster.

The corrected table is written into `docs/audits/latency/lat-p060-warmer-arithmetic.md` §8 in the
same commit as this ruling, because a registered prediction that is known to be ungradeable and left
standing is worse than no prediction at all.

## Clause 2 — the ceiling is re-derived, and the bar goes UNDER it

LAT-P060 was handed a target of **≥20 of 24** against a ceiling of **16 of 24**. The 16 rested on a
single structural claim — *"with a 3-round probe, round 0 can never be pre-warmed"* — which had been
stated once and quoted thereafter. The lane re-derived it instead of quoting it, called the claim a
p≈0.15 coincidence, and then **measured run 1's round 0 coming back 8 of 8 PRE-WARMED.** Head
membership measured **8 of 8**, not 7. The real ceiling is **24**.

The bar did not move. Its relationship to reality inverted:

|  | ceiling | bar | relationship |
|---|---|---|---|
| as staged | 16 (phantom) | ≥20 | **four ABOVE an unreachable maximum** — unfalsifiable, guaranteed to fail, and a failure would have proved nothing about the fix |
| as re-derived | **24** (measured) | ≥20 | **four UNDER a real maximum** — demanding, reachable, and a miss is informative |

**A bar above the ceiling is not a strict standard; it is a broken instrument wearing the costume of
rigour.** It cannot be met, so it cannot discriminate, so the result it produces carries no
information either way — which is the identical defect as clause 1, relocated from the measurement
to the target.

**The house standard, stated as a procedure:** before registering a criterion, derive the maximum the
instrument can physically report **on this run, with this probe, against this corpus**, and show the
derivation. A ceiling inherited from a previous window's prose is a quoted number, and ruling 069
already governs quoted numbers: **measure, never quote.**

Corollary, because it is the part that costs something: **re-deriving a ceiling can move the bar
against you.** Here it made a 20/24 criterion genuinely hard where it had been merely impossible.
That is the ruling working, not a reason to skip it.

## Application

- Any completion/coverage/health metric asserting success must be able to answer **"what changed
  because of me?"** — `rebuilt`, `written`, `linked`, `resolved` — and not merely **"did my calls
  return?"** A `complete` verdict alongside a zero work count is a defect to surface loudly, which
  is what `app/utils/task_verdict.py` exists for.
- Any registered prediction (ruling 050) states its ceiling **and the derivation of that ceiling**,
  taken in the same window as the registration.
- Any prediction row whose subject is a behaviour is written as a **predicate over work performed**.
  Duration bands, byte ranges and count windows may appear as corroboration; they may not be the
  criterion.

## Sibling rulings

- **050** — register the prediction before the read.
- **064** — the sandwich is permanent doctrine; one read is never a number.
- **066** — a deferred read owes a receipt with a named exit condition.
- **069** — the ledger is the allocator; measure, never quote.
- **071**, **072**, and gotchas **#49 / #53 / #54 / #124 / #135** — the instruments-that-lie family
  this ruling is banked into.
- **073** — CORPUS-MOVED. Its subject is the denominator moving under a frozen probe; this ruling's
  subject is the numerator being counted wrong and the maximum being quoted wrong. Same programme,
  three different places for a comparison to go bad.
