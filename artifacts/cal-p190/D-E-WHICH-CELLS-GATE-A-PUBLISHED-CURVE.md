# CAL-P190 — D-E option (b): which of M-J's cells actually gate a published curve

**Directive:** `920-freeze-window-design-work.md` ITEM 2 — *"D-E is defaulted (b): repair only cells
that gate a published curve — measure which cells those are (from M-20260830-J's table) and prepare
the repair for after the publish."*
**Measured:** 2026-09-01 ~16:1xZ / ~09:1x am PT. Source read + one live fetch of
`GET /api/calibration`. No write, no deploy.

---

## 0. THE ANSWER IN ONE LINE

🔴 **Option (b) removes 6 of the 23 cells and 291 of the 36,228 overrun markets — 0.8%. On this
population (b) and (a) are the same repair, and the scope reduction the default was buying is
rounding error.**

---

## 1. HOW A CELL FAILS TO GATE THE CURVE — three ways, and only one of them fires

| gate | what it is | how many of M-J's 23 cells it removes |
|---|---|--:|
| **RULE E cell exclusion** | `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` = `('kalshi','crypto')`, `('kalshi','economics')` | **0** |
| **K′ cell exclusion** | `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS` = `('polymarket','baseball')` | **0** — M-J is explicitly the cells *other than* `polymarket/baseball` |
| **the publish bar** | `min_category_outcomes = 1000`, per CATEGORY. Below it a category is `parked_below_publish_bar` and appears in no published number | **6** |

Both cell-exclusion lists are read from `app/tasks/precompute_calibration.py` at
`origin/master 35c50d48`; the bar and the parked list are read from the live payload
(`generated_at 2026-08-31T04:37:36Z`).

⚠️ **The published curve I read predates RULE E and K′.** That does not weaken the answer: the two
lists it would add exclude `kalshi/crypto`, `kalshi/economics` and `polymarket/baseball`, and none of
the three is in M-J's table. The exclusions cannot change this result in either direction.

---

## 2. THE 23 CELLS, MAPPED TO THEIR PUBLISHED CATEGORY

Overrun-market counts are M-J §1's chunked census. `published n` is the live `by_category` entry for
that category (all sources pooled — **the bar is per category, not per source×category**).

| M-J cell | overrun markets | category | published n | gates? |
|---|--:|---|--:|:--:|
| `kalshi / baseball` | 10,340 | baseball | 215,680 | ✅ |
| `kalshi / tennis` | 9,685 | tennis | 47,646 | ✅ |
| `kalshi / esports` | 4,440 | esports | 30,974 | ✅ |
| `polymarket / basketball` | 2,667 | basketball | 124,138 | ✅ |
| `polymarket / tennis` | 2,454 | tennis | 47,646 | ✅ |
| `polymarket / soccer` | 2,380 | soccer | 132,103 | ✅ |
| `kalshi / basketball` | 1,682 | basketball | 124,138 | ✅ |
| `kalshi / soccer` | 761 | soccer | 132,103 | ✅ |
| `kalshi / football` | 560 | football | 12,012 | ✅ |
| `kalshi / mma` | 380 | mma | 3,988 | ✅ |
| `kalshi / hockey` | 229 | hockey | 35,427 | ✅ |
| **`kalshi / lacrosse`** | **216** | lacrosse | **303** | 🔴 **no** |
| `polymarket / hockey` | 195 | hockey | 35,427 | ✅ |
| `polymarket / esports` | 85 | esports | 30,974 | ✅ |
| **`kalshi / boxing`** | **58** | boxing | **238** | 🔴 **no** |
| `polymarket / cricket` | 38 | cricket | 3,414 | ✅ |
| `kalshi / cricket` | 34 | cricket | 3,414 | ✅ |
| **`polymarket / rugby`** | **6** | rugby | **333** | 🔴 **no** |
| **`kalshi / rugby`** | **6** | rugby | **333** | 🔴 **no** |
| `polymarket / mma` | 5 | mma | 3,988 | ✅ |
| **`polymarket / boxing`** | **3** | boxing | **238** | 🔴 **no** |
| **`polymarket / lacrosse`** | **2** | lacrosse | **303** | 🔴 **no** |
| `kalshi / motorsports` | 2 | motorsports | 6,027 | ✅ |

**17 cells gate · 6 do not.**
**35,937 overrun markets gate · 291 do not.**

None of the three parked categories is marginal: `rugby` 333, `lacrosse` 303, `boxing` 238, against
a bar of 1,000. They are not about to cross it.

---

## 3. WHAT THE REPAIR SCOPE IS, IF (b) STANDS

**Repair 17 cells / 35,937 overrun markets.** Ordered by size, the first six carry 32,268 of them
(90%), so a size-ordered repair is 90% done after six cells:

```
kalshi/baseball 10340 · kalshi/tennis 9685 · kalshi/esports 4440
polymarket/basketball 2667 · polymarket/tennis 2454 · polymarket/soccer 2380
```

**Skip:** `kalshi/lacrosse`, `kalshi/boxing`, `polymarket/rugby`, `kalshi/rugby`,
`polymarket/boxing`, `polymarket/lacrosse`.

⚠️ **Skipping them is a defensible call and a small one.** Those 291 markets are still wrong in the
database; they are merely invisible on the page today. If `rugby`/`lacrosse`/`boxing` ever cross the
1,000-outcome bar they become visible carrying uncorrected prices, so (b) is *defer*, not *drop*, and
should be recorded that way.

---

## 4. WHAT THIS DOES NOT MEASURE, STATED PLAINLY

* **Markets, not outcomes.** M-J's census counts overrun *markets*; the publish bar counts
  *outcomes*. The 0.8% is a market-count share. The outcome-share could differ, though not by enough
  to change the verdict — the six skipped cells are the six smallest in the table.
* **Whether repairing a gating cell moves its published number.** That is M-J §2's per-outcome
  price-move probe, which **times out** on the web dyno even at `LIMIT 3` — M-J reported that as a
  finding and it is still true. Sizing the *benefit* of the repair needs the measurement lane.
* **Row-level filters shrink these cells; they do not remove them.** The esports bundle filter, the
  liquidity filter, the malformed-binary filter and the golf placeholder filter all cut rows inside a
  gating cell. A cell can therefore gate the curve with fewer outcomes than its market count
  suggests. Not sized here.
* **Not re-derived:** M-J's own census. Its counts are two days old and it warns that its four named
  cells drift +22% / +12% / −29% against the source note. The *ranking* is what this uses, and the
  ranking is stable at this granularity.

---

## 5. FOR `YOUR-TURN.md`

D-E's default (b) is safe to keep — **but it should be recorded that (b) ≈ (a) here.** The choice
between them is worth about 291 markets in three categories nobody can currently see. If (b) was
chosen to make the repair smaller, it did not, and the real scope question is *ordering* (the top six
cells are 90% of it), not *inclusion*.
