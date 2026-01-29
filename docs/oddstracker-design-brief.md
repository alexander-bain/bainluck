# OddsTracker Design Brief

## 1. Design Principles

**1. Clarity Over Chrome**
Every element earns its place. No decorative gradients, no unnecessary borders, no visual noise. If it doesn't help the user understand win probability faster, remove it.

**2. Confidence at a Glance**
The most important information—who's favored and by how much—should be comprehensible in under one second. Design for the peripheral glance, not the focused study.

**3. Time is Data**
Freshness of odds is as important as the odds themselves. Timestamps, update indicators, and staleness warnings are first-class citizens, not afterthoughts.

**4. Progressive Disclosure**
Show probability first. Reveal trend, then context, then history—only when requested. The casual fan sees clean numbers; the curious fan can drill deeper.

**5. Hierarchy Through Restraint**
Use whitespace and typography weight—not color or decoration—to establish importance. Popular games surface through placement, not visual loudness.

**6. Trustworthy Precision**
Display probabilities as whole percentages (not "59.7%"). Round confidently. Use language that conveys calculated intelligence, not gambling excitement.

**7. Platform Fluency**
On iOS, feel like an Apple app. On web, feel like a premium dashboard. Respect each platform's conventions while maintaining brand coherence.

---

## 2. Color System

### Core Palette

| Role | Name | Hex | Usage |
|------|------|-----|-------|
| Background | Snow | `#FAFAFA` | Primary app background |
| Surface | White | `#FFFFFF` | Cards, modals, input fields |
| Primary Text | Graphite | `#1A1A1A` | Headlines, probabilities, key data |
| Secondary Text | Slate | `#6B7280` | Timestamps, labels, supporting info |
| Tertiary Text | Silver | `#9CA3AF` | Disabled states, placeholders |
| Border | Mist | `#E5E7EB` | Subtle dividers, card edges |
| Accent | Ink | `#0F172A` | Interactive elements, selected states |

### Semantic Colors

| Role | Name | Hex | Usage |
|------|------|-----|-------|
| Favorite Indicator | Charcoal | `#374151` | Strong favorite (>65%) |
| Underdog Indicator | Fog | `#D1D5DB` | Underdog probability bar fill |
| Positive Trend | Forest | `#059669` | Probability increased |
| Negative Trend | Rust | `#DC2626` | Probability decreased |
| Live Indicator | Emerald | `#10B981` | Live game pulse dot |
| Stale Warning | Amber | `#F59E0B` | Data older than expected |

### Usage Guidelines

- **Never use color alone** to convey meaning—always pair with text or icons
- **Trend colors appear only in trend contexts**—not for team branding or decoration
- **Live indicator** uses subtle pulse animation, never harsh blinking
- **Dark mode** (future): invert Snow/White, adjust text colors for WCAG AA contrast

---

## 3. Typography Scale

### Font Families

| Use | Family | Fallback |
|-----|--------|----------|
| Primary | SF Pro Display (iOS) / Inter (Web) | -apple-system, system-ui, sans-serif |
| Monospace | SF Mono (iOS) / JetBrains Mono (Web) | monospace |

### Type Scale

| Name | Size | Weight | Line Height | Letter Spacing | Usage |
|------|------|--------|-------------|----------------|-------|
| Display | 48px | 700 | 1.1 | -0.02em | Hero probability on event detail |
| Title 1 | 28px | 600 | 1.2 | -0.01em | Screen titles |
| Title 2 | 22px | 600 | 1.25 | -0.01em | Section headers |
| Title 3 | 18px | 600 | 1.3 | 0 | Card titles, team names |
| Body | 16px | 400 | 1.5 | 0 | Descriptions, paragraphs |
| Body Strong | 16px | 600 | 1.5 | 0 | Inline emphasis |
| Caption | 14px | 400 | 1.4 | 0.01em | Timestamps, labels |
| Caption Strong | 14px | 600 | 1.4 | 0.01em | Small headers |
| Micro | 12px | 500 | 1.3 | 0.02em | Badges, status indicators |
| Probability | 32px | 700 | 1 | -0.02em | List view percentages (monospace) |

### Guidelines

- **Probabilities always use monospace** for tabular alignment
- **Never use italic** except for proper names that require it
- **Maximum two weights per screen** to maintain hierarchy clarity
- **Minimum touch target**: 44px on iOS, 48px on web

---

## 4. Spacing System

### Base Unit
4px base unit. All spacing derives from this.

### Scale

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight internal padding, icon gaps |
| `space-2` | 8px | Related element spacing |
| `space-3` | 12px | Standard internal padding |
| `space-4` | 16px | Card padding, list item gaps |
| `space-5` | 20px | Section gaps within cards |
| `space-6` | 24px | Between cards |
| `space-8` | 32px | Section dividers |
| `space-10` | 40px | Major section breaks |
| `space-12` | 48px | Screen edge padding (mobile) |
| `space-16` | 64px | Hero section spacing |

### Application

- **Card internal padding**: `space-4` (16px)
- **Between list items**: `space-3` (12px)
- **Screen horizontal margins**: `space-4` mobile, `space-8` tablet, `space-12` desktop
- **Between sections**: `space-8` (32px)

---

## 5. Component Inventory

### Navigation

| Component | Description |
|-----------|-------------|
| **Tab Bar** | iOS: standard SF Symbols. Web: horizontal text tabs. Two items: "Live" and "My Teams" |
| **Filter Pills** | Horizontally scrolling sport filters (NFL, NBA, MLB, NHL). Single-select. Unselected = ghost style, selected = filled |
| **Back Navigation** | iOS: standard chevron. Web: breadcrumb or back arrow |

### Data Display

| Component | Description |
|-----------|-------------|
| **Event Card** | Primary list item. Contains: two teams, two probabilities (as horizontal bar), start time or live indicator, sport badge |
| **Probability Bar** | Horizontal bar showing relative probability. Favorite side filled with Charcoal, underdog with Fog. Centered number labels |
| **Trend Indicator** | Small arrow (↑ or ↓) with percentage change. Appears next to probability when meaningful movement occurs |
| **Timestamp Badge** | "Updated 30s ago" or "Next update in 2m". Uses Caption style. Shows warning color if stale |
| **Live Pulse** | Small green dot with subtle pulse animation. Appears on live games |
| **Sport Badge** | Micro-sized pill showing sport abbreviation (NFL, NBA). Monochrome |

### Event Detail

| Component | Description |
|-----------|-------------|
| **Hero Probability** | Large Display-sized percentage for home team, with team name above. Away team mirrored |
| **Trend Chart** | Minimal line chart showing probability over time. No gridlines. Single line. Time axis only shows start and "now" |
| **Matchup Header** | Team logos (if available), names, scheduled time, venue |
| **Data Freshness Strip** | Full-width bar showing last update time and countdown to next update |

### Interactive

| Component | Description |
|-----------|-------------|
| **Favorite Toggle** | Star icon. Outlined when unfavorited, filled when favorited. Tap area extends beyond visible icon |
| **Refresh Control** | iOS: standard pull-to-refresh. Web: subtle refresh icon in header that spins during load |
| **Empty State** | Centered illustration-free message. "No games today" with suggestion to check another sport |
| **Loading Skeleton** | Animated placeholder matching Event Card dimensions. Subtle shimmer, not pulsing |

### Feedback

| Component | Description |
|-----------|-------------|
| **Toast** | Brief confirmation messages. Appears bottom-center on mobile, top-right on desktop. Auto-dismisses after 3s |
| **Error State** | Inline error messages below affected component. Red text, no icons. Actionable when possible |

---

## 6. Layout Patterns

### Grid System

**Mobile (< 640px)**
- Single column
- 16px horizontal margins
- Cards span full width minus margins

**Tablet (640px – 1024px)**
- Two-column grid for event list
- 24px gutters
- 32px horizontal margins

**Desktop (> 1024px)**
- Max content width: 1200px, centered
- Three-column grid for event list
- Left sidebar (240px) for filters on "All Events" view
- 24px gutters
- Event detail: two-column (60/40 split)

### Breakpoints

| Name | Min Width | Behavior |
|------|-----------|----------|
| Mobile | 0px | Single column, compact spacing |
| Tablet | 640px | Two columns, medium spacing |
| Desktop | 1024px | Three columns or sidebar layout |
| Wide | 1440px | Max-width container centered |

### Key Layout Templates

**1. Event List (Home)**
```
┌─────────────────────────────────────┐
│ [Filter Pills: NFL | NBA | MLB ...] │
├─────────────────────────────────────┤
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│ │ Event   │ │ Event   │ │ Event   │ │
│ │ Card    │ │ Card    │ │ Card    │ │
│ └─────────┘ └─────────┘ └─────────┘ │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│ │ Event   │ │ Event   │ │ Event   │ │
│ │ Card    │ │ Card    │ │ Card    │ │
│ └─────────┘ └─────────┘ └─────────┘ │
└─────────────────────────────────────┘
```

**2. Event Detail**
```
┌─────────────────────────────────────┐
│ ← Back to NFL                       │
├─────────────────────────────────────┤
│                                     │
│   PATRIOTS          BILLS          │
│      62%              38%           │
│   ████████████░░░░░░░░░░           │
│                                     │
│   Updated 45s ago · Next in 15s     │
├─────────────────────────────────────┤
│   [Trend Chart - 24h view]          │
│   ────────────────/─────            │
│   Start            Now              │
├─────────────────────────────────────┤
│   Sun, Jan 26 · 4:25 PM ET          │
│   Gillette Stadium                  │
└─────────────────────────────────────┘
```

---

## 7. Interaction Patterns

### Transitions

| Interaction | Duration | Easing | Notes |
|-------------|----------|--------|-------|
| Screen navigation | 300ms | ease-out | iOS: standard push. Web: fade + subtle slide |
| Card hover (web) | 150ms | ease-in-out | Subtle shadow lift, no scale |
| Probability bar update | 400ms | ease-out | Smooth width animation when odds change |
| Filter selection | 200ms | ease-out | Background fill transition |
| Toast appearance | 200ms | ease-out | Slide up + fade in |

### Hover States (Web)

- **Event Card**: Elevate shadow from `0 1px 3px` to `0 4px 12px`, shift background to pure white
- **Interactive text**: Underline appears, not color change
- **Buttons**: Background darkens 10%

### Touch Feedback (iOS)

- **Event Card**: Standard highlight state (slight dim)
- **Buttons**: Spring animation on press (scale to 0.97)
- **Pull to refresh**: Standard iOS rubber-band physics

### Real-Time Updates

- **Probability change**: Number animates (count up/down over 400ms), bar width transitions smoothly
- **New live game**: Card slides in from top of list with subtle fade
- **Game ends**: Card fades out after 2s delay, removed from live section

### Loading States

- **Initial load**: Skeleton cards (3 visible) with shimmer
- **Refresh**: Existing data stays visible, subtle spinner in header
- **Background update**: No visual indication—data simply updates

### Error Handling

- **Network failure**: Inline message below list: "Couldn't refresh. Showing data from [timestamp]. Tap to retry."
- **No games**: Empty state message, suggest checking another sport
- **Stale data (>2 min since expected update)**: Timestamp badge turns Amber

---

## 8. Sample Screen Specifications

### Screen 1: Event List (Home)

**Purpose**: Show all upcoming and live games with their current win probabilities.

**Header**
- Fixed position on scroll (web), standard behavior (iOS)
- Left: App wordmark "OddsTracker" in Title 2 weight
- Right: Settings gear icon (web) or profile avatar

**Filter Section**
- Horizontally scrollable pill row
- Pills: "All" (default selected), "NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAB"
- Selected pill: Ink background, white text
- Unselected pill: transparent background, Slate text, Mist border
- Sticky below header on scroll

**Live Games Section** (if any exist)
- Section header: "Live Now" in Caption Strong with Live Pulse dot
- Cards sorted by Game Excitement Index (closest games first)
- Each card shows live score beneath team names in Caption

**Upcoming Games Section**
- Section header: "Today" / "Tomorrow" / Date in Caption Strong
- Cards sorted by start time, then by GEI
- Cards grouped by day with subtle divider

**Event Card Specification**
```
┌────────────────────────────────────────────┐
│ [Sport Badge]            [Favorite Star]   │
│                                            │
│ Patriots                              62%  │
│ ███████████████████░░░░░░░░░░░░░         │
│ Bills                                 38%  │
│                                            │
│ Sun 4:25 PM                 [Trend: ↑ 3%]  │
└────────────────────────────────────────────┘
```

- Card background: White
- Card corner radius: 12px
- Card shadow: `0 1px 3px rgba(0,0,0,0.08)`
- Sport badge: top-left, Micro size, Mist background
- Favorite star: top-right, 20px, Slate when unfilled
- Team names: Title 3 weight, left-aligned
- Probability: Probability style, right-aligned, monospace
- Probability bar: 8px height, 4px radius, full card width minus padding
- Time: Caption, Slate color, bottom-left
- Trend: Caption, Forest or Rust, bottom-right (only if >2% change in 24h)

**Footer**
- iOS: Tab bar with "Events" and "My Teams"
- Web: None (filters and nav handle routing)

---

### Screen 2: Event Detail

**Purpose**: Deep dive into a single matchup showing current probability, historical trend, and game metadata.

**Navigation**
- Top-left: Back arrow + "Back to [Sport]" in Caption
- Top-right: Share icon, Favorite star

**Hero Section**
- Centered layout
- Home team above, away team below
- Each team block:
  - Team logo (48px, or placeholder initial if unavailable)
  - Team name in Title 3
  - Probability in Display size, monospace
  - Trend indicator (if applicable) below probability

**Probability Bar**
- Centered between team blocks
- 12px height, full width minus margins
- Animated on load and updates

**Freshness Strip**
- Full-width, Snow background
- Left: "Updated 45 seconds ago"
- Right: "Next update in 15 seconds"
- Caption size, Slate color
- If stale: Amber background tint, warning icon

**Trend Chart Section**
- Section header: "Last 24 Hours" with toggle for "7 Days"
- Chart area: 200px height
- Single line, Graphite color, 2px stroke
- No Y-axis labels (implied 0-100%)
- X-axis: Start time on left, "Now" on right, no intermediate labels
- Interaction: Tap/hover shows tooltip with exact probability and timestamp
- If no historical data: Message "Tracking will begin when odds are available"

**Game Info Section**
- Divider: 1px Mist, with `space-8` above and below
- Date and time: Body Strong
- Venue: Body, Slate
- Optional: Broadcast network in Caption

**Empty State (No Odds Yet)**
- Replace hero probabilities with "—"
- Message below bar: "Odds not yet available. Check back closer to game time."

---

### Screen 3: My Teams (Favorites)

**Purpose**: Filtered view showing only games involving the user's favorite teams.

**Header**
- Title: "My Teams" in Title 1
- Right: "Edit" text button to manage favorites

**Empty State** (no favorites set)
- Centered vertically
- Headline: "Follow Your Teams" in Title 2
- Subhead: "Star teams from the main list to see their games here" in Body, Slate
- CTA button: "Browse Events" (ghost style)

**Populated State**
- Same card layout as Event List
- Section groupings: "Live", "Today", "This Week"
- If a favorite team has no upcoming games: Show card with team logo and "No upcoming games" in Caption

**Edit Mode**
- List of current favorites with team logo, name, sport badge
- Swipe to delete (iOS) or X button (web)
- Reorder handle on left

---

## 9. Do's and Don'ts

### Do

- **Do** use whole number percentages (52%, not 51.7%)
- **Do** show both teams' probabilities—they should always sum to 100%
- **Do** keep the home team consistently positioned (top or left)
- **Do** show trend indicators only for meaningful changes (>2%)
- **Do** use relative timestamps ("45s ago") for recent, absolute for old ("Jan 24, 3:15 PM")
- **Do** gray out or remove completed games promptly
- **Do** show loading skeletons that match actual card dimensions
- **Do** ensure probability bar proportions are mathematically accurate
- **Do** test with extreme cases (99% vs 1%, overtime games)

### Don't

- **Don't** use gambling terminology ("odds", "moneyline", "spread", "vig")—say "win probability"
- **Don't** show decimal probabilities to users
- **Don't** use team colors in the interface—maintain neutral palette
- **Don't** animate numbers on initial load—only on updates
- **Don't** use pie charts or circular progress indicators
- **Don't** show historical data older than 7 days in the trend chart
- **Don't** auto-refresh faster than every 30 seconds on web
- **Don't** use notification badges—the live pulse is sufficient
- **Don't** add social features (comments, likes, shares beyond link)
- **Don't** show projected scores on the list view—only on detail
- **Don't** include soccer events

---

## 10. Reference Moodboard Description

Look at these references for specific design qualities:

1. **Strava Activity Feed**
   Why: Clean card-based layout, excellent information hierarchy, timestamp handling, achievement badges without being noisy

2. **Apple Health App**
   Why: Minimal charts that convey trend without overwhelming, consistent type scale, excellent use of whitespace, color used sparingly for meaning

3. **Wealthfront Dashboard**
   Why: Financial data presented cleanly, confidence-inspiring precision, excellent mobile/desktop parity, sophisticated but not complex

4. **Linear App**
   Why: Command of grayscale, typography-driven hierarchy, ultra-clean list views, subtle hover states

5. **Notion (Light Mode)**
   Why: Content-first design, generous whitespace, restrained UI chrome, excellent empty states

6. **Apple Sports App**
   Why: Direct competitor—study what works (live indicators, score prominence) and what's noisy (dense information, busy headers)

7. **Stripe Dashboard**
   Why: Data tables done right, timestamp formatting, subtle but effective status indicators, professional density

8. **Things 3 (iOS)**
   Why: Masterclass in iOS design language, subtle animations, perfect touch targets, delightful without being distracting

9. **Robinhood (Pre-2021 Design)**
   Why: Made financial data approachable, excellent mobile charts, progressive disclosure of complexity

10. **Gov.uk Website**
    Why: Radical clarity, zero decoration, typography-only hierarchy—proof that "boring" can be beautiful when serving users

---

## Implementation Notes

### CSS Custom Properties (Web)

```css
:root {
  /* Colors */
  --color-snow: #FAFAFA;
  --color-white: #FFFFFF;
  --color-graphite: #1A1A1A;
  --color-slate: #6B7280;
  --color-silver: #9CA3AF;
  --color-mist: #E5E7EB;
  --color-ink: #0F172A;
  --color-charcoal: #374151;
  --color-fog: #D1D5DB;
  --color-forest: #059669;
  --color-rust: #DC2626;
  --color-emerald: #10B981;
  --color-amber: #F59E0B;
  
  /* Typography */
  --font-sans: 'Inter', -apple-system, system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  
  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  
  /* Transitions */
  --transition-fast: 150ms ease-in-out;
  --transition-base: 200ms ease-out;
  --transition-slow: 300ms ease-out;
  --transition-probability: 400ms ease-out;
}
```

### Tailwind Config Extensions (if using)

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        snow: '#FAFAFA',
        graphite: '#1A1A1A',
        slate: '#6B7280',
        // ... etc
      },
      fontFamily: {
        sans: ['Inter', ...defaultTheme.fontFamily.sans],
        mono: ['JetBrains Mono', ...defaultTheme.fontFamily.mono],
      },
    },
  },
}
```

---

This brief should give any designer or developer enough context to create consistent, on-brand screens for OddsTracker. The emphasis throughout is on speed of comprehension, respect for the user's attention, and the quiet confidence that comes from showing exactly what matters—nothing more.
