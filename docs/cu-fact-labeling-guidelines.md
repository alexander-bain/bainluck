# Content Understanding Fact-Labeling Guidelines (One-Page Reference)

Applies to the dual-rater labeling pass on the frozen sealed (`300`) and practice development (`200`) sets at `/admin/cu-labeling`. Grounded in the five prior grading rounds and the offline fault library.

## Core Ground Rules

1. **Label blindly.** Never discuss answers with the other labeler while labeling. Both labelers submit independently; neither sees the other's answers while working.
2. **Evidence over guessing.** Use only the market title, option names, and rules text shown on the card. When the text does not support an answer, choose `"None of these"`, `"Not sure"`, `"No single day"`, or leave claim slots blank.
3. **Facts first, taste last.** Answer Questions 1–5 (facts) before Question 6 (`stakes` and `breadth`, `1–5`). Fact disagreements go to a third-look tiebreak with written evidence; `stakes` and `breadth` are **never** tie-broken (disagreements go to product review).
4. **Practice set `shared_100` vs sealed `shared_100`.** On the sealed set, `shared_100` is a representative stratified draw (`67` reader-weighted + `33` spread). On the development set, `shared_100` leads with the `100` markets that changed between repeated runs — the hardest markets — so dual-rater agreement on the development set will read lower than on the sealed `100`.

---

## Matching Rules (Frozen Before First Label)

> **Freeze rule:** This table is frozen before the first human label is read. Any matching rule changed afterwards must be reported explicitly as changed afterwards alongside any published scorecard numbers.

| Field | What the labeler answers | What counts as a match |
|---|---|---|
| **Named subjects** (`entities`) | Pick candidate chips, type custom names, `"None of these"`, or `"Not sure"` | Ignore entity `type`. Lowercase and strip punctuation (`'` removed, punctuation normalized to spaces). A labeled subject is matched when either name contains the other as contiguous whole words. The row is right only when **every** labeled subject is matched. Extra writer-only names are counted separately, not marked wrong. `"None of these"` matches an empty writer list; `"Not sure"` omits the row from scoring. |
| **The event's own day** (`event_date`) | Calendar day `YYYY-MM-DD`, or check `"No single day"` | Exact calendar day match (`YYYY-MM-DD`), or both `null` when `"No single day"` is checked. |
| **Where** (`geography`) | `us`, `global`, `local`, or `country:<XX>` | Case-insensitive exact match. |
| **Market format** (`junk_flags`) | `"Ladder of one number"`, `"Set of dated options"`, or `"Neither"` | Compare only `"ladder"` and `"dated_bucket"`. Ignore unasked writer flags such as `"duplicate_phrasing"` so extra unasked flags never fail the row. |
| **Number and comparison** (`frame`) | Fixed dropdown choices (`measure`, `comparator`, `horizon_kind`, each with `"None of these"`), plus verbatim `value`, `unit`, and `window_date` | Exact 6-slot match (`measure`, `comparator`, `value`, `unit`, `horizon_kind`, `window_date`, lowercased with thousands commas stripped from numeric `value`, or all `null` when left blank). `"None of these"` on optional `comparator` or `horizon_kind` matches writer `null`. |
| **How much it matters** (`stakes`) | Integer `1–5` (asked last; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. If dual-rater within-1 agreement falls below `80%`, `stakes` goes to Alex and is withheld from the scorecard. |
| **How many people care** (`breadth`) | Integer `1–5` (asked last; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. If dual-rater within-1 agreement falls below `80%`, `breadth` goes to Alex and is withheld from the scorecard. |

---

## Field-by-Field Edge Cases

### 1. Who or what is it about? (`subjects`)
- Pick the **specific** person, team, organization, bill, tournament, or asset the outcome turns on — not a broad category label.
- Include both sides of a head-to-head fixture (`Wake Forest Demon Deacons`, `Mississippi State Bulldogs`), not just the first team.
- Use **Custom** if the true subject is named in the title/options/rules but missing from the candidate chips.
- Use **`None of these`** when a market is purely an index, threshold, or macro series with no discrete named subject (e.g., `"US CPI YoY"`, `"Highest temperature in Austin"`). Use **`Not sure`** only when genuinely ambiguous.

### 2. The event's own day (`event_date` vs `No single day`)
- Record the **real-world day the event happens** (`YYYY-MM-DD`, US Eastern calendar day for US fixtures/elections), **not** the platform contract settlement timestamp.
- **Settlement-echo trap:** Kalshi/Polymarket settlement timestamps often land at `14:00Z` / `21:00Z` / `23:59Z` or weeks after Election Day / Championship finals. For `"Connecticut presidential election winner? (2028)"`, the event's day is `2028-11-07`, even when settlement reads `2029-05-07`.
- **Deadline vs single-day trap:** For multi-month props (`"Conference USA Champion"`, `"Will X happen before Dec 31?"`, year-long totals), mark **`No single day`** unless the event itself occurs on one calendar day.

### 3. Where (`geography`: `us` | `global` | `local` | country)
- **`local`**: city, county, school board, mayoral/municipal races, AND **state legislative districts** (`Vermont House Orleans-3`, `Connecticut Senate District 36`, `Alaska House District 11`, city weather highs). Even though state legislatures sit inside the US, legislative district seats are `local`, not `us`.
- **`us`**: national US politics, US macro releases, Fed decisions, nationwide US pop culture, and US domestic leagues (`NBA`, `NFL`, `MLB`, `NHL`, `NCAA`) unless strictly one city's affair.
- **Cross-border / international sports**: domestic league cups belong to that country (`country:GB`, `country:ES`, etc.); **cross-border** competitions (`UEFA Europa League`, `Champions League`, `World Cup`, Olympics, geopolitical treaties) are `global` (or multi-country global), never `"us"`.

### 4. Market format (`ladder` | `dated_bucket` | `neither`)
- **`ladder`**: multiple outcomes sweeping thresholds of **one underlying number** (`Above 13000`, `Above 13100`, ..., `Above 13700`, or `Above 5.00%`..`6.75%`).
- **`dated_bucket`**: outcomes splitting **one question across different deadline dates** (`By October 31`, `By December 31`).
- **`neither`**: plain Yes/No, two-sided game/matchup, or multi-contender field (`Winner of ...` with team/candidate options). Check the options list carefully—ladders often look like plain questions until you read the options.

### 5. Number and comparison (`frame`: `measure`, `comparator`, `value`, `unit`, `horizon_kind`, `window_date`)
- Choose `measure`, `comparator`, and `horizon_kind` from the writer's dropdown lists (or `"None of these"` if none fits).
- Copy `value`, `unit`, and `window_date` **verbatim from the title or options** — never expand abbreviations or invent unprinted numbers:
  - Season strings like `"2026-27"` are **not** a numeric threshold `value: "27"`.
  - Team/brand substrings like `"W7M"` are **not** `value: "7M"`.
  - If the title says `"13M subscribers"`, copy `"13M"` verbatim (do not rewrite `"13000000"`).
  - If the title ends `"by December 31, 2027"`, copy `"December 31, 2027"` into `window_date`.
- Leave all 6 claim fields **blank** on qualitative winner / yes-no questions without an explicit numeric threshold (`"Will Commanders advance?"`).

### 6. How much it matters & how many people care (`1–5`, asked last)
- **How much it matters (`stakes`):**
  - `1`: Hyper-local seat, niche daily stat, single city weather high, obscure prop (`Vermont House Orleans-3`).
  - `2`: Regular-season game, minor regional/company metric.
  - `3`: Major national game/round, marquee earnings/macro print, senator/governor race.
  - `4`: Championship final, Supreme Court/cabinet/Fed rate move, major geopolitical treaty.
  - `5`: Presidential election, war/peace inflection, global macro shock.
- **How many people care (`breadth`):**
  - `1`: Handful of locals or niche fans follow this.
  - `2`: Followers of one team, state, or industry care.
  - `3`: National sports, politics, or market followers know it.
  - `4`: Most people in a country or major sport pay attention.
  - `5`: Household-name story that crosses borders.

## Tiebreak Rules (Third Look)
- Triggered only after both first and second labelers finish a market and disagree on at least one fact field (`subjects`, `event_date`, `geography`, `structure`, `claim_frame`).
- Inspect both fact answers + title/options/rules and cite the exact phrase or rule in **`evidence_note`** (required).
- **Never** tiebreak `stakes` or `breadth`.
