# Content Understanding Fact-Labeling Guidelines (One-Page Reference)

Applies to the dual-rater labeling pass on the mandatory 5-card practice round, the frozen sealed (`300`) set, and the development (`200`) set at `/admin/cu-labeling`. Grounded in the five prior grading rounds and the offline fault library.

> **Everything on the card itself:** Every field on `/admin/cu-labeling` carries its own plain sentence and example directly beneath the field heading, and every choice under **Where** defines what belongs there with an example. You never need to open this page to label a market.

## Core Ground Rules

1. **Practice round first (5 cards).** Every person labeling starts on a 5-card practice round that shows the right answer and a short explanation after each card. The sealed test set opens automatically after the fifth practice card is saved.
2. **Label blindly.** Please label on your own. Nobody sees another labeler's answers while working on the sealed or dev sets.
3. **Evidence over guessing.** Use the card text, then the **"Open on Kalshi / Polymarket"** link, then any fixed public date you are sure of (such as an election day). Choose **`Cannot tell`** only when none of those settles the day.
4. **Facts first, taste last.** Answer Questions 1–3 (facts) before Questions 4–5 (`stakes` and `breadth`, `1–5`). Fact disagreements go to a third-look tiebreak with written evidence; `stakes` and `breadth` go straight to product review.
5. **Dev set `shared_100` vs sealed `shared_100`.** On the sealed set, `shared_100` is a representative stratified draw (`67` reader-weighted + `33` spread). On the development set, `shared_100` leads with the `100` markets that changed between repeated runs — the hardest markets — so dual-rater agreement on `dev` reads lower than on `sealed`.

---

## Matching Rules (Changed Before the First Sealed Label — Nov 28, 2026)

> **Pre-label update notice (`472: A`, Nov 28, 2026):** This matching table was **changed before the first sealed human label was saved** (zero sealed labels existed when this update landed, and zero existed through this follow-up). Changes from the prior draft:
> - Removed **Market format** (`junk_flags`) and **Number and comparison** (`frame`) from the human card — those two are checked by deterministic code against the option list and title, paired with a separate 20-card human spot-check proposed on `#13900`.
> - Added **`Cannot tell`** to **The event's own day** (`event_date`), separate from **`No single day`**, and added the venue link on every card. When the resolved human answer is **`Cannot tell`** and a writer states a specific day anyway, the scorecard marks that writer **wrong** (an invented day), while a writer saying it does not know is right; `cannot_tell_event_date_count` keeps the separate count line.
> - Clarified **Who or what is it about?** (teams without competition nouns, named actors beside subjects, elections without candidates, no tickers/cities) and tightened **Where** (`geography`) so its four choices do not overlap.
>
> If dual-rater agreement on **any** remaining field (fact or opinion) falls below `80%`, that field is withheld from the scorecard and sent to Alex with disagreement examples.

| Field | What the labeler answers | What counts as a match |
|---|---|---|
| **1. Which named people, teams, companies or countries is it about?** (`entities`) | Pick candidate chips, click **Add a name** to type one, or choose `"None of these"` / `"Not sure"` | Ignore entity `type` and ignore whether the name came from a chip or Add a name. Lowercase and strip punctuation (`'` removed, punctuation normalized to spaces). A labeled subject is matched when either name contains the other as contiguous whole words. The row is right only when **every** labeled subject is matched. Extra writer-only names are counted separately, not marked wrong. `"None of these"` matches an empty writer list; `"Not sure"` omits the row from scoring. |
| **2. The event's own day** (`event_date`) | Calendar day (`YYYY-MM-DD`), `"No single day"`, or `"Cannot tell"` | Exact calendar day match (`YYYY-MM-DD`), or both `null` when `"No single day"` is chosen. When both raters (or Tie-breaker) choose `"Cannot tell"`, the pair agrees and `cannot_tell_event_date_count` counts it; if the AI writer states a specific calendar day anyway on that market, the scorecard marks it **wrong** (an invented day), whereas a writer saying it does not know (`null` / `"cannot_tell"`) is right. `"Cannot tell"` vs a calendar date or vs `"No single day"` counts as a rater disagreement and routes to Tie-breaker (who opens the venue link to check the full rules). |
| **3. Where** (`geography`) | Non-overlapping choice: `local`, `us`, `country:<XX>`, or `global` | Case-insensitive exact match (`country:XX` two-letter ISO code). Cities anywhere (US or non-US), whole US states, and US state legislative districts are strictly `local` (never `us`); teams in a national league take that league's country (`us` for US leagues, `country:XX` for domestic non-US leagues); non-US national topics and domestic-only firms are `country:<XX>`; cross-border contests, neutral-site international matchups, worldwide company totals (e.g., Ferrari global shipments), and global awards/tech are `global`. |
| **4. How much this matters** (`stakes`) | Integer `1–5` (asked after facts; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. |
| **5. How many people care** (`breadth`) | Integer `1–5` (asked after facts; never tie-broken) | Writer matches within `±1` step. On `shared_100` where two people rated, right when within `±1` of **either** labeler's score. |

*(Code-checked fields — **not asked on this card**: **Market format** (`junk_flags`) and **Number and comparison** (`frame`) are evaluated deterministically against the option list and market title, audited separately via a 20-card spot-check.)*

---

## Field-by-Field Edge Cases

### 1. Which named people, teams, companies or countries is it about? (`subjects`)
- Pick every **specific** named person, team, company, bill, tournament, or country the market turns on — not a place smaller than a country (cities go under **Where**), not a bare stock ticker duplicate (`Amazon`, not `AMZN`), and not an election answer option (`Democratic party` / `Republican party`).
- **Teams beside competitions:** Pick the team (`San Jose Sharks`, not `NHL Playoffs`); pick the competition only when the market is about the competition itself (`NHL Playoffs` with no single team).
- **Actors beside targets:** Pick **all** named actors and targets when companies/agencies act on another subject (`Moody's`, `S&P`, and `France` in `"Moody's or S&P downgrades France"`).
- **Elections:** If named candidates appear, pick those candidates; if a seat/race has only party or generic choices (like `"Vermont House Orleans-3 winner?"` with Democratic/Republican options), choose **`None of these`**.
- **Bilateral / head-to-head events:** Include both sides (`Israel`, `Iran`; `Wake Forest`, `Duke`).
- Use **Add a name** if the true subject is named in the title/options/venue rules but missing from the chips.
- Use **`None of these`** when a market is city weather, a plain market index, or an election seat with no named candidate. Use **`Not sure`** only when genuinely ambiguous.

### 2. The event's own day (`Specific day` · `No single day` · `Cannot tell`)
Read the card first, then open the venue page link if needed, then use any fixed public date you are sure of (such as an election day). Choose **`Cannot tell`** only when none of those settles it:
- **Specific day:** The real-world calendar day the event happens (US Eastern for US fixtures/elections) — **not** the venue's settlement date.
  - *Settlement trap:* `"Kalshi settles this on May 7, 2029"` after a Nov 7, 2028 election → the event's day is `2028-11-07`, not `2029-05-07`.
- **No single day:** Not tied to one day — a month, a season, or a `"by"` / `"before"` / `"through"` deadline where it can trigger on any day in the window (`"China abolish birth limits Before 2027..2030"`, `"Trump pardon in Nov 2026"`).
- **Cannot tell:** Happens on one day and nothing you can read on the card or venue page says which (`"Will Marvell beat quarterly earnings?"` if neither the card nor the venue rules name the earnings release date).

### 3. Where (`Local` · `US (nationwide)` · `One country (outside the US)` · `Global`)
Choices do not overlap — pick the smallest region containing where the event happens or applies:
- **`Local`:** One city/town (anywhere in the world — inside or outside the US, e.g., Denver or Tokyo), one metro area, one whole US state (e.g., California governor), or a US state legislative district (`Vermont House Orleans-3`).
- **`US (nationwide)`:** Federal US politics, US-wide business or macro releases, Fed decisions, or any team/game in a **US national league** (`NBA`, `NFL`, `MLB`, `NHL`, `NCAA`) — use the league's country (`US`), never the team's city (`Local`).
- **`One country (outside the US)` (`country:<XX>`):** National politics, economy, a domestic non-US company, or a domestic sports league inside one single country outside the US (`China birth limits` → `CN`, `France credit rating` → `FR`, `Premier League` → `GB`).
- **`Global (multiple countries)`:** Wars, treaties, or matches involving two or more countries (even when two players/teams from different countries meet in a third country), worldwide business/shipments for an international brand (`Ferrari total car shipments in 2026`), or international competitions (`World Cup`, `Champions League`, `Eurovision`).

### 4–5. How much this matters & how many people care (`1–5`)
- **How much this matters (`stakes`):**
  - `1`: Local seat, city weather high, niche daily stat.
  - `2`: Regular-season game, routine regional or single-company metric.
  - `3`: Major national game/round, marquee earnings or macro print, senate/governor race.
  - `4`: Championship final, Fed decision, court ruling, major international treaty.
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
