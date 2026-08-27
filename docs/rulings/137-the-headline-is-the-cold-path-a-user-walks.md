# RULING 137 — The headline is the cold path a user walks, not the warm one the cache can produce

date: 2026-08-26
author: Alex (PROGRAM CHARTER AMENDMENT, directive authored in Alex's Fable session and delivered
through the lane runner Alex launched under his standing authorization)
issue: 1545

**Amends:** ruling 127 §1 (HEADLINE METRIC) and `docs/PRD.md`'s latency charter (Alex,
2026-08-24). Everything else in 127 — the instrument test, the beat-cost flag, the
census-counts-the-observer protocol, the frozen probe set, the derived warm/cold threshold —
stands unamended.
**Binds:** the `latency` program lane, every cycle, starting LAT-P099.
**Pre-registration record:** `docs/audits/latency/lat-p099-cold-path-charter.md`, committed
before the first number was taken.

---

## The clause

> "stop bragging about warm searches — a tiny fraction of searches will be warm. What matters
> most: Discover load time, the load time of the other tabs, and COLD search load. That's what a
> user experiences in volume."
> — Alex, 2026-08-26

**A performance program reports the case its users are in, weighted by how often they are in it.
The best case a cache can produce is not that case, and leading with it is a claim about the hit
rate wearing the costume of a claim about speed.**

Ruling 127 already banked the sharper half of this — *a p50 over mixed cache states is a
statement about the HIT RATE, not about latency* — and then made the warm number the headline
anyway. That is the defect this amendment fixes, and it is worth naming precisely because 127 was
right: the fault was not a missing insight, it was an insight applied to the footnote and not to
the headline.

## What it replaces

`feed p50` and `typeahead p50`, warm, opened every report from LAT-P083 to LAT-P098. `feed p50`
was reported at 16–20 ms for three consecutive cycles — 18 ms, 17.5 ms, 20.7 ms — every one of
them true, every one of them measured correctly, and none of them describing what a person felt,
because in the same three cycles the miss under it cost 3,201.7 ms (LAT-P097) and 4,100 ms (the
PRD's first honest measurement). A reader of those headlines would have concluded the feed was
solved. A reader of the same reports' §3 would have concluded it was not. **The headline and the
finding disagreed for three cycles and the headline won every time**, which is what a headline
is for and why the choice of one is a ruling rather than a formatting preference.

## The new headline metric set

Every latency report from LAT-P099 onward **opens** with these and nothing before them:

1. **Discover first-load p50** · 2. **Sports first-load p50** · 3. **Browse first-load p50** ·
4. **My Stuff first-load p50** · 5. **cold search p50** (`/api/events/search` and
`/api/events/typeahead`, first touch, never-asked term)

The native tab bar (`Views/MainTabView.swift:19-52`) has FIVE tabs — Discover, Sports, Browse,
**Search**, My Stuff — so the directive's "the other tabs" plus cold search is five rows, and
Search is both the fifth tab and the surface row 5 grades.

**Warm numbers are DEMOTED, NOT DELETED.** `done_bar_snapshot.py` keeps measuring `feed p50 warm`
and `typeahead p50 warm` and keeps their series, because a series re-baselined mid-flight is
worth nothing and this program has already paid for that lesson twice (the salt, the term set).
They move below the fold. **A warm-hit win may never open a report or lead a claim again**; it is
supporting evidence for "the good case did not regress", which is a real thing to know and a
worthless thing to lead with.

## Three definitions the clause needs to be enforceable

**A first load is the request a tab issues when a person opens it on an install the server has
never served.** Not a cache-buster, not a synthetic key: a fresh `x-session-id` per sample, which
is exactly what a new install sends (`APIClient.swift:162`). It is safe to repeat because the
LAT-P089 inert-principal share republishes only to the private key — a fresh-session sample can
*read* what the warmer left and can never *extend* it.

**A tab is a request SET and only one member gates the paint.** Sports issues three requests, My
Stuff two, Discover two. Summing them overstates the wait; reporting only the main one hides a
sibling that can hang. The `blocking` flag is taken from the client's own control flow, the
headline is the blocking member, and the whole set is printed beneath it.

**A surface that issues no request is reported as NO SERVER DEPENDENCY, never as "0 ms".** Browse
renders static arrays (`Views/LeaguesView.swift:55-78`); the web Browse is a link dropdown with
no route. That is asserted from source and pinned by a test. A request that is never issued has
no latency, and printing a zero as though an instrument produced it is the same class of error as
a gate that cannot fire — it reads as a measured pass.

## The bars are inherited, and a cycle may not move the one it is about to fail

Tab first-load p50 **≤ 1,000 ms**, taken verbatim from the charter's existing feed-miss bar; cold
`/api/events/search` p50 **≤ 1,000 ms**; cold `/api/events/typeahead` p50 **≤ 500 ms**, unchanged;
and a per-sample hard ceiling of **6,000 ms**, which is `DiscoverViewModel.retryBudget`
(`DiscoverViewModel.swift:216`) — a non-retryable client deadline past which the app gives up and
paints disk last-good. The ceiling is graded on the MAX and not the median, because one sample
over it is a user-visible failure that a median hides.

## What this does NOT do

It does not loosen a single instrument clause of ruling 127 — the organic-first census read, the
observer subtraction, the contamination declaration, the derived transport-floor threshold and
the frozen term set all apply to the new numbers exactly as they applied to the old, and the new
instrument enforces the first of them mechanically rather than by memory (`--stats-before`).

It does not make cold-only the rule: the headline is the **user-volume** number over the real
cache mix, with the cold sub-median printed beside it. A tab that is genuinely warm 90 % of the
time is genuinely fast 90 % of the time, and pretending otherwise would be the same error with
the sign flipped — which is the error `done_bar_snapshot.py` guards against by discarding warm
samples, correctly, for a different question.

It does not retire `done_bar_snapshot.py`, and it does not license comparing its numbers with the
new instrument's. Two instruments, two series, never subtracted (ruling 127's own rule: *a delta
between two different measurements is a delta of instruments*).

And it does not lower the reliability bar or the cert tiering. It changes which number a report
opens with, which is exactly the thing that decides what a lane works on next.

**General form, and it is the transferable part:** *when a system is bimodal, the headline must be
weighted by the mode users are actually in — otherwise the metric improves every time the cache
gets luckier and never when the product gets faster.*
