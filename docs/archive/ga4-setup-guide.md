# GA4 Console Configuration Guide

All configuration is done in [analytics.google.com](https://analytics.google.com) for the Bain Luck property. No code changes needed — the events are already being sent from web and iOS.

## Step 1: Custom Dimensions

Go to **Admin → Property → Custom definitions → Create custom dimension**

| Dimension name | Event parameter | Scope |
|---|---|---|
| Sport | `sport` | Event |
| League | `league` | Event |
| Event ID | `event_id` | Event |
| Event Status | `event_status` | Event |
| Source Section | `source_section` | Event |
| Position Index | `position_index` | Event |
| Is Live | `is_live` | Event |
| Is Close Game | `is_close_game` | Event |
| Platform | `platform` | User |
| App Version | `app_version` | User |
| Days Since Install | `days_since_install` | User |

## Step 2: Key Events (Conversions)

Go to **Admin → Property → Key events** and mark these as key events:

- `sign_up`
- `onboarding_complete`
- `event_detail_view`
- `prediction_submit`
- `challenge_start` (daily challenge)

## Step 3: Audiences

Go to **Admin → Property → Audiences → New audience**

| Audience | Condition |
|---|---|
| Sports Enthusiasts | `event_detail_view` count ≥ 3 in last 7 days |
| NBA Fans | `sport` = "basketball_nba", session count ≥ 5 |
| Power Users | Sessions ≥ 5 in last 7 days |
| Prediction Players | `prediction_submit` count ≥ 3 in last 7 days |
| Discover Browsers | `page_view` where page = "/" or "/discover", count ≥ 5 in 7 days |

## Step 4: Explorations

Go to **Explore tab → Create new**

### Acquisition Funnel
1. `session_start`
2. `page_view`
3. `event_detail_view`
4. `prediction_submit`
5. `sign_up`

### Retention Cohort
- Cohort: first visit date
- Return criteria: any event
- Granularity: daily

## Step 5: Dashboard Reports

Go to **Reports → Library → Create new report**

Key metrics to surface:
- **DAU by platform** — web vs iOS vs macOS
- **Top sports by engagement time** — which sports drive the most time
- **Discover feed CTR** — card opens / impressions (from `discover_card_open` / `discover_impression`)
- **Onboarding completion rate** — `onboarding_complete` / `onboarding_start`
- **Prediction accuracy** — from `prediction_submit` events with `correct` parameter
- **Return visit rate** — `return_visit` events by `days_since_last`
