# App Store Launch Plan

Everything needed to submit Bain Luck 1.0 to the App Store. Realistic time: **3-4 hours** (mostly screenshots).

**Current state:** Build 3 on TestFlight, gambling language removed (commit `cea3892`), privacy policy live, privacy manifest in place. Main remaining work is screenshots + App Store Connect metadata.

---

## Phase 1: Pre-Submission Technical Work (30 min)

Do these in Xcode before archiving.

### 1.1 Bump Build Number

Every App Store / TestFlight upload needs a unique build number. Build 3 is already on TestFlight, so bump to 4+.

In Xcode: **Bain Luck target → General → Build** — change from `3` to `4` (or whatever's next).

Or in `project.pbxproj`, find `CURRENT_PROJECT_VERSION = 3` under the main app target (lines ~518, ~565) and increment both.

### 1.2 Dark/Tinted App Icon (Recommended)

The `AppIcon.appiconset/Contents.json` declares dark and tinted icon slots but no images are assigned. On iOS 18+, the system auto-generates dark variants — your white-background clover will look washed out.

**Options:**
- **Best:** Create `icon_1024_dark.png` (clover on dark background) and `icon_1024_tinted.png` (monochrome version), add to `Contents.json`
- **Acceptable:** Remove the empty dark/tinted slots from `Contents.json` — system will just use the light icon everywhere
- **Risky:** Do nothing — auto-generated dark variant may look bad

### 1.3 Deployment Target Review

Current settings in `project.pbxproj`:

| Platform | Target | Concern |
|----------|--------|---------|
| iOS | 17.0 | Good — covers ~95% of active devices |
| macOS | 26.2 | Only runs on macOS 26.2+ (current beta) |
| visionOS | 26.2 | Only runs on visionOS 26.2+ |
| watchOS | 26.0 | Only runs on watchOS 26.0+ |

**Decision needed:** The macOS/visionOS/watchOS targets correspond to the Xcode 26 beta SDK defaults. If you're submitting from Xcode 26, these are fine for initial launch — users on older OS versions just can't install. If you want broader macOS reach, lower `MACOSX_DEPLOYMENT_TARGET` to 14.0 or 15.0 (will need testing).

### 1.4 Watch App: Include or Exclude?

The Watch app is included in the build (`Embed Watch Content` build phase). Per earlier testing, content was unreliable. **Options:**
- **Include it** — it'll be reviewed alongside the main app. If it crashes, the whole submission gets rejected.
- **Remove the embed** — ship Watch app in a later update once it's stable. Safer for v1.0.

To remove: In Xcode, select Bain Luck target → Build Phases → delete "Embed Watch Content" phase. You can add it back later.

### 1.5 visionOS: Include or Exclude?

`SUPPORTED_PLATFORMS` includes `xros xrsimulator` and `TARGETED_DEVICE_FAMILY` includes `7` (visionOS). Unless you've tested on Vision Pro, consider removing to avoid review issues.

To remove: In Xcode, select Bain Luck target → General → Supported Destinations → remove visionOS.

---

## Phase 2: Archive & Upload (15 min)

### 2.1 Archive

1. In Xcode, select **Bain Luck** scheme (not BainLuckWatch)
2. Set destination to **Any iOS Device (arm64)**
3. **Product → Archive** (⌘⇧B won't work — must use Archive)
4. Wait for build to complete (2-3 min)

### 2.2 Upload to App Store Connect

1. Xcode opens the **Organizer** window automatically after archive
2. Select the new archive → **Distribute App**
3. Choose **App Store Connect** → **Upload**
4. Leave all checkboxes at defaults (bitcode, symbols, etc.)
5. Xcode auto-signs with your team (`J893F72P4R`) — if it fails, go to Signing & Capabilities and ensure "Automatically manage signing" is checked
6. Click **Upload** — takes 1-2 min
7. Wait ~15 min for App Store Connect to process the build (you'll get an email)

### 2.3 Verify in App Store Connect

Go to [App Store Connect](https://appstoreconnect.apple.com) → My Apps → Bain Luck → TestFlight. The new build should appear. If there are compliance warnings, check the email — usually it's about missing privacy manifest entries from third-party SDKs (Firebase handles its own).

---

## Phase 3: App Store Connect Metadata (20 min)

### 3.1 App Information

Go to App Store Connect → My Apps → Bain Luck → **App Information**.

| Field | Value |
|-------|-------|
| **Name** | `Bain Luck` |
| **Subtitle** (30 chars) | `Prediction Market Probabilities` |
| **Primary Category** | Sports |
| **Secondary Category** | News |
| **Content Rights** | Does not contain third-party content that requires rights |
| **Age Rating** | Fill out questionnaire — answer **No** to all. The app does NOT facilitate gambling. The Higher/Lower game has no stakes. |

### 3.2 Pricing

**Price:** Free

### 3.3 App Privacy

| Field | Value |
|-------|-------|
| **Privacy Policy URL** | `https://bainluck.com/privacy` |
| **Data Collection** | Yes |

**Data types to declare:**

| Data Type | Category | Purpose | Linked to User? |
|-----------|----------|---------|-----------------|
| User ID | Identifiers | App Functionality | Yes |
| Product Interaction | Usage Data | Analytics | No |

No tracking. Already matches `PrivacyInfo.xcprivacy`.

### 3.4 Version Information

Go to App Store Connect → My Apps → Bain Luck → iOS App → prepare the version.

**Description** (4000 chars max):

```
Bain Luck translates prediction markets into simple probabilities. See "60% vs 40%" instead of confusing formats.

WHAT THE WORLD THINKS WILL HAPPEN

Browse hundreds of prediction markets across sports, politics, economics, entertainment, weather, and tech — all showing clear probabilities.

DISCOVER FEED
Your personalized feed of the most interesting predictions happening right now. See what moved, what's surprising, and what's about to resolve. Swipe through cards and test your intuition with Higher or Lower predictions.

LIVE GAME PROBABILITIES
Watch win probabilities shift in real-time during live games. Multi-source charts combine data from sportsbook consensus, ESPN, and statistical models into one view.

CHAMPIONSHIP GRIDS
See every team's title chances at a glance. Track how paths evolve across NBA, NHL, MLB, NFL, and more.

PREDICTION MARKETS
Explore thousands of Kalshi and Polymarket predictions on elections, Fed policy, movie performance, weather, tech milestones, and more — with cross-source comparison when the same question appears on multiple platforms.

CALIBRATION
See how accurate prediction markets actually are. Our calibration curve analyzes resolved predictions with per-source and per-category accuracy breakdowns.

DAILY CHALLENGE
Test your probability intuition with 5 questions per day. Track your streak and see how you compare.

KEY FEATURES
• Probability-first: everything shown as clear percentages
• Multi-source: combines sportsbook consensus, Kalshi, Polymarket, ESPN, and stat models
• Live updates: real-time probability charts during games
• Prediction game: Higher or Lower guessing with accuracy tracking
• Championship paths: grids for every major league
• Category pages: politics, entertainment, economics, weather
• Universal links: share any event or market
• iPad and Mac support

Bain Luck is an informational app. It does not facilitate, encourage, or enable wagering of any kind. No real-money transactions occur in this app.
```

**Keywords** (100 chars max, comma-separated):

```
prediction,market,probability,sports,politics,Kalshi,Polymarket,live,scores,NBA,NFL,MLB,NHL,weather
```

*(Removed "odds" — could trigger gambling review filters. Replaced with "weather" for category coverage.)*

**Support URL:**

```
https://bainluck.com/about
```

**Marketing URL:**

```
https://bainluck.com
```

**What's New in This Version:**

```
Initial release — Bain Luck translates prediction markets into clear probabilities.

• Discover feed with Higher/Lower prediction game
• Daily Challenge with streak tracking
• Live game probability charts
• Championship grids with playoff paths
• Category pages: politics, entertainment, economics, weather
• Calibration: see how accurate markets really are
• iPad and Mac support
```

**Copyright:**

```
© 2026 Alexander Bain
```

---

## Phase 4: Screenshots (1-2 hours)

### Required Device Sizes

Since `TARGETED_DEVICE_FAMILY = "1,2"` (iPhone + iPad), you need:

| Device Size | Dimensions | Required? | What to Use |
|-------------|-----------|-----------|-------------|
| **iPhone 6.7"** | 1290 × 2796 | **Yes** | iPhone 15 Pro Max (or Simulator) |
| **iPhone 6.5"** | 1242 × 2688 | **Yes** (if supporting older notch phones) | iPhone 11 Pro Max Simulator |
| **iPad 13"** | 2048 × 2732 | **Yes** (iPad is a supported device) | iPad Pro 12.9" Simulator |

You can skip 6.5" if you only want to show 6.7" screenshots to all iPhone users — App Store Connect lets you use 6.7" for all sizes.

### What to Capture (5-8 screenshots per device, in order)

| # | Screen | What to Show | Why |
|---|--------|-------------|-----|
| 1 | **Discover feed** | 2-3 cards with probabilities, category pills, swipe hint | This is the landing page — first impression |
| 2 | **Higher/Lower game** | A card mid-guess with the percentage reveal | Core engagement mechanic |
| 3 | **Live game** | Event detail with probability chart during a live game | Differentiator — real-time data |
| 4 | **Championship grid** | NBA or NHL playoff odds grid | Visual wow factor |
| 5 | **Politics or Entertainment** | Category page with market cards | Shows breadth beyond sports |
| 6 | **Calibration** | The calibration curve chart | Credibility — "we measure accuracy" |
| 7 | **Daily Challenge** | Challenge in progress or results | Gamification hook |
| 8 | **Market detail** | A prediction market detail page with cross-source comparison | Shows depth |

### How to Take Them

**Option A — Real device (best quality):**
- Open TestFlight build on iPhone
- Navigate to each screen
- Screenshot (Side button + Volume Up)
- AirDrop to Mac
- Upload to App Store Connect

**Option B — Simulator (if no live games available):**
```bash
# Boot a 6.7" simulator
xcrun simctl boot "iPhone 15 Pro Max"

# Take screenshot
xcrun simctl io booted screenshot ~/Desktop/screenshot_1.png
```

**Option C — Framed screenshots (most polished):**
Use a tool like [Screenshots Pro](https://screenshots.pro) or Figma to add device frames and marketing text above each screenshot. Common for v1.0 launches.

### Tips
- Capture during a live game window (evening ET) for the best live game screenshot
- For the grid, pick a league with active playoff races (visual contrast in probabilities)
- Make sure Discover feed has compelling cards visible — timing matters

---

## Phase 5: App Review Notes & Strategy (10 min)

### Review Notes

Paste into App Store Connect → Version → App Review Information → Notes:

```
Bain Luck is an informational app that displays publicly available prediction market data as probabilities. It does NOT facilitate gambling, accept wagers, or process any payments.

The app aggregates data from:
- Public sportsbook consensus data (via The Odds API)
- Kalshi (CFTC-regulated prediction exchange, publicly available data)
- Polymarket (public prediction market, free API)
- ESPN (live game data)
- Statistical models

No demo account is needed — all content is accessible without signing in. Sign in with Apple or Google is available for optional personalization (favorites, prediction history).

The "Higher or Lower" prediction game is purely for entertainment — it tests probability intuition. No money is wagered, won, or exchanged. No in-app purchases exist.

The app is comparable to: FiveThirtyEight (election forecasts), ESPN (win probability charts), or PredictIt (market data display).
```

### Gambling Review Risk Mitigation

This app sits in a gray area Apple scrutinizes. Key things already done:

- [x] Removed "betting" and "odds" from all user-visible text (commit `cea3892`)
- [x] Description explicitly states "does not facilitate wagering"
- [x] No links to sportsbooks, Kalshi, or Polymarket sign-up pages
- [x] No real-money transactions or IAP
- [x] Age rating questionnaire: gambling = No
- [x] Privacy policy is live

**If Apple flags it as gambling:**
1. Respond to the rejection citing App Store Review Guideline 4.7 (Sports) — the app displays publicly available data, same as ESPN showing win probability
2. Emphasize it's comparable to FiveThirtyEight / RealClearPolitics — data aggregation, not a wagering platform
3. Offer to remove any specific screen or wording they flag
4. If needed, add an explicit "For informational purposes only — not gambling advice" banner

### Contact Information

| Field | Value |
|-------|-------|
| **First Name** | Alexander |
| **Last Name** | Bain |
| **Email** | (your Apple Developer email) |
| **Phone** | (your phone number) |

Apple may call during review if they have questions about the gambling angle. Make sure the phone number is reachable.

---

## Phase 6: Final Checks & Submit (10 min)

### Pre-Submit Checklist

**Technical:**
- [ ] Build number bumped (> 3)
- [ ] Archive built successfully in Xcode
- [ ] Build uploaded to App Store Connect
- [ ] Build processed (check email — usually 15-30 min)
- [ ] No compliance warnings on the build

**App Store Connect:**
- [ ] Description pasted (check: no "betting" or "odds" in text)
- [ ] Keywords pasted
- [ ] Subtitle set
- [ ] Support URL set (`https://bainluck.com/about`)
- [ ] Marketing URL set (`https://bainluck.com`)
- [ ] Privacy Policy URL set (`https://bainluck.com/privacy`)
- [ ] Copyright set
- [ ] Age Rating questionnaire completed (gambling = No)
- [ ] Price set to Free
- [ ] App Privacy section completed (User ID + Product Interaction)
- [ ] At least 5 iPhone 6.7" screenshots uploaded
- [ ] iPad 13" screenshots uploaded (required — iPad is a supported device)
- [ ] What's New text pasted
- [ ] App Review notes pasted with gambling disclaimer
- [ ] Build selected for this version
- [ ] Contact phone number is reachable

### Submit

1. In App Store Connect, go to the version page
2. Click **Add for Review**
3. Answer any final questions (export compliance should auto-fill from Info.plist)
4. Click **Submit to App Review**

Apple typically reviews within **24-48 hours**. You'll get email notifications for status changes.

---

## If Rejected

Common rejection reasons for this type of app and how to respond:

### "Guideline 5.3.4 — Gambling"
**Response:** The app does not facilitate gambling. It displays publicly available data as probabilities — identical to ESPN showing win probability or FiveThirtyEight showing election forecasts. No money changes hands, no wagers are placed, no accounts on betting platforms are created. Offer to add additional disclaimers or remove specific language.

### "Guideline 4.0 — Design (Minimum Functionality)"
**Response:** Unlikely given the app's depth, but if flagged, emphasize: 30+ pages, live data from 5+ sources, 8 sports leagues, 4 non-sports categories, daily challenge game, calibration analysis. Link to specific screens.

### "Guideline 2.1 — Performance (Crashes)"
**Response:** If the Watch app crashes during review, remove it from the build and resubmit. If the main app crashes, check App Store Connect → Crashes for the stack trace, fix, bump build number, re-archive, re-upload.

### "Metadata Rejected"
**Response:** Usually minor — screenshot contains placeholder text, description mentions another platform inappropriately, etc. Fix the metadata and resubmit (no new build needed, usually approved within hours).

### General Tips
- Read the rejection reason carefully — Apple provides specific guideline numbers
- Respond via the Resolution Center in App Store Connect
- Be concise and professional — reviewers handle thousands of apps
- You can request a phone call with the review team if written appeals aren't working

---

## After Approval

### Immediate (Day 1)

- [ ] Verify the app appears in App Store search
- [ ] Download from App Store on a device — full smoke test
- [ ] Check Universal Links work from App Store install (not TestFlight)
- [ ] Verify Apple Sign-In and Google Sign-In work on the production build

### First Week

- [ ] Monitor App Store Connect → Crashes for crash reports
- [ ] Check Sentry for new error patterns from App Store users
- [ ] Monitor App Store Connect → App Analytics for downloads and retention
- [ ] Add `SKStoreReviewController.requestReview()` after 5+ sessions (prompt users to rate)

### Ongoing

- [ ] Respond to App Store reviews (builds trust, improves ranking)
- [ ] Update screenshots when major UI changes ship
- [ ] Consider App Store Optimization (ASO): A/B test screenshots, refine keywords based on search data
- [ ] Plan a v1.1 with whatever Apple flagged or users request

---

## Reference: Current Technical Configuration

| Setting | Value |
|---------|-------|
| Bundle ID | `com.bainluck.Bain-Luck` |
| Team ID | `J893F72P4R` |
| Marketing Version | `1.0` |
| Current Build | `3` (TestFlight) |
| iOS Deployment Target | 17.0 |
| macOS Deployment Target | 26.2 |
| Supported Platforms | iPhone, iPad, Mac, (visionOS) |
| Code Signing | Automatic |
| SPM Dependencies | Firebase 11.15.0, GoogleSignIn 8.0.0 |
| Privacy Manifest | PrivacyInfo.xcprivacy (UserDefaults reason CA92.1) |
| Export Compliance | `ITSAppUsesNonExemptEncryption = NO` |
| Associated Domains | `applinks:bainluck.com` |
| AASA File | Deployed at `bainluck.com/.well-known/apple-app-site-association` |
