# RULING 081 — A clause that pays out inside its own banking window is doctrine, not a candidate

date: 2026-08-18
author: Fable
issues: #1947, #1924, #1933, #1779

## The ruling

Ruling 064 set the bar for promoting a practice to permanent doctrine: **three payouts, in three
distinct failure classes.** One payout is a technique; three is a property of the method.

This ruling adds a second, rarer qualifying condition:

> **A clause that pays out INSIDE THE WINDOW THAT BANKED IT is doctrine immediately.**

**Ruling 078's clause 3 — "assert on a call node, not a substring of the source" — is therefore
permanent doctrine as of the window that wrote it.** It is not on probation, it does not need two
more instances, and it is not open to being relaxed to a string match "for now".

## Why one payout is enough when the payout is same-window

The three-payout bar exists because a rule invented after one incident is usually fitted to that
incident. Time and distinct classes are how you tell a principle from a post-hoc story.

Same-window payout defeats that objection on different grounds. Queue 365 wrote ruling 078,
including the clause requiring a contract test that asserts the CALL per surface. It then wrote
exactly that test:

```python
assert "assert_absorbable_now" in ast.get_source_segment(source, fn)
```

...and the mutant that DELETES the call left it **green** — because the name still appeared in the
docstring one line above, which the same author had just written to explain the call.

That is the strongest evidence a rule can produce about itself:

1. **The author knew the rule.** They had written it minutes earlier, in its final wording.
2. **The author was trying to comply.** This was not a skipped step; it was a sincere attempt.
3. **It failed anyway**, and failed GREEN — invisible to review, because the test reads correct.
   It *was* correct, as prose.

A rule that its own author violates while holding it in mind is not a rule that needs more
instances to prove it is load-bearing. The instances would only re-demonstrate that intent is not a
mechanism. **The mistake was never in the understanding** — the same sentence ruling 022 was
written under.

## The operative content, restated so it cannot be softened

- Walk the function's AST, collect `ast.Call` targets, require the name among them.
- **Run the mutant.** A guard test that has never been observed to fail is a guard test whose
  failure mode is unmeasured, and this class is specifically invisible to reading.
- Never satisfy a guard with a substring of source text. Docstrings, comments and the guard's own
  explanatory prose all live in that string.

This generalizes past AST: it is the dead-oracle class arriving inside the mechanism built to
prevent it. Anywhere a check is satisfied by *text about* the thing rather than the thing, the
check is decorative. Ruling 044's rendered-green and this are the same animal.

## Reading note

This does not lower ruling 064's bar for the ordinary case, and it is deliberately narrow: the
payout must be **inside the banking window**, on the **clause itself**, against a **sincere
attempt to comply**. A rule that merely feels obviously right on the day it is written does not
qualify — every rule does.
