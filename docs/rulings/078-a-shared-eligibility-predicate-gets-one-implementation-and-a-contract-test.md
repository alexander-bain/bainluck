# RULING 078 — A shared eligibility predicate gets ONE implementation and a contract test

date: 2026-08-17
author: Fable
issues: #1924, #1933, #1779, #1947

## The ruling

When two or more surfaces must agree about whether something is **eligible** — live, disputed,
absorbable, showable, gradeable — that agreement is expressed as **one implementation, imported by
every surface, with a contract test that fails when a surface stops importing it.**

Three things are required, and the third is the one that keeps being skipped:

1. **One implementation.** Not a rule in a docstring, not the same `if` written carefully in four
   files. A function, in one module.
2. **Every surface calls it.** A predicate with zero callers is a document. A predicate with
   *some* callers is worse than a document, because the surfaces that do call it make the ones
   that do not look intentional.
3. **A contract test that asserts the CALL, per surface, by name** — and asserts it as a call, not
   as a substring of the source. It must fail when a surface is unwired. If unwiring a caller
   leaves the suite green, the predicate is shared by convention, and convention is what this
   ruling exists to replace.

## Why — four instances in three windows, all the same shape

The candidate was raised in report 363 and earned itself again twice more before it was banked.
Every one is a *correct* rule that some surface did not consume:

| # | the rule | who was behind |
|---|---|---|
| **#1924** | live-eligibility | web behind iOS |
| **#1933** | the same class again | native behind web |
| q363 | `market_identity_disputed` | existed as prose; made executable |
| **#1779** | `enforce_live_requires_start` | **imported by NOBODY** while the surface it governed served four wrong MLB cards, live 40–51h before first pitch |

The fourth is the specimen worth keeping. `app/utils/lifecycle.py` opens with *"one canonical rule
for every surface that labels a card/event/concept live"* — the intent was stated, in the file, at
the top — and the function had zero importers. The rule was not wrong, not out of date and not
disputed. It simply was not called, and nothing anywhere could notice.

**A rule with no consumer is a document, and a document cannot fail a build.**

## The third clause is not decoration — it failed within the hour

Queue 365 wired an in-transaction ruling-048 guard into four destructive rails and wrote exactly
the contract test this ruling requires. It asserted:

```python
assert "assert_absorbable_now" in ast.get_source_segment(source, fn)
```

Then the mutant that DELETES the call from the drain left it **green** — because the name still
appeared in the docstring one line above, which the same author had just written to explain the
call. A guard test satisfied by prose *about* the guard is the dead-oracle class arriving inside
the mechanism built to prevent it.

So clause 3 is specific on purpose: **assert on a call node.** Walk the function's AST, collect
`ast.Call` targets, and require the name among them. And prove it by running the mutant, because
this failure is invisible to review — the test reads correct, and it was.

## Relationship to the other instrument rulings

Sibling of 071 (a malformed lock reads as held), 072 (a fixture that agrees with the bug is the
bug), and gotchas #53 / #124 / #135. All five are one family: **an instrument reporting
confidently about something it never measured.** This one names the specific case where the
unmeasured thing is *whether the rule is plugged in at all*.
