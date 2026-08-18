# RULING 021 — Two graders reading one input must share the DECISION, not just the predicate

date: 2026-08-10
author: Fable
issues: #1648 · #1525 · #1600

**The ruling, on #1648 P1:**

1. **Allowance expiry moves to RUN level.** A declared navigation-abort allowance must fire
   *somewhere* in the run; one that fires nowhere is red. This preserves #1525's expiry
   property exactly — only its scope changes.
2. **Both graders import the predicate AND the allowance set from one shared module**, so a
   0-vs-1 disagreement on one input becomes structurally impossible.
3. **`is_feed_request` (Shape A) remains never-excusable, asserted in both.**
   **AMENDED 2026-08-18 — see "Amendment: the instrument-induced carve-out" below. Do not
   quote this clause without it.**
4. Apply to `deploy-smoke` first (the daily pack, red on three commits that day), then
   `event-page`.

## Why the scope had to move

`allowedNavigationAborts` was mandatory-fire *per journey*: a declaration matching nothing
failed that journey, which is what stopped an excuse outliving its reason.

That is right about excuses and wrong about **racy** facts. `discover-smoke` never clicks — it
calls `page.goto` and waits — and Next auto-prefetches in-viewport links, abandoning one as the
feed re-renders. On 2026-08-10 the desktop journey saw one cancelled prefetch and the mobile
journey saw none, **in the same run**. Declaring the allowance per journey would therefore have
converted a flaky red into a *different* flaky red, on whichever viewport happened not to race.

**The design had no way to express "expected, but not guaranteed."** A run is the smallest
scope at which a prefetch race is a stable fact, so that is where firing is graded.

## Why sharing the predicate was not enough — the part worth remembering

#1649 already imported `isNavigationCancellation` into the per-error grader precisely to stop
the two graders drifting. They drifted anyway, and the manifest from run 31428469455 says so in
a single record:

```
"checked_clean": [ "network.failure_volume_within_policy (0 failed request(s) ...)" ]
"assertions":    [ { "assertion_id": "network.no_unexpected_failures", "ok": false,
                     "detail": "1 failed request(s): ...?_rsc=... net::ERR_ABORTED" } ]
```

**Zero and one, one input, one manifest.** Sharing the predicate left each grader owning its own
*decision* built from it: the volume grader excluded every cancellation unconditionally, the
per-error grader excluded one only behind a declaration. Two rules, one fact.

The general form: **when two consumers must agree about the same input, the unit to share is
the decision, not the ingredient.** A shared predicate under two policies is still two policies.

The drift also ran the other way and nobody had noticed: the volume grader carried **no feed
guard at all**, so an aborted `/api/feed` — the one abort that is a real open defect, invisible
to the backend's own metrics — was silently dropped from its count. Hence clause 3, and hence
"asserted in both" rather than "asserted".

## Cost of leaving it

A rail that fails falsely on its daily sweep is worse than a rail nobody reads: it teaches its
readers that red means nothing. `deploy-smoke` was red on production at three commits on
2026-08-10, including the 07:40 UTC scheduled run, against a completely healthy page.

## Implementation note — clause 1 holds for STRICT allowances only, and why

Recorded here because a future reader must not take "expiry moves to the run" as unconditional.

While this was being built, **INT-034 landed an independent fix for the same red** (`a4275e07`),
introducing a measured `{ match, intermittent: true, issue }` allowance form. Its measurement is
the reason clause 1 could not be applied literally — all at frontend SHA `f6a40849`,
pack `deploy-smoke`, against production:

| run | `discover.route` desktop | mobile | `discover.landing` |
|---|---|---|---|
| 31428469455 | 1 abort | 0 | 0 both viewports |
| 31431570162 | 1 abort | 0 | 0 both viewports |
| 31431775245 | **0 aborts (run PASSED)** | 0 | 0 both viewports |

**One run in three carried no abort ANYWHERE.** A mandatory run-level fire would have turned
that clean run red — so run-level expiry alone does not fix a racy phenomenon. It fixes a
*deterministic* one that happens to land in a different journey of the same run, which is a real
but different problem.

So the shipped shape is:

- **Strict allowances** — expiry moves to the RUN, exactly as ruled. Firing in one journey is
  enough; firing nowhere is red.
- **Intermittent allowances** — exempt from expiry, as INT-034 established, and required to
  carry an `issue` so they stay attributable and retirable.
- **Clauses 2 and 3 applied in full**, and both were genuinely missing: master still defined the
  allowance decision locally in `journey.js`, and its volume grader still had **no feed guard at
  all**, so an aborted `/api/feed` was silently dropped from that count.

The general lesson survives intact, and is really the point of this ruling: **the scope at which
a fact is stable is the scope at which it should be graded.** For a deterministic abort that is
the run; for a racy one, no scope makes "it must fire" true, and the honest move is to say so in
the declaration rather than to pick a threshold.

---

## Amendment: the instrument-induced carve-out (Fable, 2026-08-18, resolving #1908 M2)

**Clause 3 is amended: the abort is excusable when the INSTRUMENT caused it; the AFTERMATH is
graded, always.**

### The deadlock this resolves

UX cycle 91 routed M2 for a ruling rather than patching it, because both sides were correct as
written and applying either alone breaks the other:

- the consent pack's **method** is to navigate mid-load — grant, revoke, reload, open a second
  tab. Cancelled in-flight requests are its exhaust, not its findings.
- the rail's **rule**, clause 3 above, is that a cancelled `/api/feed` stays graded.

**#1667 is the collision, and the best specimen either side could ask for:** a first-party
aborted `/api/feed`, in a journey whose own navigation aborted it. Under clause 3 as written it
is a permanent red the product cannot fix; loosen clause 3 and the one abort class that is
invisible to the backend's own metrics stops being watched.

### The amendment

An aborted `is_feed_request` may be excused **only** when all four hold:

1. **Attributable.** The abort is caused by an action the harness itself issued — a
   `page.goto`, a reload, a context switch — recorded with the action that caused it. "It
   happened during a journey that navigates" is not attribution; the causing action is named.
2. **Declared.** It carries a declaration in the shared allowance set (clause 2 still governs —
   one decision, both graders), so an excuse remains visible and retirable.
3. **The aftermath is graded, and the aftermath assertion may not itself be excused.** After the
   instrument's navigation settles, the journey MUST assert that the main region reaches a
   rendered, non-blank state. That assertion is mandatory-fire in the strict sense of clause 1:
   an excused abort with no graded aftermath is not a carve-out, it is a deletion.
4. **Settled, not instantaneous.** The aftermath is measured after the region stops loading, on
   a raw measurement rather than a spec-side threshold. A grader that photographs a skeleton is
   measuring its own timing (#1663/#1909's last criterion, fixed in UX-P094).

### Why this keeps the property clause 3 exists for

Clause 3 was never really about the request record. It is about **#1909: a blank main region a
user actually sees, produced by a feed fetch that failed in a way the backend cannot see.** The
abort is the *proxy*; the blank region is the *defect*.

When the harness caused the navigation, the proxy carries no information about the product — of
course the request died, the instrument killed it — while the defect is still perfectly
observable one step later, in the state the page settles into. So the amendment does not weaken
the guard; it **moves it off a proxy that the instrument controls and onto the outcome that the
user experiences**, which is the only reading under which the guard means anything in a pack
whose method is to navigate mid-load.

The direction of travel matters and is stated so it cannot be quoted the other way: an abort
**nobody instrumented** is unchanged — never excusable, asserted in both graders, exactly as
ruled on 2026-08-10.

### The pattern being priced in

Three consecutive cycles resolved a consent finding to the **instrument** rather than the
product (#1860's oracle, #1909's 40-character threshold, #1658's host-scoped counter), and this
is the fourth. A measuring apparatus that perturbs its subject is not a defect in the subject.
The correct response is never to loosen the assertion — every one of those four was fixed by
measuring the right thing, not by measuring less strictly. This amendment is the same move at
ruling level: keep the standard, correct the thing it is pointed at.

Owners disposed under this amendment: **#1662, #1668, #1783, #1667**.
