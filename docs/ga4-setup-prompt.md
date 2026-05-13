# GA4 Setup — Claude Desktop Prompt

Copy and paste this into the Claude desktop app. It will use computer use to navigate Chrome and configure GA4.

---

## Prompt

I need you to configure Google Analytics 4 for my Bain Luck app. Please use my Chrome browser to do this. Go to analytics.google.com — I should already be signed in. Find the Bain Luck property.

Work through ALL of the following steps. After each step, verify it was saved before moving to the next. If something fails, retry it. Don't stop until all steps are complete.

### Step 1: Custom Dimensions (11 total)

Go to Admin → Property → Custom definitions → Create custom dimension. Create each of these:

1. Name: "Sport", Parameter: "sport", Scope: Event
2. Name: "League", Parameter: "league", Scope: Event
3. Name: "Event ID", Parameter: "event_id", Scope: Event
4. Name: "Event Status", Parameter: "event_status", Scope: Event
5. Name: "Source Section", Parameter: "source_section", Scope: Event
6. Name: "Position Index", Parameter: "position_index", Scope: Event
7. Name: "Is Live", Parameter: "is_live", Scope: Event
8. Name: "Is Close Game", Parameter: "is_close_game", Scope: Event
9. Name: "Platform", Parameter: "platform", Scope: User
10. Name: "App Version", Parameter: "app_version", Scope: User
11. Name: "Days Since Install", Parameter: "days_since_install", Scope: User

### Step 2: Key Events (5 total)

Go to Admin → Property → Key events. Mark each of these existing events as key events (toggle them on):

1. sign_up
2. onboarding_complete
3. event_detail_view
4. prediction_submit
5. challenge_start

If any of these events don't appear in the list yet (they may not have been triggered), skip them and note which ones were missing.

### Step 3: Audiences (5 total)

Go to Admin → Property → Audiences → New audience → Create a custom audience. Create each:

1. Name: "Sports Enthusiasts"
   - Condition: event_detail_view count >= 3 in last 7 days

2. Name: "NBA Fans"  
   - Condition: sport parameter = "basketball_nba" AND session count >= 5

3. Name: "Power Users"
   - Condition: Sessions >= 5 in last 7 days

4. Name: "Prediction Players"
   - Condition: prediction_submit count >= 3 in last 7 days

5. Name: "Discover Browsers"
   - Condition: page_view where page_location contains "/" or "/discover", count >= 5 in 7 days

### Step 4: Funnel Exploration

Go to Explore tab → Create new exploration → Funnel exploration.

Name it "Acquisition Funnel" with these steps:
1. session_start
2. page_view  
3. event_detail_view
4. prediction_submit
5. sign_up

Save it.

### Step 5: Summary

When you're done with all steps, tell me:
- How many custom dimensions were created
- How many key events were marked
- How many audiences were created
- Whether the funnel was saved
- Any steps that failed or events that weren't found
