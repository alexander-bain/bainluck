# #2222 — the nineteen tier-1 markets that could never be priced

Measurements taken 2026-08-29/30 by lane1 Q447, all read-only (`POST /api/admin/db-query`,
`GET /api/admin/source-health/futures-price-freshness`, and unauthenticated venue GETs).

The reasoning lives in `backend/app/utils/futures_liveness.py` and the docstrings of
`backend/app/tasks/futures_price_refresh.py`. **This file carries the numbers**, which do not
belong in a docstring and would otherwise be lost when the issue closes.

---

## 1. What a user saw

`GET /api/politics`, `international` and `elections` sections, 2026-08-30:

```
{"q": "Which Georgia primary elections will have a first-round winner?",
 "prob": 98.0, "src": "kalshi", "market_id": 12925046,
 "top_outcomes": [{"name": "Governor Democratic primary", "prob": 98.0}, ...]}
```

`market_id 12925046` is `KXGAPRIMARY1R-26MAY19`. The primary was held 2026-05-19. Our own database
records the winner (`Governor Democratic primary … is_winner = TRUE`). The last price capture was
`2026-07-23 22:59Z` — 37 days before the read. It is served in the same list as
`"Will Trump be impeached by end of 2026?"`, with nothing distinguishing the settled one.

That is the ship: a settled election stops being printed as a live 98% market.

---

## 2. The population, and that it is unanimous

`price_dark = 19` of `eligible_markets = 927`, `status: red`, checked
`2026-08-30T02:30:15Z`. Stuck at 19 across every run since 2026-08-26 (#2222's filing).

Every Kalshi row was probed against the venue with the same unauthenticated call the task makes:

| probe | result |
|---|---|
| `GET /events/{ticker}?with_nested_markets=true` on all **18** Kalshi rows | HTTP **200**, `event` present, **zero markets**, unanimous |
| `GET /markets?event_ticker={ticker}` on the same 18 | HTTP 200, **zero markets**, unanimous |
| **control:** `KXSB-27` (2027 Pro Football Champion, 73M volume, priced 2026-08-29T20:52Z) | HTTP 200, **32 markets** |

The control is what makes the zero a reading rather than an artefact of an unauthenticated call.
Kalshi keeps event rows forever and purges market rows (gotcha #35), so 200-with-no-book on a
resolvable event is a settled contest that has aged out.

The single Polymarket row, `86515` (Alpha Arena Season 1.5), is **not** purged — Gamma still serves
43KB for it — and is settled a different way. Driving the real fetch path against live Gamma:

```
parsed: True  markets: 9  neg_risk: True   event.closed: True   all markets closed: True
  0x4aacbc471ca5 prob=1.0  bid=None ask=0.001 last=1.0      <- eight losing legs, each quoting
  ...                                                          lastTradePrice 1 on its own No token
  0xb23782f3b415 prob=1.0  bid=0.999 ask=1.0 last=1.0       <- the winner ("Unknown")
priced: 8     field_is_incoherent: True
```

`field_is_incoherent` refuses it, correctly — eight legs at 1.0 in a mutually-exclusive field is
not a price. But a settled field can never become coherent again, so the refusal was permanent and
the market was reported as unreadable rather than as over.

---

## 3. Why neither liveness bound could see it

| row | `status` | `resolution_date` | ticker encodes | winner? | last capture |
|---|---|---|---|---|---|
| `KXUCL-26` (final played 2026-05-30) | open | **2028-05-29** | — | yes | 2026-08-06 |
| `KXPREMIERLEAGUE-26` | open | **2028-05-23** | — | yes | 2026-07-17 |
| `KXLALIGA-26` | open | **2028-05-23** | — | yes | 2026-07-10 |
| `KXCOLOMBIAPRESR1-26MAY31` | open | **2027-05-31** | 2026-05-31 | yes | 2026-08-06 |
| `KXPERUPRES1R-26APR12` | open | **2027-04-12** | 2026-04-12 | yes | 2026-07-19 |
| `KXGAPRIMARY1R-26MAY19` | open | **2027-05-19** | 2026-05-19 | yes | 2026-07-23 |
| `KXCHESSCANDIDATES-26` | open | 2028-04-16 | — | **no** | 2026-04-14 |
| `KXHOUSENJ11SPECIAL-26` | open | 2027-04-16 | — | **no** | 2026-04-17 |

`status='open'` survives settlement (gotcha #33). `resolution_date` — which the task's own docstring
called "what actually keeps the dead out of the queue" — is future on all nineteen and wrong by one
to two years wherever the ticker encodes a date to check it against.

**The `resolution_date` corruption is real and is NOT fixed here.** It is a writer bug in the
ingest, not a liveness bug, and #2222 is about the price refresh. Parked rather than dropped.

---

## 4. Blast radius of the graded-winner bound, measured before applying it

Across the full eligible set (927 rows), split by winner state and current freshness:

| winner state | freshness | source | n |
|---|---|---|---|
| has_winner | dark | kalshi | **16** |
| has_winner | **fresh** | kalshi | **1** |
| no_winner | dark | kalshi | 2 |
| no_winner | dark | polymarket | 1 |
| no_winner | fresh | kalshi | 424 |
| no_winner | fresh | polymarket | 483 |

The bound newly excludes exactly **one currently-priced market**: `KXWTA-26WASHIN` (WTA Washington
Winner, winner `Alexandra Eala`, tournament finished early August, still being re-priced hourly on
2026-08-29T21:50Z). Excluding it is correct — it is settled — and it is the one behaviour change to
watch after merge: it stops receiving new snapshots, so a surface gating on a 6h freshness window
will show it dark rather than showing a settled board as live.

**One eligible market is non-mutually-exclusive with a winner** (`KXGAPRIMARY1R-26MAY19`, the
independent-binary Georgia field) and it is dark. So scoping the bound to
`mutually_exclusive IS TRUE` would have spared the exact row proven user-visible in §1, and was
rejected for that reason. The residual risk — an independent-binary field where one leg settles and
others stay live — has **zero instances today** and is why the guard reports its exclusions by name
(§6) instead of dropping them silently.

---

## 5. What the fix moves, and what it does not

Dry-run of the new predicate against production, 2026-08-30:

```
price_dark  19 -> 3     (graded-winner bound alone)
settled_excluded         17, all reason=has_winner, 0 venue_settled (nothing stamped pre-deploy)
```

The remaining **3** carry no graded winner. They leave the set only after the venue-settled stamp
has stood for `VENUE_SETTLED_CONFIRM_HOURS = 48`, so:

> **`price_dark: 0` arrives roughly 48 hours after deploy, not on merge.** That delay is the safety
> property, not a shortcoming — see §7. Do not close #2222 or #2199 on the merge.

---

## 6. The guard is not allowed to silence itself

The task writes the venue-settled stamp, and the stamp is one of the guard's own bounds. A guard
that quietly shrinks its denominator can be talked into green by the thing it measures. So
`/api/admin/source-health/futures-price-freshness` now returns:

```json
"settled_excluded": {
  "why": "...cannot be re-priced and is not counted dark",
  "count": 17,
  "by_reason": {"has_winner": 17},
  "sample_limit": 25,
  "sample_markets": [ ... ]
}
```

`count` is the whole population; `sample_markets` is named a sample because it is capped at 25.
Green now reads *"no live market is dark, and here are the N I ruled not-live and why"*, which is
checkable.

---

## 7. Why the venue answer waits 48 hours

If the bound bit on a single read, one bad fifteen minutes at Kalshi would drop a live market out
of the refresh set **and** out of the guard's denominator at the same instant: it would stop being
priced and nothing would go red. That is the quiet failure direction, and it is the one that looks
like success.

So the stamp excludes nothing for 48h, the market keeps being retried throughout, and any single
successful price clears the stamp and the clock. The stamp is written **once**
(`WHERE market_metadata->>'…' IS NULL`), because re-stamping every run would reset the window and
restore #2222 exactly: observed settled hourly, stamped hourly, never old enough to leave, retried
forever, alarm red.

The comparison is lexicographic on ISO-8601 text rather than a `::timestamptz` cast: a cast raises
on a value some other writer left in the JSONB blob, and a raising selector is a refresher that
never runs. A value that is not a date sorts above a year-digit string and therefore leaves the
market **live** — noisy rather than silently retired.

---

## 7b. The stamp would have been deleted by the polls

Found while writing the cert's own attack list. Both ingest polls SET `market_metadata` to a
freshly built dict on every upsert — `"market_metadata": kalshi_metadata if kalshi_metadata else
None` — which is a **replace**, not a merge, so any key the poll does not know about is deleted.

Measured before changing anything:

| writer | reaches these rows? | how it writes `market_metadata` |
|---|---|---|
| `poll_kalshi_markets` | **no** (that is #2199's founding premise) | wholesale REPLACE |
| `poll_polymarket_markets` | **no** | wholesale REPLACE |
| `backfill_market_shapes` | **yes** — it is what moved `updated_at` on `KXHOUSENJ11SPECIAL-26` to 2026-08-30T00:30Z | merges with `\|\|` — safe |
| `kalshi.py` third writer | n/a | `on_conflict_do_nothing` — never updates |

`updated_at` on `KXHOUSENJ11SPECIAL-26` was `2026-08-30 00:30:22.990749Z` at 02:40Z and **identical**
at 03:32Z, so the polls are demonstrably not reaching it. The stamp therefore survives today —
**because of the very starvation #2199 exists to fix.** When discovery coverage improves the poll
reaches the row, the blob is replaced, the 48h clock resets to nothing, and #2222 returns silently.

Fixed rather than noted: both UPDATE paths now merge the key back. Validated against production
PostgreSQL 17.10, read-only:

```
NULL + absent key         -> NULL              (contract unchanged — still writes SQL NULL)
{"ticker":"X"} + absent   -> {"ticker": "X"}   (no-op for every market without a stamp)
{"ticker":"X"} + present  -> both keys         (the stamp is carried across the replace)
```

`NULLIF(..., '{}')` is what keeps the first line true. Without it the polls would begin writing
`{}` where they wrote NULL, and every reader testing `market_metadata IS NULL` would change
behaviour — a repo-wide side effect from a fix about nineteen markets. jsonb subscripting is PG14+;
production is 17.10.

---

## 8. Parked, deliberately

* **The `resolution_date` corruption** (§3). A writer bug in the ingest; needs its own measurement
  of how many rows carry a date the ticker contradicts.
* **The settled-stale population beyond tier 1.** `KXCOLOMBIA1R2-COLOMBIAPRES26-2` ("Colombian
  presidential election: 2nd place (1st round)", tier 2, winner recorded, 98%) renders on
  `/api/politics` from the same cause and is outside this queue's value floor. The class is
  broader than the nineteen; the nineteen are what the tier-1 invariant can see.
* **`status` is never corrected.** Nothing here sets `status='resolved'`, grades an outcome, or
  deletes a row. Applying a repair from a detection is how a wrong detection becomes data loss
  (gotcha #21), and the read side already has the information it needs.
