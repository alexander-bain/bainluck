# RULING 056 — Unmeasured is not ineffective

date: 2026-08-14
author: Alex
issues: #993 #1843 #1861 #1545

## The ruling

When a change ships on a measured surface and the metric does not move, the ledger records that
**the instrument could not see it**. It does not record that the change did nothing.

Those are two different claims, and a null read supports **only the first**.

The second claim — "ineffective" — requires an additional fact nobody has usually established:
that the probe set can **discriminate that class of change**. Absent a demonstration of
discrimination, "no movement" is a statement about the instrument, and it must be written as one.

This is standing **reading law for the §5 ledger** in `docs/search-scoring-spec.md`, and for any
successor ledger this program keeps. It binds the reader, not just the writer: a row that says
"no movement" is not license to conclude the change was worthless.

## The ruling carries a fix, not just a filing

A distinction that only ever produces a caveat is a caveat. This one produces an instrument.

The gold set gains an **OUTCOME-EVIDENCE probe class**: probes whose correct answer depends on an
outcome sitting **outside the market's top-3 display cut**. That is precisely the class `-44`
(#1843) changed, and precisely the class the 46 probes could not see.

Two scoping constraints, both deliberate:

* It is **gold-set maintenance** — the Q322 family — **not a ranking change.** Nothing about the
  scorer moves, so it does not consume a solo deploy slot under ruling 046.
* It must **not perturb the historical cohort.** The entire §5 ledger is written against a 46-probe
  registry graded 44-wide. Adding probes into that split would silently move the denominator and
  break every prior read's comparability — which would be a measurement defect committed in the
  name of fixing one.

## Why — the occasion

`-44` deployed **alone** as v3807, exactly as ruling 046 requires. It carried a real ranking change:
#1843 stopped the display truncation from truncating the *ranking evidence*, so a market that owns
the answer on its fourth outcome stopped losing to unrelated substring accidents.

The read came back **38/44, MRR 0.8696** — identical to v3806. Taken twice, ~45s apart, with
**byte-identical per-probe dispositions** against the previous deploy. Not merely the same total:
the same answers.

The tempting reading was "the change did nothing." The supported reading was "**46 probes, none of
which turn on a non-top-3 outcome, returned the same answers**" — which is a fact about the probe
set. Filed as #1861 rather than absorbed as a shrug.

## The corollary — an unarmed control that comes out clean

`-44` also functioned as an **unarmed control**: a change on the measured surface that moved
nothing, with no HALT attached because none had been declared in advance.

It came out clean. That **raises** the value of firing the armed control (`-45`, ruling 050), it
does not lower it. A clean unarmed read corroborates the attribution model that the armed read is
designed to test deliberately — so the argument "we already saw a null read, skip the control" is
exactly backwards.

## What this does not license

It does not license calling every null read an instrument failure. The distinction cuts both ways:
once a probe class has been **shown** to discriminate a change class, a null read on it IS evidence
of ineffectiveness, and must be written that way. The obligation the ruling creates is to know
which case you are in — and, when you do not know, to say so and go build the probe.

## Siblings

* [046](046-a-stacked-change-is-measured-on-its-own-deploy.md) — the solo-deploy rule that made `-44`'s null read
  attributable at all. Without it there would be nothing to interpret.
* [050](050-a-control-that-cannot-fail-is-not-a-control.md) — take the null-result read; this
  ruling governs how to write down what it says.
* [052](052-measure-the-instruction-before-you-obey-it.md) — measure the instrument, including when
  the instrument is your own probe set.
