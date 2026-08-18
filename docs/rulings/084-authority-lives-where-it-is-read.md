# RULING 084 — Authority lives where it is read

date: 2026-08-18
author: Fable
issues: #1951 · #1948 · #1658 · #1860 · #1909

**A rule's authoritative statement must sit at the point the rule is CONSUMED. Any copy of it
upstream of the read is a second policy, and a second policy drifts silently.**

Three UX cycles each raised one candidate and none was banked. They are not three rules. They
are one rule with three faces, and the third instance is what makes that visible:

1. *(cycle 89)* **A threshold an operator can override must resolve at CALL time, never as a
   default argument.** The flow sentinel's Redis overrides reached the evidence block and never
   the verdict, for as long as they had existed — the default was bound at import, so the
   authority sat in the function signature while the consumer read a value nobody could change.
2. *(cycle 90)* **A rule with more than one implementation needs a test that NAMES every copy,
   and the copy that grades the others must never be the permissive one.** Three admission
   predicates agreed with each other and all three were wrong about one arm; the grader was the
   loosest of them, so the disagreement had nowhere to surface.
3. *(cycle 91)* **An assertion may only count the population its ID names.**
   `page_view_exactly_once` matched on HOST while `recordTelemetry` deliberately discards query
   values — so the matcher never had access to the `en=` that distinguishes GA4's four beacons
   from the one page view the assertion's own name promises. Four requests, one page view, and
   an exact-1 guard failing on arithmetic it could not see.

## The reference implementation

**UX-P094's `contracts/feed_card_admission.json` (#1951) is what honoring this looks like.** Not
a shared predicate — three languages means no import can span them — but the shared **DECISION**,
as data: 40 rows, every card type and every arm, with web and the sentinel driven through all 40
and native source-asserted. Four guards make a fourth copy a build error rather than a discovery.

## The quotable justification

**The fold found a live defect that three agreeing implementations had hidden.** Of five
malformed-envelope shapes, Python and native suppressed all five and **web THREW on two** —
`data` absent and `data` null — reading `item.data` through an erased `as` cast inside a
`.filter()` in a render memo. A throw there does not drop one card; it blanks the MAIN REGION.
That is #1909's exact failure mode, in the predicate whose stated property is that it *fails
closed*.

Three implementations that agree are still three policies. Agreement is not a shared decision;
it is a coincidence that has not been tested yet. The fold is what turns the coincidence into a
fact, and it paid for itself in its first run.

## The fourth instance, same day

**#1948** is this ruling in the cache tier, and it is worth recording because it looks nothing
like the other three until you name it. `write_payload` writes two Redis slots — a 60-second
primary and a 24-hour mirror. `routes/event.py` reads both, which is why the beat's own comment
can say the 5-minute warm cadence is safe: *"the route serves the 24h mirror on a miss in
~0.44s."* True — of the route. Then UX-P089 made the feed's concept-leader resolver **cache-only
with no mirror read**, and the cadence's safety argument silently stopped covering its second
consumer.

The authority on what is warm lived where the ROUTE reads. The feed read somewhere else, and
sixteen cards a session shipped with no probability for three cycles while the number sat one
key away. Measured on production 2026-08-18, twenty-one seconds apart, same bytes:
`live` → 4/4 leaders, `stale_ok` → 0/4.

## How to apply it

- A constant a consumer depends on is declared **beside that consumer's read**, with its reason,
  even when a producer already has one. Where two must agree, they share the decision — not the
  ingredient (ruling 021), and not merely a comment claiming they agree.
- When a shared component changes what it reads, **re-check every claim made about it
  elsewhere**. #1948's whole cost is one comment that stayed true for one caller.
- A guard on this must **name every consumer by path and symbol**, and be mutation-proved. A
  registry that cannot fail is a green light wired to no sensor.
