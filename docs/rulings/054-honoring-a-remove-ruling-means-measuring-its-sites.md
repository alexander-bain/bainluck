# RULING 054 — Honoring a remove-ruling means measuring its sites, not counting its lines

date: 2026-08-14
author: Alex
issues: #1854

A ruling that says **"remove X"** is a ruling about the **defect**, not about the
line count. Executing it means:

1. **Enumerate every producer site.** Not the one the issue names — all of them.
2. **Remove the ones that are actually defective.**
3. **Keep the coherent ones, with the reason written in place.** A site that is
   correct today and gets deleted anyway teaches the next reader nothing except
   that the field was unpopular.
4. **Convert the ruling into a recursive invariant over the served payload**,
   not a deleted line. The guard has to fail when someone re-introduces the
   defect somewhere the original ruling never looked.

Ratified as built on UX-P077, and the ratification is the ruling:

> *I said remove; you measured five producer sites, found only two defective,
> kept three that bound their own number with reasons written, and made the
> guard a recursive invariant instead of a deleted line.*

## WHY

**Obeying a ruling reproduces its letter; honoring one delivers the state it was
issued to reach.** The letter here was "remove `probability_range`". The state it
was issued to reach was "no reader is ever shown a range that excludes the number
sitting next to it". Those come apart immediately: three of the five sites emit a
range beside a *sportsbook* number that the range genuinely bounds. Deleting
those would have satisfied the letter and improved nothing, while removing
information that was correct.

And the letter is *weaker* than the state in the direction that matters. A
deleted line stops the two known-bad sites. It does not stop the sixth site
somebody adds next month, and it leaves no artifact explaining why the field went
away — so the sixth site gets added in good faith by someone who never saw the
ruling. **An invariant written over the served payload is the ruling in a form
that outlives the person who read it.**

This is the same shape as ruling 052 (measure the instruction before you obey it)
and ruling 030 (the census runs before the staged work), arriving from the third
direction: 030 says the census may re-decide the work, 052 says an impossible
instruction is measured rather than performed, and 054 says a **possible**
instruction is still measured, because the ruling's target is a state of the
world and the instruction is only one route to it.

## The obligation this creates, stated plainly

A lane that keeps a site the ruling said to remove is **deviating**, and owes:

- the **measurement** that says the kept site is coherent (not an argument that
  it probably is),
- the **reason written at the site**, in the code, where the next reader is,
- and the deviation **declared in the report**, not discovered in the diff.

A kept site with no measurement and no written reason is not this ruling. It is
the thing this ruling is most likely to be misquoted to excuse.
