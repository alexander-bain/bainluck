# LAT-P091 — what #1916 actually costs the `/search` head warmer, measured

**Taken:** 2026-08-25 ~23:40 UTC (16:40 PDT), production, via `POST /api/admin/db-query`.
**Why it exists:** the LAT-P090 head warmer ships DISABLED behind #1916. Fable asked for a
decision-shaped statement of what that block costs. A percentage of contaminated *rows* does not
decide anything; **whether the contamination changes which terms get elected** does. This is that
counterfactual.

**Named decision it unblocks (ruling 127 §2):** whether Fable grants or denies
`SEARCH_HEAD_WARM_ENABLED=1`. Without it the grant rests on "23.6% contaminated" — a number about
the table, not about the head.

## Method

The warmer elects its head with `_head_from_query_log` (`app/tasks/typeahead_warmer.py:457`),
imported by `search_head_warmer.resolve_head`. That exact SQL was re-run against production, once
as-is and once with the #1206 gold-sentinel minute excluded. The sentinel is identified by #1916 as
07:09–07:12 UTC; it is excluded here by that timestamp predicate, which is the heuristic #1916 says
must eventually be replaced by a flag — **so this read is an estimate of the block's cost, not the
clean distribution #1916 asks for.** It does not discharge #1916.

`DEFAULT_HEAD_SIZE = 8`, so only the top 8 are warmed.

## Result — the head membership CHANGES, 6 of 8 survive

| # | head as elected TODAY (contaminated) | n | sentinel-minute rows | sentinel share | clean head (sentinel excluded) | n |
|---|---|---|---|---|---|---|
| 1 | `masters winner` | 116 | 56 | **48.3%** | `red sox` | 94 |
| 2 | `stanley cup` | 110 | 28 | 25.5% | `stanley cup` | 82 |
| 3 | `world cup` | 103 | 28 | 27.2% | `yankees` | 77 |
| 4 | `nba champion` | 101 | 28 | 27.7% | `world cup` | 75 |
| 5 | `world series` | 99 | 28 | 28.3% | `nba champion` | 73 |
| 6 | `red sox` | 94 | 0 | 0% | `world series` | 71 |
| 7 | `yankees` | 77 | 0 | 0% | **`fed`** | 68 |
| 8 | `grammys` | 75 | 28 | 37.3% | **`chiefs`** | 65 |

**Overlap: 6 of 8.** Head total n=775, of which 196 sentinel = **25.3% echo**, materially the 23.6%
#1916 measured over the whole table.

- **Warmed but should not be:** `masters winner` (clean rank 10) and `grammys` (clean rank 12).
- **Not warmed but should be:** `fed` (clean rank 7) and `chiefs` (clean rank 8).

`fed` and `chiefs` are **the same two terms #1916 named** as human #3 and #4 going unwarmed on the
`/typeahead` head. Two independent sources, two different head mechanisms, the same two victims.
That corroborates #1916's thesis rather than weakening it.

The sentinel is not a rounding error at the top: it supplies **48.3%** of the rank-1 term's votes,
and rank-1 is the term the warmer spends its first slot on.

## What this does and does not license

**Does not:** conclude the head is fine. It is measurably wrong, in the direction #1916 predicted.

**Does:** bound the cost of being wrong. With the warmer OFF, **0 of 8** head answers are warm and
each costs a full cold `/search` (measured today: `winner`, off-head, **7,755 ms wall / 7,719 ms
db**). With it ON against today's contaminated head, **6 of 8** are the terms a clean distribution
would also pick; the loss is 2 wasted warm slots and 2 real head terms left cold.

The harm #1916 exists to prevent — a closed self-electing loop — **cannot occur on this path**:
`_warm_one` sets `_suppress_search_log`, so this warmer casts no votes for its own head. The
contamination is fixed at ~25% and does not compound. That is the structural difference from the
`/typeahead` warmer, 89% of whose head score was its own echo.

## Contamination introduced by this read, declared

This lane issued 4 `/search` requests during LAT-P091's check run (`winner` ×3, `zzq control lat90`
×1). `/search` writes `search_query_logs`, so those 4 rows are in the table this measurement reads.
4 rows against ~4,000 over 30 days, and neither term is within 60 votes of the head cut. Stated
because ruling 127's general form is that an instrument writing to what it reads must say so.
