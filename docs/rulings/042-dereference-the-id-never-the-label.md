# RULING 042 — Dereference the id, never the label

date: 2026-08-13
author: Fable, from the lane1 /triage 342 retraction
via: three specimens in one day, one of which reversed a published conclusion
issues: #1796 · #1811 · #1798 · #1779 · #1817

> **When a check can reach either a label or an identifier, it must reach the identifier. A label
> is a claim ABOUT the thing; the id IS the thing. A check built on a label measures whoever
> assigned the label, and reports that measurement as though it were about the world.**

## What produced it — three specimens, 2026-08-13

### 1. The `llm_league` numerator (#1796)

The schedule-completeness sentinel's whole purpose is a denominator we do not own. Its first
measurement of the Aug 10–12 MLB window selected our side with `llm_league = 'MLB'` — an
LLM-assigned label — and reported **+2 / +5 / −2**: an over-count, and therefore that #1779 had
been repaired and overshot.

Selecting by the **sport foreign key** instead:

| ET day | truth (statsapi) | by sport FK | by `llm_league` |
|---|---|---|---|
| 2026-08-10 | 10 | 10 | 12 |
| **2026-08-11** | **15** | **6** | **20** |
| 2026-08-12 | 15 | 8 | 11 |

**Aug 11 is 9 MISSING — the incident's own number, reproduced exactly.** #1779 was never repaired.
The 14 apparent extras were 11 real Triple-A games wearing a wrong LLM label, one Polymarket
pseudo-event, and two Mexican-League games mis-sported.

The label did not merely add noise. It **inverted the finding**: a mislabelled row inflates the
count while a missing row hides behind the inflation, so a shortfall of nine presented as a surplus
of five. A published conclusion was retracted on the issue.

### 2. The names-only MISATTACHED check (#1798, #1779)

The team-binding defect is rows whose `home_team_name` / `away_team_name` are **correct** while
`home_team_id` / `away_team_id` point at another club. 153 sides measured across the 2026 MLB
season. Every name-based check passes all of them — which is why nothing caught it for months, and
why the repair's detection was specified to dereference the FK rather than compare strings.

The sentinel independently surfaced five such rows on *future* games hours before the repair rail
ran, from a different code path, and recorded `names_agree` on each finding so the filed issue says
outright that a name check passes the row.

### 3. The drifted event integers (queue 341)

Queue 341 carried the deadline as two literal ids: *"`15191702` (Aug 16)"* and *"`15194469`
(Aug 18)"*. In production those events are **Aug 14** and **Aug 19**, and the real Aug 16 Boston
fixture is **`15198424`** — an id the queue never names.

A hand-copied integer is a label too. It was true when written and silently stopped being true;
the obligation was owed to *the games*, and checking the integers would have discharged it against
the wrong ones. The window that caught it re-derived from the schedule and verified all four Red
Sox games in the range, rather than trusting the two numbers it was handed.

## The shape they share

In each case a cheap, human-readable, *derived* handle sat next to an authoritative one:

| derived handle | authority |
|---|---|
| `llm_league` (an LLM's opinion) | `sport_id` FK |
| `home_team_name` (a string) | `home_team_id` FK |
| an id transcribed into a queue file | the live row |

The derived handle is always more convenient, always more readable, and always the thing that is
wrong first — because it is a **copy**, and copies drift while references cannot.

## Why the failure mode is specifically dangerous

A label-based check does not fail loudly. It returns a number, and the number is about the
labeller. Specimen 1 is the sharp case: the check reported the *opposite sign* of the truth and
would have been believed, because a completeness check returning "we hold more than exist" reads as
reassuring. **A wrong answer that flatters is not detected by re-running the check.**

This compounds with the absence problem the sentinel exists for. An absence has no field to be
wrong; a mislabel has a field that is wrong but not on the row you are looking at. Together they
make a shortfall look like a surplus.

## What this obliges

1. **Any check whose result is a count of a population must choose that population by identifier.**
   If only a label is available, the check reports on the labeller and must say so in its output —
   not in a comment, in the output.
2. **Any comparison that could dereference must dereference.** Names are corroboration, never the
   test. Where a check compares names because that is all it has, it records that fact on each
   finding, as the sentinel's `names_agree` does.
3. **An identifier transcribed into a document is a label from that moment on.** Queues, briefs and
   rulings may carry ids for orientation, but the executing window re-derives from the live source
   and reports the drift as a finding (ruling 030's census rule, applied to identifiers).
4. **When a fix hinges on this, put the reasoning in the code**, not the commit message.
   `load_our_events` carries it so that "simplify to `llm_league`" is visibly a regression.

## Where it does NOT apply

An id is only authoritative for what assigned it. Ruling 031 already governs the case where two
providers disagree: assigned identity beats inferred, but a *provider's* id names that provider's
referent — which is exactly why #1811's fix re-links by the Kalshi ticker rather than trusting our
own `event_id`. Dereferencing the wrong id is not an improvement on reading a label.

And an id you fabricated is a label. R3's id-less work found that 73% of un-individuated rows carry
a `commence_time` that is a `datetime.now()` ingest stamp rather than a published start — a value
with an authoritative *shape* and no authority behind it (#1817). The discriminator that made R3
workable is precisely the test of whether the field was assigned or invented: a published start is
whole-minute (99.2% of individuated rows), a fabricated one essentially never is.

## Related

[030](030-census-runs-before-the-staged-work.md) — the census runs before the staged work; this is
its identifier-shaped corollary.
[031](031-assigned-identity-beats-inferred.md) — assigned identity beats inferred; 042 is what to do
when both an assignment and a description are in reach.
[038](038-circular-authority-is-never-tier-3.md) — a grade computed from our own data is never
tier-3; the same suspicion of self-referential authority, one layer up.
