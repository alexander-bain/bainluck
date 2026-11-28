# Content Understanding Fact-Labeling Guidelines (One-Page Reference)

Applies to the dual-rater labeling pass on the mandatory 5-card practice round, the frozen sealed (`300`) set, and the development (`200`) set at `/admin/cu-labeling`. Grounded in the five prior grading rounds and the offline fault library.

> **Everything on the card itself:** Every field on `/admin/cu-labeling` carries its own plain sentence and example directly beneath the field heading, and every choice under **Where** defines what belongs there with an example. You never need to open this page to label a market.

## Core Ground Rules

1. **Practice round first (5 cards).** Every person labeling starts on a 5-card practice round that shows the right answer and a short explanation after each card. The sealed test set opens automatically after the fifth practice card is saved.
2. **Label blindly.** Never discuss answers with the other labeler while working on the sealed or dev sets. Both labelers submit independently; neither sees the other's answers while working.
3. **Evidence over guessing.** Use the card text plus the **"Open on Kalshi / Polymarket"** link when the title is not enough to determine the real event date or place. When neither the card nor the venue rules establish an answer, choose `"None of these"`, `"Not sure"`, `"No single day"`, or `"Cannot tell from this card"`.
4. **Facts first, taste last.** Answer Questions 1–3 (facts) before Questions 4–5 (`stakes` and `breadth`, `1–5`). Fact disagreements go to a third-look tiebreak with written evidence; `stakes` and `breadth` are **never** tie-broken (disagreements go to product review).
5. **Dev set `shared_100` vs sealed `shared_100`.** On the sealed set, `shared_100` is a representative stratified draw (`67` reader-weighted + `33` spread). On the development set, `shared_100` leads with the `100` markets that changed between repeated runs — the hardest markets — so dual-rater agreement on `dev` reads lower than on `sealed`.

---

## Matching Rules (Changed Before the First Sealed Label — Nov 28, 2026)

> **Pre-label update notice (`472: A`, Nov 28, 2026):** This matching table was **changed before the first sealed human label was saved** (zero sealed labels existed when this update landed). Changes from the prior draft:
> - Removed **Market format** (`junk_flags`) and **Number and comparison** (`frame`) from the human card — those two are checked by deterministic code against the option list and title, paired with a separate 20-card human spot-check proposed on `#13900`.
> - Added **`Cannot tell from this card`** to **The event's own day** (`event_date`), separate from **`No single day`**, and added the venue link on every card.
> - Tightened **Where** (`geography`) so its four choices do not overlap.
>
> If dual-rater agreement on **any** remaining field (fact or opinion) falls below `80%`, that field is withheld from the scorecard and sent to Alex with disagreement examples.

| Field | What the labeler answers | What counts as a match |
|---|---|---|
| **1. Who or what is it about?** (`entities`) | Pick candidate chips, type custom names, `"None of these"`, or `"Not sure"` | Ignore entity `type` and ignore whether the name came from a chip or Custom. Lowercase and strip punctuation (`'` removed, punctuation normalized to spaces). A labeled subject is matched when either name contains the other as contiguous whole words. The row is right only when **every** labeled subject is matched. Extra writer-only names are counted separately, not marked wrong. `"None of these"` matches an empty writer list; `"Not sure"` omits the row from scoring. |
| **2. The event's own day** (`event_date`) | Calendar day `YYYY-MM-DD`, `"No single day"`, or `"Cannot tell from this card"` | Exact calendar day match (`YYYY-MM-DD`), or both `null` when `"No single day"` is checked. When both raters choose `"Cannot tell from this card"` (or Tie-breaker resolves it as `"Cannot tell"`), the pair agrees, `event_date` is omitted from scorecard scoring (neither right nor wrong, mirrored to `"Not sure"` on subjects), and it is counted separately on `cannot_tell_event_date_count`. `"Cannot tell"` vs a calendar date or vs `"No single day"` counts as a disagreement and routes to Tie-breaker (who opens the venue link to check the full rules). |
| **3. Where** (`geography`) | Non-overlapping choice: `local`, `us`, `country:<XX>`, or `global` | Case-insensitive exact match (`country:XX` two-letter ISO code). State legislative districts and cities are strictly `local` (never `us`); US nationwide topics/federal agencies/leagues are strictly `us`; non-US national topics are `country:<XX>`; cross-border contests/wars/global awards are `global`. |
| **4. How much this matters** (`stakes`) | Integer `1–5` (asked after facts; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. |
| **5. How many people care** (`breadth`) | Integer `1–5` (asked after facts; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. |

*(Code-checked fields — **not asked on this card**: **Market format** (`junk_flags`) and **Number and comparison** (`frame`) are evaluated deterministically against the option list and market title, audited separately via a 20-card spot-check.)*

---

## Field-by-Field Edge Cases

### 1. Who or what is it about? (`subjects`)
- Pick the **specific** person, team, company, organization, bill, tournament, or country the outcome turns on — not a broad category label.
- Include both sides of a head-to-head fixture or bilateral event (`Israel`, `Iran`; `Wake Forest`, `Duke`), not just the first name.
- When both a company name and its stock ticker appear as chips (`Amazon` and `AMZN`), pick the company name (`Amazon`).
- Use **Custom** if the true subject is named in the title/options/venue rules but missing from the candidate chips.
- Use **`None of these`** when a market is purely city weather, a plain market index, or an unnamed macro series (`"Highest temperature in Denver on November 28?"`). Use **`Not sure`** only when genuinely ambiguous.

### 2. The event's own day (`Specific day` · `No single day` · `Cannot tell from this card`)
- **Specific day (`YYYY-MM-DD`):** Record the **real-world day the event happens** (US Eastern calendar day for US fixtures/elections), **not** the platform contract settlement/payout timestamp.
  - *Settlement-echo trap:* Venue payout timestamps (`"The site pays out on May 7, 2029"`) often fall weeks or months after Election Day or a game. For `"Vermont House Orleans-3 winner? (2028)"`, the event's day is `2028-11-07`, not `2029-05-07`.
- **No single day:** Use when the outcome spans multiple days/weeks/years OR is phrased as a deadline window (`"by November 30"`, `"through November 30"`, `"Before 2030"`, `"How many people will Trump pardon in Nov 2026?"`), because the triggering event can occur on any day inside that window.
- **Cannot tell from this card:** Use when the market probably turns on a specific day (like `"Will Marvell beat quarterly earnings?"`) or is unclear, and neither the card nor the venue link shows the calendar day.

### 3. Where (`Local` · `US (nationwide)` · `One country (outside the US)` · `Global`)
Choices are strictly mutually exclusive — pick the single smallest region containing the market:
- **`Local`:** One city, county, metro area, or **US state legislative district** (`Highest temperature in Denver`, `NYC mayor`, `Vermont House Orleans-3`). Even though state legislatures sit inside the US, local and state-district races are `Local`, never `US (nationwide)`.
- **`US (nationwide)`:** Federal US politics, US-wide business/macro releases, Fed decisions, or US national leagues (`NBA`, `NFL`, `MLB`, `NHL`, `NCAA`) — excluding single-city and state-district races.
- **`One country (outside the US)` (`country:<XX>`):** National politics, economy, weather, or a domestic league inside one single country outside the US (`China birth limits` → `country:CN`, `France credit rating` → `country:FR`, `Premier League` → `country:GB`).
- **`Global (multiple countries)`:** Cross-border contests, wars or treaties between nations (`Israel x Iran ceasefire`), international sports (`Champions League`, `World Cup`), or worldwide awards/technology (`Eurovision`, global AI benchmarks).

### 4–5. How much this matters & how many people care (`1–5`, asked last)
- **How much this matters (`stakes`):**
  - `1`: Local seat, city weather high, niche daily stat (`Vermont House Orleans-3`, `Highest temperature in Denver`).
  - `2`: Regular-season game, minor regional or single-company metric.
  - `3`: Major national game/round, marquee earnings or macro print, senate/governor race.
  - `4`: Championship final, Fed decision, Supreme Court/cabinet move, major international treaty.
  - `5`: Presidential election, war/peace shift, global macro shock.
- **How many people care (`breadth`):**
  - `1`: Handful of locals or niche fans follow this.
  - `2`: Fans of one team, state, or industry care.
  - `3`: National sports, politics, or market followers know it.
  - `4`: Most people in a country or major sport pay attention.
  - `5`: Household-name story people follow worldwide.

## Tiebreak Rules (Third Look)
- Triggered only after both first and second labelers finish a market and disagree on at least one fact field (`subjects`, `event_date`, `geography`).
- Inspect both peer fact answers plus the title/options/venue link and cite the exact phrase or rule in **`evidence_note`** (required).
- **Never** tiebreak `stakes` or `breadth`.
