# LAT-P081 GATE 2 — the owed P4-tail like-for-like, and why a sampled bound cannot settle it

**Fired 2026-08-22 10:07:30 PDT**, not before ~10:07 per Fable's directive item 3. Production
`a13239f1` / **v3884 throughout** — the deploy watcher ran 06:46 → 10:08 and recorded **no
release**, so all four rings below were taken on identical code.

---

## 1. The directed read

```
verdict : NOT_REFUTED
arms    : post_fix=32  pre_fix=0  unknown=0  (no wall: 0)
post-fix: n=32  p50=34.920  p95=42.458  max=44.883  over_ttl=0
pinned  : MEASURED_WALL_MAX_S=66.365  TTL=65  WALL_MAX_EXCEEDS_RESPONSE_TTL=True
exit code 0
```

**The ring is fully post-fix** — 32 of 32, zero pre-fix, zero unknown, so the MIXED_RING refusal
did not trigger and this is a clean like-for-like against LAT-P079's pinned post-fix arm
(n=8, p50 43.310, p95 45.421, max 45.952).

**The standing verdict is `NOT_REFUTED`. Explicitly NOT "improved"**, exactly as the directive
requires and as the grader is built to enforce — `improved` is not an available verdict.

## 2. 🔴 `MEASURED_WALL_MAX_S` DOES NOT MOVE

The directive says *"Only after THAT grade may `MEASURED_WALL_MAX_S` move."* The grade is taken,
and it says the constant must stay at **66.365**:

* it cannot go **down** — a favourable sampled max is a lower bound, and lowering on a favourable
  read is the move that made LAT-P075's "SAFE for the first time" retractable (ruling 075, trap 2);
* it cannot go **up** — nothing observed today comes near it, so there is no stale-underestimate
  obligation to discharge (the grader would have exited 2).

`WALL_MAX_EXCEEDS_RESPONSE_TTL` stays `True`, and the live beat stays MARGINAL.

## 3. THE FINDING — four disjoint rings, and the noise exceeds the signal

The directive gated this read on "≥18 h since 16:07 Friday, so the ring is fully post-fix." **The
ring's own span refutes that premise, favourably**: at 0.47–1.26 h wide, a 32-deep ring turns over
in well under two hours. It was fully post-fix by roughly 17:20 Friday and has been ever since,
through ~15 turnovers. The overnight wait bought no post-fix purity, because none was left to buy.

What the tail clause actually needs is **independence**. So this window banked four disjoint
32-sample rings across the morning — which is the grader's **own** stated criterion for the read
meaning more:

> "What would make it mean more: **a second independent fully-post-fix ring at the same depth
> agreeing**, or a wall bound that is derived rather than sampled."

| ring | taken | n | span | p50 | p95 | **MAX** | > TTL |
|---|---|---|---|---|---|---|---|
| **A** | 06:22 | 32 | 1.26 h | 42.577 | 52.982 | **55.400** | 0 |
| **B** | 07:50 | 32 | 0.48 h | 39.518 | 43.319 | **45.765** | 0 |
| **C** | 09:15 | 32 | 0.52 h | 37.859 | 47.683 | **54.568** | 0 |
| **D** (the gate read) | 10:07 | 32 | 0.47 h | 34.920 | 42.458 | **44.883** | 0 |

**They do not agree.**

```
MAX spread across four disjoint rings   10.517 s   (23 % of the smallest)
headroom, highest max (55.400) -> TTL    9.600 s
spread as a fraction of that headroom      110 %
```

> **The ring-to-ring noise in the sampled maximum is LARGER than the distance from that maximum to
> the TTL it is being compared against.**

A single 32-sample ring therefore cannot answer "does the tail cross 65 s?" Two rings taken 88
minutes apart on identical code disagree by more than the gap to the threshold. This is not a
subtle statistical objection — it is the direct, measured mechanism behind the constant having
been raised **four times**, each time on an honest sampled max that a later, luckier sample
exceeded:

```
42.6  ->  53.920  ->  61.282  ->  66.365
```

### Two aggravating facts the four rings also expose

1. **The rings are not exchangeable — the medians drift monotonically.** 42.577 → 39.518 → 37.859
   → 34.920 across the morning, a steady 18 % decline. These are not four draws from one
   distribution; the population is non-stationary within a single morning. So "take more rings and
   average" does not rescue the method either.
2. **A fixed ring depth covers a wildly variable period.** Spans run 0.47 h to 1.26 h — a **2.7×**
   range — because the warmer's own period is highly variable (`period_s`: min 34.1 s, p50 49.9 s,
   p95 327.6 s, max 2112.9 s). "32 samples" is a stable-sounding label for an unstable window, and
   any max read off it is a statement about somewhere between 28 and 76 minutes.

## 4. What this means for the clause

* **The like-for-like read is TAKEN and the debt is discharged.** LAT-P079 owed a fully-post-fix
  32-deep comparison against its n=8 arm; this is it, and the arms are comparable
  (post-fix 32/32, MIXED_RING not triggered).
* **The verdict is `NOT_REFUTED` and must not be reported as an improvement.** Today's max
  (44.883) is below LAT-P079's post-fix arm max (45.952), and that is exactly the reading ruling
  075 forbids treating as progress — ring B's 45.765 and ring A's 55.400 came from the same
  morning and the same code.
* **The honest conclusion is that the SAMPLED method is exhausted.** Four rings in one morning
  scatter by more than the headroom to the TTL. No amount of further sampling at this depth will
  settle whether the tail crosses 65 s, so the grader's second criterion is the only way out:
  **a wall bound that is DERIVED rather than sampled.**

That is stated as a finding, not built: deriving the bound is a change with its own design and its
own gate, and this directive authorised a read, not a fix.
