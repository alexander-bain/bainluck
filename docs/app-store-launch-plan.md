# App Store Launch Plan

Everything you need to submit Bain Luck to the App Store. Estimated time: 2 hours.

---

## Step 1: App Store Connect — App Information (10 min)

Go to [App Store Connect](https://appstoreconnect.apple.com) → My Apps → Bain Luck → App Information.

**Name:** `Bain Luck`

**Subtitle (30 chars):**
```
Prediction Market Probabilities
```

**Primary Category:** Sports

**Secondary Category:** News

**Content Rights:** Does not contain third-party content that requires rights (the app displays publicly available market data)

**Age Rating:** Fill out the questionnaire — answer No to all (no gambling, violence, mature content, etc.)

---

## Step 2: App Store Connect — Pricing (1 min)

**Price:** Free

---

## Step 3: App Store Connect — App Privacy (5 min)

**Privacy Policy URL:**
```
https://bainluck.com/privacy
```

**Data Collection:** Yes, the app collects data:
- **Identifiers** → User ID → App Functionality → Linked to User
- **Usage Data** → Product Interaction → Analytics → Not Linked to User
- **No tracking** (already set in privacy manifest)

---

## Step 4: Version Information (15 min)

Go to App Store Connect → My Apps → Bain Luck → iOS App → the version you're submitting.

### Description (4000 chars max)

```
Bain Luck translates prediction markets and betting odds into simple probabilities. See "60% vs 40%" instead of confusing odds formats.

WHAT THE WORLD THINKS WILL HAPPEN

Browse hundreds of prediction markets across sports, politics, economics, entertainment, weather, and tech — all showing clear probabilities, not betting lines.

DISCOVER FEED
Your personalized feed of the most interesting predictions happening right now. See what moved, what's surprising, and what's about to resolve. Swipe through cards and test your intuition with Higher or Lower predictions.

LIVE GAME PROBABILITIES
Watch win probabilities shift in real-time during live games. Multi-source charts combine sportsbook odds, ESPN data, and statistical models into one view.

CHAMPIONSHIP GRIDS
See every team's championship odds at a glance. Track how playoff paths evolve across NBA, NHL, MLB, NFL, and more.

PREDICTION MARKETS
Explore thousands of Kalshi and Polymarket markets on elections, Fed policy, movie box office, weather, tech milestones, and more — with cross-source comparison when the same question appears on multiple platforms.

CALIBRATION
See how accurate prediction markets actually are. Our calibration curve shows 60,000+ resolved predictions with per-source and per-category accuracy breakdowns.

DAILY CHALLENGE
Test your probability intuition with 5 questions per day. Track your streak and see how you compare.

KEY FEATURES
• Probability-first: everything shown as clear percentages
• Multi-source: combines sportsbooks, Kalshi, Polymarket, ESPN, and stat models
• Live updates: real-time probability charts during games
• Prediction game: Higher or Lower guessing with accuracy tracking
• Championship paths: playoff grids for every major league
• Category pages: politics, entertainment, economics, weather
• Universal links: share any event or market
• iPad and Mac support
```

### Keywords (100 chars max, comma-separated)

```
prediction,market,probability,odds,sports,politics,Kalshi,Polymarket,live,scores,NBA,NFL,MLB,NHL
```

### Support URL

```
https://bainluck.com/about
```

### Marketing URL (optional)

```
https://bainluck.com
```

### What's New in This Version

```
• Discover feed: personalized prediction market cards with Higher/Lower game
• Daily Challenge: 5 questions per day with streak tracking
• Friend Challenges: challenge friends to prediction duels via shareable links
• Calibration page: see how accurate prediction markets really are
• Probability model comparison: view methodology for each source
• Browse All Futures: access every prediction market from iPhone
• Championship grids with live playoff odds
• 5 category pages: politics, entertainment, economics, weather, preferences
• Bug fixes and performance improvements
```

---

## Step 5: Screenshots (1-2 hours)

You need screenshots for at least **iPhone 6.7"** (required). iPad 13" is optional but recommended.

### What to capture (5 screenshots, in order):

1. **Discover feed** — showing 2-3 cards with probabilities, category pills visible
2. **Live game** — event detail page during a live game with the probability chart
3. **Championship grid** — NBA or NHL playoff odds grid
4. **Politics or Entertainment** — a category page with market cards
5. **Calibration** — the calibration curve chart

### How to take them:

**On your iPhone (easiest):**
- Open the TestFlight build
- Navigate to each screen
- Screenshot (Side button + Volume Up)
- AirDrop to your Mac

**Upload to App Store Connect** → Version → Screenshots → drag and drop per device size.

---

## Step 6: App Review Notes (5 min)

Paste this into App Store Connect → Version → App Review Information → Notes:

```
Bain Luck is an informational app that displays publicly available prediction market data and sports odds as probabilities. It does NOT facilitate gambling, accept wagers, or process payments.

The app shows data from:
- Public sportsbook odds (via The Odds API)
- Kalshi (CFTC-regulated prediction exchange)
- Polymarket (public prediction market)
- ESPN (live game data)

No demo account is needed — users can browse all content without signing in. Sign in with Apple or Google is available for personalization features (favorites, predictions).

The "Higher or Lower" prediction game is for entertainment only — no money is wagered or won. Users simply guess whether a probability is higher or lower than a threshold.
```

---

## Step 7: Submit for Review (2 min)

1. Make sure Build 3 (or 4 if you re-archived) is selected in the version
2. Click **Add for Review**
3. Click **Submit to App Review**

Apple typically reviews within 24-48 hours.

---

## Before You Submit — Quick Checklist

- [ ] Description pasted
- [ ] Keywords pasted
- [ ] Subtitle set
- [ ] Support URL set (`https://bainluck.com/about`)
- [ ] Privacy Policy URL set (`https://bainluck.com/privacy`)
- [ ] Age Rating questionnaire completed
- [ ] Price set to Free
- [ ] App Privacy section completed
- [ ] At least 5 iPhone 6.7" screenshots uploaded
- [ ] What's New text pasted
- [ ] App Review notes pasted
- [ ] Build selected

---

## After Approval

1. **Remove `BYPASS_RATE_LIMITS`** — Already done ✅
2. **Re-enable CI auto-deploy** — The deploy job in GitHub Actions was disabled. Re-enable it so pushes to master auto-deploy to Heroku again.
3. **In-app review prompt** — Add `SKStoreReviewController.requestReview()` after 5+ sessions (AS-14, nice-to-have)
4. **Monitor crash reports** — Check App Store Connect → Crashes after first week
