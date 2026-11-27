# Content Understanding Fact-Labeling Guidelines (One-Page Reference)

Applies to the `#13900` dual-rater pass on the frozen sealed (`300`) and development (`200`) sets at `/admin/cu-labeling`. Grounded in the five grading rounds on `#1809` and the fault library in `#13901`.

## Core Ground Rules

1. **Label blindly.** Never discuss answers with the other labeler while labeling. Both labelers submit independently; neither sees the other's answers while working.
2. **Evidence over guessing.** Use only the market title, option names, and rules text shown on the card. When the text does not support an answer, choose `"none_of_these"`, `"not_sure"`, `"no_single_day"`, or leave claim slots blank.
3. **Facts first, taste last.** Answer Questions 1–5 (facts) before Question 6 (`stakes` and `breadth`, `1–5`). Fact disagreements go to a third-look tiebreak with written evidence; `stakes` and `breadth` are **never** tie-broken (disagreements go to product review).

---

## Field-by-Field Edge Cases (From #1809 Rounds 1–5)

### 1. Who or what is it about? (`subjects`)
- Pick the **specific** person, team, organization, bill, tournament, or asset the outcome turns on — not a broad category label.
- Include both sides of a head-to-head fixture (`Wake Forest Demon Deacons`, `Mississippi State Bulldogs`), not just the first team.
- Use **Custom** if the true subject is named in the title/options/rules but missing from the candidate chips.
- Use **`none_of_these`** when a market is purely an index, threshold, or macro series with no discrete named subject (e.g., `"US CPI YoY"`, `"Highest temperature in Austin"`). Use **`not_sure`** only when ambiguous.

### 2. The event's own day (`event_date` vs `No single day`)
- Record the **real-world day the event happens** (`YYYY-MM-DD`, US Eastern calendar day for US fixtures/elections), **not** the platform contract settlement timestamp.
- **Settlement-echo trap:** Kalshi/Polymarket `resolution_date` often lands at `14:00Z` / `21:00Z` / `23:59Z` or weeks after Election Day / Championship finals. For `"Connecticut presidential election winner? (2028)"`, the event's day is `2028-11-07`, even when settlement reads `2029-05-07`.
- **Deadline vs single-day trap:** For multi-month props (`"Conference USA Champion"`, `"Will X happen before Dec 31?"`, year-long totals), mark **`No single day`** unless the event itself occurs on one calendar day.

### 3. Where (`geography`: `us` | `global` | `local` | country)
- **`local`**: city, county, school board, mayoral/municipal races, AND **state legislative districts** (`Vermont House Orleans-3`, `Connecticut Senate District 36`, `Alaska House District 11`, city weather highs). Even though state legislatures sit inside the US, legislative district seats are `local`, not `us`.
- **`us`**: national US politics, US macro releases, Fed decisions, nationwide US pop culture, and US domestic leagues (`NBA`, `NFL`, `MLB`, `NHL`, `NCAA`) unless strictly one city's affair.
- **Cross-border / international sports**: domestic league cups belong to that country (`country:GB`, `country:ES`, etc.); **cross-border** competitions (`UEFA Europa League`, `Champions League`, `World Cup`, Olympics, geopolitical treaties) are `global` (or multi-country global), never misattributed to `"us"`.

### 4. Structure (`ladder` | `dated_bucket` | `neither`)
- **`ladder`**: multiple outcomes sweeping thresholds of **one underlying number** (`Above 13000`, `Above 13100`, ..., `Above 13700`, or `Above 5.00%`..`6.75%`).
- **`dated_bucket`**: outcomes splitting **one question across different deadline dates** (`By October 31`, `By December 31`).
- **`neither`**: plain Yes/No, two-sided game/matchup, or multi-contender field (`Winner of ...` with team/candidate options). Check the options list carefully—ladders often look like plain questions until you read the options.

### 5. Claim (`measure`, `comparison`, `value`, `unit`, `deadline`)
- Copy values **verbatim from the title or options** — never expand abbreviations or invent unprinted numbers:
  - Season strings like `"2026-27"` are **not** a numeric threshold `value: "27"`.
  - Team/brand substrings like `"W7M"` are **not** `value: "7M"`.
  - If the title says `"13M subscribers"`, copy `"13M"` verbatim (do not rewrite `"13000000"`).
- Leave the claim **blank** on qualitative winner / yes-no questions without an explicit numeric threshold (`"Will Commanders advance?"`).

### 6. Stakes and Breadth (`1–5`, asked last)
- Score independently using the common-sense anchor:
  - `1`: Hyper-local seat, niche daily stat, single city weather high, obscure prop (`Vermont House Orleans-3` is `stakes=1, breadth=1`).
  - `2`: Normal regular-season game, minor regional/company metric.
  - `3`: Major national game/round, marquee earnings/economic print, senator/governor race.
  - `4`: Championship final, Supreme Court/cabinet/Fed rate move, major geopolitical treaty.
  - `5`: Presidential election, war/peace inflection, global macro shock.

## Tiebreak Rules (Third Look)
- Only triggered after both primary and second raters have completed the market and disagree on at least one fact field (`subjects`, `event_date`, `geography`, `structure`, `claim_frame`).
- Inspect both fact answers + title/options/rules and cite the exact phrase or rule in **`evidence_note`** (required).
- **Never** tiebreak `stakes` or `breadth`.
