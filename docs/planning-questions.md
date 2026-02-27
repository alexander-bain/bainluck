# Planning Questions

These question sets are designed to be answered asynchronously. Your answers will form the basis for implementation plans. No need to answer everything at once — partial answers are fine, and "I don't know yet" is a valid answer that will prompt follow-up discussion.

---

## §1: Bespoke Category Landing Pages

### Vision & Scope

1. The Oscars page is the current prototype for this pattern — what do you love about it, and what would you change? What's the "feel" you want replicated across other categories?

2. Which categories should get bespoke pages first? Rank these by priority:
   - Major sports: Basketball (NBA/NCAAB), Football (NFL/NCAAF), Baseball (MLB), Hockey (NHL), Soccer (EPL/UCL/etc.), Golf, Tennis, MMA
   - Non-sports: Politics, Entertainment, Weather, Crypto/Economics, Miscellany/Fun
   - Or is there a category not listed here that you'd want first?

3. Should there be a "miscellany" or "wild card" category that's intentionally eclectic (weather + crypto + culture + "will X happen?")? What would you call it?

4. How static vs. dynamic should these pages be? Options:
   - a) Fully hand-crafted per category (like Oscars: custom section ordering, custom enrichment APIs, bespoke visual treatment)
   - b) A shared template system where each category plugs in its own hero, color scheme, and section ordering, but the rendering engine is shared
   - c) Some hybrid (bespoke for top 3-4, template for the rest)

### Design Language

5. Should each category have its own color palette/theme, or stay within Bain Luck's existing dark design system with accent colors?

6. What visual elements make a landing page feel "bespoke" to you? Pick all that apply:
   - Category-specific hero imagery (golf course, basketball court, Capitol building)
   - Custom typography choices per category
   - Category-specific data enrichment (e.g., course maps for golf, electoral maps for politics)
   - Unique card layouts (not just the standard EventCard/FuturesCard)
   - Background textures or patterns
   - Category-specific iconography

7. Should these pages have a "curated editorial" feel (like a magazine cover) or a "live dashboard" feel (like a command center)?

### Content & Data

8. For a **basketball** landing page, what sections would you want? Draft ideas:
   - Live games with team colors, Pulse badges
   - Championship odds (top 8 teams, visual bracket-style?)
   - MVP/awards race
   - "Biggest movers this week" (teams whose odds shifted most)
   - Upcoming marquee matchups
   - Recent results with Pulse scores
   - Something else?

9. For a **politics** landing page, what sections would you want?
   - Presidential election odds
   - Congressional/Senate odds
   - Policy markets (Fed rate, legislation passage)
   - Approval ratings
   - Comparison to prediction market aggregators (RCP, 538)
   - Something else?

10. For a **golf** landing page:
    - Active tournament leaderboard odds
    - Major championship futures
    - Player rankings vs. odds comparison
    - Historical major winners
    - Something else?

11. Should category pages show content from ALL sources (Odds API + Kalshi + Polymarket) or filter to the most relevant?

12. How should the category page relate to the main feed? Options:
    - a) Category page replaces the feed for that category (standalone experience)
    - b) Category page is a richer entry point that links back to individual events/futures
    - c) Both — category page has its own curated view, plus a "See all" link to filtered feed

### Technical & Enrichment

13. For sports categories, should we integrate sport-specific APIs beyond what we already have? Examples:
    - Golf: PGA Tour leaderboard API
    - Soccer: league tables, Champions League bracket
    - Tennis: ATP/WTA rankings
    - Or keep it odds-only and let the visual treatment do the differentiation?

14. Should category pages have their own URL structure? Options:
    - a) `/basketball`, `/politics`, `/golf` (clean, shareable)
    - b) `/categories/basketball` (organized under a parent)
    - c) `/explore/basketball` (discovery framing)

15. Should the landing pages be server-rendered (for SEO) or client-rendered (for interactivity)?

16. How often do you expect to update the "bespoke" aspects of each page? Should there be a CMS-like admin interface, or is editing code directly fine since categories don't change much?

---

## §2: "What Are the Odds?" Game

### Core Mechanics

1. What's the core loop? Options:
   - a) **Single question**: Show one event/future, user guesses probability, get instant feedback
   - b) **Round of 5-10**: Batch of questions, score at the end
   - c) **Daily challenge**: Same questions for all users each day (like Wordle), compare scores
   - d) **Endless mode**: Keep going until you want to stop, track running average
   - e) Some combination?

2. What does the user see when guessing? Options:
   - a) Slider from 0-100% (precise but slower)
   - b) Multiple choice: pick from 4 probability options (e.g., 15%, 35%, 55%, 80%)
   - c) Over/Under: "Is this team's chance above or below 40%?" (simplest)
   - d) Bracket: "Is this between 0-25%, 25-50%, 50-75%, 75-100%?" then refine
   - e) Free-form number entry

3. What types of questions should be asked? All of these, or a subset?
   - "What are the Lakers' chances of winning tonight?" (live game)
   - "What are the Chiefs' chances of winning the Super Bowl?" (futures)
   - "What are the odds of rain in NYC tomorrow?" (non-sports, if we have weather)
   - "Who's more likely to win MVP: Jokic or Shai?" (comparative)
   - "What are the odds of Bitcoin hitting $100k by June?" (crypto)
   - Historical: "The Celtics were down 15 in Q3. What were their odds at that point?" (using our snapshot data)

4. How should we score accuracy? Options:
   - a) **Brier Score**: Mean squared error of probability estimates (standard in forecasting)
   - b) **Points system**: Closer = more points, with bonus for confidence (gaming feel)
   - c) **Letter grades**: A through F based on accuracy ranges
   - d) **Calibration score**: Track whether your "70% guesses" happen 70% of the time over many rounds

5. Should difficulty scale? Ideas:
   - Easy: "Are the Warriors favored or underdogs tonight?" (binary)
   - Medium: "What are the Warriors' chances tonight?" (within 10%)
   - Hard: "What are the Warriors' chances of winning the championship?" (small number, hard to estimate)
   - Expert: Comparative or multi-part questions

### Social & Viral

6. What makes this shareable? Options:
   - a) Daily score card image (like Wordle's green/yellow/gray grid)
   - b) "I scored better than 87% of players today"
   - c) Challenge a friend: "Beat my score on today's questions"
   - d) Streak counter: "5-day prediction streak"
   - e) Some combination?

7. Should there be multiplayer? Options:
   - a) No — solo experience only
   - b) Asynchronous: compare scores on the same daily challenge
   - c) Real-time: head-to-head prediction battles during live games
   - d) Group/party mode: everyone in a room answers simultaneously

8. Leaderboards — which ones?
   - All-time accuracy
   - Daily/weekly/monthly
   - By category (sports, politics, etc.)
   - Friends-only (requires auth)
   - None (personal best only)

### Content Selection

9. How should we pick which events/futures to feature as questions?
   - Random from active markets?
   - Curated "interesting" ones (high Pulse, close odds, marquee events)?
   - Difficulty-balanced (mix of easy/hard)?
   - Personalized to user's sport preferences?

10. Should questions have a time limit? If so, how long?

11. How do we handle the "reveal" moment? The user guesses 35%, the real answer is 42%. How do we make that feel satisfying rather than deflating?
    - Show how close they were relative to other guessers?
    - Show it on a visual scale?
    - Show an explanation of why the odds are what they are?

12. For futures (which resolve over months), how do we handle scoring? Options:
    - a) Score against current market odds (immediate feedback, but market could be wrong)
    - b) Wait for resolution (accurate but delayed — user forgets)
    - c) Both: immediate score vs. market, then bonus/penalty when the event resolves

### Identity & Retention

13. Does the game require authentication? Options:
    - a) Anonymous play, auth only for leaderboards/streaks
    - b) Auth required (simplifies score tracking)
    - c) Anonymous with localStorage history, auth unlocks cross-device + social

14. How do we bring players back?
    - Daily challenge (new questions each day, same for everyone)
    - Push notifications ("Tonight's NBA games are live — can you beat your score?")
    - Streak mechanics (lose your streak if you miss a day)
    - Weekly tournaments
    - Seasonal themes (playoff prediction tournament, election special)

15. What's the name? "What Are the Odds?" is the working title. Other options:
    - "Odds Quiz"
    - "Probability Challenge"
    - "The Line" (betting reference)
    - "Call It" (prediction framing)
    - Something that ties to the Bain Luck brand?

16. Should the game live at a dedicated URL (`/game`, `/play`, `/quiz`) or be integrated into the main experience (e.g., a game card in the feed)?

### Monetization & Legal

17. Any concern about the game feeling too "gambling-adjacent"? We're not taking money, but probability guessing on sports events could attract scrutiny. Should we emphasize non-sports categories to broaden the positioning?

18. Should we ever offer prizes (gift cards, merch) for top scores, or keep it purely for fun/bragging rights?

---

## §3: Insight Arena (Admin LLM Training)

### Insight Generation

1. What makes a good insight to you? Pick examples that resonate:
   - "The Celtics' championship odds have dropped 5% this week despite going 3-1 — the losses were to playoff teams."
   - "67% of NBA games today are within 5% of 50/50 — an unusually competitive slate."
   - "Since Chet Holmgren's injury, the Thunder's title odds dropped from 18% to 12%."
   - "Golf's PGA Championship field has the tightest top-5 odds spread in 3 years."
   - "The market thinks Lakers-Celtics is the most important game tonight — winner's championship odds jump ~2%."
   - "Bitcoin is at 73% to hit $100k by March — up from 45% two weeks ago."
   - Something else entirely?

2. What does a BAD insight look like? Examples to avoid:
   - Too obvious: "The team with better odds is favored to win."
   - Too niche: "The 14th-ranked tennis player's odds shifted 0.3%."
   - Too speculative: "If the Dolphins win their next 5 games, they could make the playoffs."
   - Just data: "There are 12 NBA games today." (no "so what?")

3. What are the scopes for insights?
   - **Event-level**: About a specific game ("This is the closest NBA game tonight — 51/49")
   - **Category-level**: About a sport or topic ("NFL playoff picture: 3 teams within 1% of each other for the last wild card")
   - **Cross-category**: Connecting different domains ("More people think Bitcoin hits $100k than think the Bills win the Super Bowl")
   - **DB-wide / meta**: About the platform's data ("We tracked 847 live games this week — the average Pulse score was 52, highest was 97")
   - **Temporal**: About trends over time ("Championship odds for the top 4 NBA teams have barely moved in 2 weeks — market is 'locked in'")
   - All of the above?

4. How many insights should the LLM generate per cycle? And how often?
   - 10 per hour? 50 per day? 100 per day?
   - Should it be triggered manually or on a schedule?

### The A/B Training Interface

5. When you see two insights side by side, what criteria will you use to pick the "better" one? Options to formalize:
   - More surprising / non-obvious
   - More actionable / "makes me want to click"
   - Better written / more concise
   - More relevant to what's happening right now
   - Better use of data (specific numbers, not vague)
   - Some combination — should we ask you to label WHY you preferred it?

6. Should the comparison be strictly A vs. B (binary choice), or should there be more options?
   - a) A vs. B only
   - b) A vs. B + "Both good" + "Both bad"
   - c) Rate each independently 1-5, then compare
   - d) A vs. B + "Why?" free-text

7. Should you be able to edit an insight to show the LLM what you'd prefer? ("This insight is close, but here's how I'd rewrite it...")

8. How should training data accumulate?
   - a) **Few-shot prompting**: Winning insights become examples in the LLM prompt ("Here are 10 insights the user liked...")
   - b) **Style guide extraction**: After N comparisons, ask the LLM to write a "style guide" summarizing your preferences, then use that guide in future prompts
   - c) **Fine-tuning dataset**: Export preference pairs for actual model fine-tuning (more expensive, more powerful)
   - d) Some layered approach (start with few-shot, graduate to style guide, eventually fine-tune)

### Data & Queries

9. What structured data should the LLM have access to when generating insights?
   - Current odds for all live/upcoming events
   - Odds deltas (24h change, 7d change)
   - Pulse scores for live/recent events
   - Championship odds top N per sport
   - Recent line movements
   - Prediction market vs. sportsbook divergences
   - Event importance / tier
   - Something else?

10. Should insights reference specific events/futures by name, or be more abstract? ("Celtics at 22% for the title" vs. "One Eastern Conference team has seen a 5% drop...")

11. What's the freshness requirement? Should insights always be about data from the last 24 hours, or can they reference weekly/monthly trends?

### Graduation Path

12. When do insights graduate from admin-only to user-facing? Options:
    - a) Never — this is purely for your entertainment / product intuition
    - b) After N rounds of training, deploy a "Daily Insight" card on the homepage
    - c) After training, power the "Related Futures Summary" LLM and line movement explanations with the learned style
    - d) Eventually become push notifications ("Bain Luck Insight: ...")

13. If insights do go user-facing, where should they appear?
    - Homepage "Insight of the Day" card
    - Category landing page header insight
    - Event detail page contextual insight
    - Push notification / email digest
    - Dedicated `/insights` page

14. Should different users see different insights (personalized to their teams/interests), or should everyone see the same curated set?

### Technical

15. What LLM should generate insights? Options:
    - a) GPT-4o-mini (cheap, fast, currently used for categorization — ~$0.02/day)
    - b) GPT-4o (better quality, ~10x cost)
    - c) Claude (different style, good at nuance)
    - d) Start with mini, upgrade if quality plateaus

16. How many preference comparisons do you expect to make per week? This affects how fast the system learns:
    - 5-10/week (casual, check in occasionally)
    - 20-50/week (daily engagement)
    - 100+/week (dedicated training sessions)

17. Should the admin interface be a dedicated page (`/admin/insights`) or a section within the existing admin dashboard?

18. Should there be a "reject both" option that also lets you write what you WISH the insight said? This gives the strongest training signal but requires more effort.

---

## How to Use This Document

When you're ready to answer some of these, you can:
1. Answer in any order — skip what you're unsure about
2. Say "default" to let Claude pick a reasonable default
3. Answer partially ("for basketball, definitely X, but I'm unsure about politics")
4. Add new questions that these sparked

Your answers will be used to write implementation plans for each feature.
