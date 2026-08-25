# US Open 2026 — market census

**Measured 2026-08-25 against production** via `POST /api/admin/db-query` (UX-P130, Day 1 of 5).
This is the measurement that decides whether Sunday's boards are rich or sparse, and it is the
input the register is built from. Every SQL statement here is re-runnable.

**Headline: identity is rich, price is dark.** We know exactly who is in both draws and which
market backs each of them across two sources. We have no current price for any of it. The
championship boards — the layer that "ships Sunday, no excuses" — are the half that is broken,
and the daily slate is the half that works. That is the inverse of what the ship plan assumed.

---

## 1. What exists

### Outright winner fields (the championship boards)

| market | source | outcomes | volume | liquidity | tier | status |
|---|---|---|---|---|---|---|
| `KXATP-26USO` — men's singles | kalshi | 33 | 470,270 | — | 1 | open |
| `KXWTA-26USO` — women's singles | kalshi | 23 | 67,491 | — | 1 | open |
| `139236` — men's singles | polymarket | 23 | 4,108,808 | 1,126,220 | 1 | open |
| `139255` — women's singles | polymarket | 41 | 5,819,053 | 991,336 | 1 | open |

Four fields, two per draw, two sources. **`odds_api` holds zero tennis futures of any kind**, and
DataGolf is golf-only — so the blend on this page has exactly two contributors and there is no
sportsbook column to build. That is a permanent shape, not a gap to close this week.

After identity resolution (see §3):

| draw | union rows | real players | two-source | one-source |
|---|---|---|---|---|
| men's singles | 37 | **36** | 19 | 17 |
| women's singles | 45 | **44** | 19 | 25 |

### Match markets (the daily slate)

**320 Polymarket markets named `US Open, Qualification ATP/WTA: <A> vs <B>`**, resolution dates
2026-08-31 → 2026-09-02 — main-draw week. A further **187 Polymarket `tennis` rows** named "US
Open" resolve 09-06 → 09-13 (later rounds and props). Event-level liquidity across both
qualifying draws is ~$2.45M.

These are live and updating hourly. `polymarket|table_tennis` is currently the platform's single
busiest snapshot writer: **2,571 snapshots across 456 markets in 3 hours**.

### Props

Nine Kalshi US-Open-adjacent markets: the two outright fields above plus
`KXATPCOMPETE-26USOALC`, `KXATPCOMPETE-26USOSIN`, `KXATPGRANDSLAM-26`,
`KXATPGRANDSLAMFIELD-26`, `KXGRANDSLAM-CALC26`, `KXGRANDSLAM-JSIN26`, `KXWTAGRANDSLAM-26`.

---

## 2. The blocking defect — the boards are price-dark

Filed as **#2199 (P1)**.

| market | source | last price capture | dark for |
|---|---|---|---|
| `KXATP-26USO` | kalshi | 2026-08-17 09:00 UTC | 8 days |
| `139236` | polymarket | 2026-08-10 15:15 UTC | 15 days |
| `139255` | polymarket | 2026-07-30 15:19 UTC | 26 days |
| `KXWTA-26USO` | kalshi | 2026-07-24 02:50 UTC | **32 days** |

**It is a capture stop, not price stasis.** Snapshots carry `reading_count = 1` on an hourly
cadence and then simply stop; Sinner moved 0.500 → 0.505 → 0.525 across the final readings and
then silence, mid-trend. `futures_outcomes.current_probability` still holds the last captured
value, so a naive board renders month-old numbers as today's with nothing marking them stale.

**Controls proving this is not a general outage:**

- Platform-wide, **194 distinct tier-1 markets** captured in the last 3h.
- `polymarket|tennis` is actively writing — 459 snapshots / 157 markets in 3h — but **only tiers
  2 and 5**, max volume among them **291**. Zero tier-1.
- Tier-1 `open` tennis captured in 24h: **kalshi 0 of 22** (total blackout), **polymarket 247 of
  1,385** (18%).

The rail is capturing the least valuable tennis markets hourly and skipping the most valuable
entirely.

```sql
SELECT fm.source, fm.external_id, MAX(s.captured_at) AS last_price, COUNT(*) AS snaps
  FROM futures_odds_snapshots s
  JOIN futures_outcomes fo ON fo.id = s.outcome_id
  JOIN futures_markets fm ON fm.id = fo.market_id
 WHERE fm.external_id IN ('KXATP-26USO','KXWTA-26USO','139236','139255')
 GROUP BY 1,2;
```

---

## 3. Mis-categorisation — how bad, and in which direction

Filed as **#2200 (P2)**. The register builds from source truth, so the page is immune; every
other surface that filters on these columns is not.

**`llm_gender` is NULL on all 861,809 rows of `futures_markets`.** The column is dead, not wrong.
Draw membership is therefore register-owned and never read from it.

**`llm_sport_category` fails in both directions:**

- *False negative.* All **298** US Open singles match markets sit under `table_tennis`.
  Platform-wide there are **12,766** `table_tennis` rows, of which **zero** name table tennis or
  ping pong, while **2,710** explicitly name ATP / WTA / ITF.
- *False positive.* Of 31 Polymarket rows labelled `tennis`, **26 are celebrity-attendance
  markets** — "Will LeBron James attend the US Open Finals?" — all under
  `group_id = polymarket:813144`.

So category is never a membership test in either direction, and gender is not a signal at all.

**Identity spelling splits across sources.** Kalshi writes `Felix Auger-Aliassime`; Polymarket
writes `Felix Auger Aliassime`. Punctuation-only normalisation leaves these as two board rows for
one player. `normalize_player_name` drops **spaces as well as punctuation**, which took the men's
two-source match count from 18 to 19.

**Aggregate buckets rank first.** Both Polymarket fields carry an `Other` outcome pinned at
`probability = 1.000000` since 2026-05-12. Sorted by probability descending it is the **first row
of both boards** — the "Party C, 100%" class. Excluded from the register by
`INVALID_NON_PLAYER_ENTITY`, so it cannot render.

---

## 4. Traps the slate must not walk into

**Stale-settled Kalshi matches (gotcha #33).** 15 Kalshi match markets for matches *played
2026-08-19* (Cincinnati) are still `status = 'open'` with `resolution_date` inside US Open week,
both outcomes already graded. Any date-window slate query renders finished matches as Sunday's
slate. One, `KXATPMATCH-26AUG19TIAAUG`, has zero outcomes. A register keyed on explicit matchups
cannot pull them in.

**Match-market outcome names are unusable.** The Polymarket match markets carry outcome names
that are a mix of `Yes`, `No`, the full market name repeated, and `... Set 1 Winner` variants:

```
US Open, Qualification WTA: Clara Burel vs Yexin Ma  →  "…Clara Burel vs Yexin Ma"=72 / "Yes"=72 / …
Cincinnati Open: Linda Noskova vs Amanda Anisimova    →  "Yes"=54 / "No"=47
```

Rendering these directly gives a slate of "Yes 54% / No 47%" instead of player names. **This is
what the register's matchup `sides` mapping is for**: `entity_key → outcome_id`, explicit, so the
slate prints players.

**Two-outcome match markets are not complements.** `Yes=54 / No=47` sums to 101; `Yes=62 / No=39`
to 101; `Yes=72 / No=29` to 101. These are independent binary quotes (gotcha #23, and #2088's
class). The slate must not present them as a 100% split without normalising or saying why.

> **Amendment 2026-08-25 (UX-P132) — this does not describe the US Open markets.** The three
> specimens above are **Cincinnati** rows. Re-measured against the 162 US Open qualification
> Yes/No pairs specifically, **every one sums to exactly 1.000** — Polymarket's own metadata
> calls them `outcome_relation: "complements", exhaustive: true`. The trap is real and the
> normaliser shipped, but the US Open slate is not currently walking into it. Stated because a
> carried-forward figure that was never true of *these* markets would have been cited as evidence
> of a defect that is not there.
>
> Two corrections to §1 from the same pass. **The 320 match markets are 324, and they are 162
> matches**: each match exists as *two* rows sharing one `group_id` — an event row whose outcomes
> are the decomposed sub-markets (winner, Set 1 Winner, totals) and a condition row carrying the
> `Yes`/`No` pair. And the match-winner sides mapping **is not in our database at all**; it has to
> be read from Gamma. See `docs/tournament-register.md` for both.

**`futures_outcomes.last_updated` is not a freshness signal.** It reads `2026-07-21` on all 23
Polymarket men's outcomes while that market's snapshots ran to `2026-08-10`. Freshness must come
from `futures_odds_snapshots.captured_at`, which is what `price_observed_at` stores.

---

## 5. Consequence for the register: it needs two population sources

The v1 register is seeded from the **outright fields** — 80 contenders, which is exactly right for
the boards. But the slate's players are the **qualifying draw**, and most of them (Diego
Dedura-Palomero, Jacob Fearnley, Aliona Falei …) are not contenders and so are not in the
register. `validate_matchup` enforces `MATCHUP_PLAYER_NOT_REGISTERED`, so **every qualifying
matchup would be rejected today** — correctly, and loudly.

Day 3 must therefore extend the register with a second population pass over the match markets
before any matchup can be added. This is a design consequence worth stating plainly: *contenders
and participants are different sets*, and a register that conflates them either rejects the slate
or lets unvetted names onto the boards.

> **Done 2026-08-25 (UX-P132).** Register v2: 80 contenders preserved, **131 participants** added,
> **66 matchups** on the slate. The conflation was avoided with a `role` field rather than a
> loosened matchup rule — `MATCHUP_PLAYER_NOT_REGISTERED` still bites exactly as hard.
> One player, **Qinwen Zheng**, appears in both sets and merged onto a single identity via the
> same space-dropping normalizer that fixed Auger-Aliassime. A top-10 player in a qualifying draw
> is more likely a Polymarket labelling quirk than a fact; it is recorded here rather than
> silently dropped, because the register handles it correctly either way.

---

## 6. Verdict for the ship

| layer | identity | price | verdict |
|---|---|---|---|
| Championship boards | ✅ 80 players, 2 sources, 38 blended | ❌ dark 8–32 days | **blocked on #2199** |
| Daily slate | ⚠️ needs the Day-3 population pass (§5) | ✅ live, hourly | **buildable** |
| Bracket | — | — | synthetic fixture per charter amendment |

The boards will render an honest degraded state until #2199 lands:
`check_freshness` emits `LIVE_PRICE_STALE` past 6h, which classifies as
`render_contract_failure` and blocks the row from presenting as a confident live number. **We
show that we don't know, rather than showing July.**
