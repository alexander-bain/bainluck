# RULING 031 — Assigned identity beats inferred, and identity precedes the page

date: 2026-08-12
author: Fable
via: cycle-64 acceptance, ratified
issues: #1744 · #1741

> **(a) An entity's identity — what it IS, and what it is an EDITION OF — is assigned in config
> and read. It is never inferred from the shape of a slug, a name, or a ticker.**
>
> **(b) When a page needs an identity that does not exist yet, the identity queue is staged
> FIRST and the page queue consumes it. The page is the smaller half.**

## What produced it

#1744 was staged as a page queue: "one standing-competition page per entity — The Masters, the
World Cup, UFC as a promotion." The sizing pass found the page had **nothing to render**.

There was no standing-competition model at all. All five `HUB_CONFIGS` rows are *sport* hubs, not
competitions. `entities` has no `parent_entity_id`. No concept adapter config carries a parent
slug. Nothing on disk modelled *"an edition of"* — so the issue's own flagship acceptance case,
the between-editions T0, had **zero entities to be empty for**.

What existed instead were three workarounds, each inferring a relationship the config never
stated, and **all three disagreeing**:

1. awards keep a standing slug and parse a year suffix back off it — the inverse of a parent
   pointer;
2. a cycling alias hard-pins a standing name to ONE edition, so the standing name goes stale the
   day that edition ends;
3. golf uses year-less slugs, in a file that also writes `masters-2027` and `ryder-cup-2027`.

## Why inference is the defect and not just the mechanism

The three disagree **because none of them is wrong locally.** Each is a reasonable reading of the
same undeclared relationship, which is the signature of the class: inference produces a rule that
is subtly wrong everywhere at once and belongs to nobody, so no single change can fix it and no
single owner is responsible for it. An assignment is one line, in a diff, with an author.

And the cost is not hypothetical. Measured in production 2026-08-12: `event:golf:masters-2027`
and `event:golf:ryder-cup-2027` — the keys our own calendar declares — **404**, while the
year-less `event:golf:the-masters` and `event:golf:ryder-cup` serve. `horizon_sentinel` decides
"has a page" by resolving `concept_key`, so each of those is a **P1 needs-page alarm already
scheduled to fire** (T-30: 2027-03-09 and 2027-08-18) about a page that exists. An inference gap
does not stay a data-modelling abstraction; it turns into a false alarm with a date on it.

**The tell to look for:** if a test written against today's rows would pass for an implementation
that inferred, the test is not testing the doctrine. Mutate the assigned field and prove the
resolution follows it (gotcha #121's shape, applied to config rather than constants).

## Why (b) is a separate clause

The ordering is not a nicety, it is what keeps a page queue honest. A page built before its
identity source infers one on the spot — inside a route, in TypeScript, per surface — and the
fourth disagreeing mechanism is born in the place hardest to notice it. Stage identity, prove it
with the smallest visible consumer that needs it, then build the page on top.

The build ORDER of the entity-pages epic is unchanged by this. Its substance is deepened: step 2
is (a) a competition identity source, then (b) the page.
