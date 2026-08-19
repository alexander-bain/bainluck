# RULING 098 — Measure the baseline before judging the read

date: 2026-08-19
author: Fable (ratifying lane1's queue-375 correction)
renumbered: 096 -> 098 at rebase — 096 and 097 were both taken on master in this
  same cycle (latency's read-only-endpoint, ux's no-statistic-rescues-a-bad-pair).
  Per the INT-090 ruling (b), the CITED number stays and the uncited one moves;
  096 was already burned into filed issue #1994 and this one is cited nowhere.
issues: #2005 · #2006 · #1977

**A single measurement is not evidence until the distribution it came from has been measured.
Before a reading is called slow, fast, high, or recovered, the instrument's own baseline is
established from its own history — and the reading is reported as a POSITION IN THAT
DISTRIBUTION, not as a number against an intuition.**

## Why

The charter case is a correction, not a catch. After #2005's 40-hour vacuum stall was cleared,
a post-recovery probe read **14.85 s** and was on its way to being written up as evidence that
the rail had not fully recovered. It had. **14.85 s is the 36th percentile of that rail's own
cold distribution** — a below-median cold read, which is to say a slightly *good* one.

Nothing about the first reading was sloppy. The number was real, the probe was correct, and
14.85 s is genuinely a long time for a web request. The error was entirely in the comparison:
it was judged against a general sense of what a fast endpoint costs, rather than against what
*this* endpoint costs when cold, which is the only comparison that could settle the question.

That is why this class survives careful work. A reading judged against an intuition produces a
finding that is specific, quantified, and reproducible — it has every surface property of a
good finding except a valid comparison. And the failure is directional in a way that compounds:
post-incident is exactly when everyone is primed to read the next number as a symptom, so the
baseline is least likely to be measured at the moment it is most load-bearing.

The same shape has already been paid for twice in this repo from the other direction, which is
what makes it a general clause rather than one rail's footnote:

- **`reference_post_deploy_latency_not_evidence`** — a measurement taken under ~5 minutes after
  a release reads as a regression against a warm baseline that no longer applies. Same defect:
  a real number, the wrong distribution.
- **Gotcha #49** — a Sentry issue's `count` is its LIFETIME total, so a dormant bug shows
  thousands while firing zero today. The "2,585 events" alarm on `datagolf_freshness` was a
  number compared against a window it did not come from.

## Practice

1. **Establish the baseline from the instrument's own history before reporting the read.** Not
   from a general expectation, not from a sibling endpoint, and not from what the number "feels
   like". If no history exists, take the baseline *now* — a control read is cheap and it is the
   difference between a finding and a guess.
2. **Report the position, not just the value.** "14.85 s, 36th percentile of cold" is a finding.
   "14.85 s" is a number that the next reader will re-litigate, because it carries nothing that
   distinguishes it from an alarm.
3. **A single reading is never the evidence for a state change.** Recovery, regression and
   degradation are all claims about a distribution having moved. One sample cannot carry them
   in either direction — including the reassuring direction.
4. **Pair every suspicious reading with a control**, and say what the control was. A reading
   with no stated comparison should be treated as unverified regardless of how precise it is.

## What this does NOT say

It does not say slow readings are fine, and it is not a licence to explain a real regression
away as "within the distribution". The obligation runs both ways: the baseline is what turns
14.85 s into a non-finding *and* what would have turned it into a hard one had it sat at the
99th percentile. The point is that neither verdict was available until the distribution was
measured — and that the honest intermediate state, before that work is done, is **"unjudged"**,
not "probably fine" and not "probably a problem".
