# v0.dev Prompt for Bain Luck Homepage Redesign

Copy everything below the line into v0.dev.

---

Design a dark-mode sports odds feed page for a product called "Bain Luck" that shows win probabilities instead of betting lines. The page is a mobile-first vertical feed of game cards and futures market cards. It should feel like a premium sports scoreboard app — think ESPN's dark mode crossed with the data density of Bloomberg Terminal and the polish of Linear.

## Tech Stack (MUST use)
- Next.js 14 App Router
- React with TypeScript
- Tailwind CSS
- Framer Motion for animations
- shadcn/ui components (already installed)
- Font: Inter for text, JetBrains Mono for numbers/probabilities

## Color System (use these exact values)
```
Background:      #0C0F14 (near-black)
Card surface:    #141820
Elevated:        #1C2028
Border:          #242830
Text primary:    #F8FAFC
Text secondary:  #94A3B8
Text muted:      #475569
Live accent:     #22C55E (green)
Brand:           #10B981 (emerald)
Futures accent:  #8B5CF6 (purple)
Warning:         #F59E0B (amber)
Danger:          #EF4444 (red)
```

## Page Layout

Full-width dark background (#0C0F14). Content area max-width 1200px centered. Top has a horizontally-scrollable row of filter chips (like "All", "NBA", "NFL", "MLB", "Soccer", "Politics", "Crypto"). Below that is a sectioned vertical feed.

### Section Headers
Sections are: "Live Now", "Just Happened", "Upcoming", "Top Markets". Each section has a subtle left-aligned header with a small icon, the section name, and a count badge. No heavy dividers — use generous spacing (32px between sections) to separate them.

## Card Type 1: Event Card (Game)

This is the most important component. It shows a two-team game with win probabilities.

### Layout — 3 states:

**STATE: Scheduled (upcoming game)**
```
┌─────────────────────────────────────────┐
│ 🏀 NBA                  Today 7:30 PM  │
│                                         │
│ [logo] Boston Celtics            62%    │
│ ████████████████████░░░░░░░░░           │ ← team-colored probability bar
│ [logo] Miami Heat                38%    │
│                                         │
│ Proj 108-102           ESPN · TNT       │
└─────────────────────────────────────────┘
```

**STATE: Live (in progress)**
```
┌─────────────────────────────────────────┐
│ ● LIVE  Upset brewing  ⚡ EI 78   NBA  │
│                                         │
│        78 - 72                          │ ← score in green monospace
│      CEL    MIA                         │
│                                         │
│ [logo] Boston Celtics            71%    │
│ ████████████████████░░░░░░░░░           │
│ [logo] Miami Heat                29%    │
│                                         │
│ Opened 62/38                    TNT     │
└─────────────────────────────────────────┘
```

The live card should have:
- A subtle left border in #22C55E (3px)
- A very faint green glow ring (ring-1 ring-green-500/20)
- The "● LIVE" badge pulses gently
- The EI badge has a background tint based on score: green for 70+, amber for 50-69, gray below

**STATE: Finished**
```
┌─────────────────────────────────────────┐
│ FINAL  Won as 35% underdog  ⚡ EI 84   │
│                                         │
│ [logo] Miami Heat         ✓   102       │ ← winner bold, loser muted
│ [logo] Boston Celtics          98       │
│ ████████████████░░░░░░░░░░░░░░          │ ← shows OPENING odds (pre-game expectation)
│                                         │
│ Pre-game: 38%/62%        Yesterday 7 PM │
└─────────────────────────────────────────┘
```

Finished cards should be slightly dimmed (opacity-80) but recover to full on hover.

### Design Details for ALL Event Cards:
- The probability numbers are the star — use JetBrains Mono, 20px for the favorite, 16px for the underdog
- The favorite's probability is #F8FAFC (bright white), the underdog is #94A3B8 (dimmer)
- Team-colored probability bar between the two teams: 5px tall, rounded-full ends, 1.5px gap between the two segments, favorite side is full opacity, underdog side is 40% opacity
- Team logos are 20x20px with a colored-initial fallback square if no logo
- Card background is #141820 with a 1px border of #242830
- On hover: background shifts to #1C2028, subtle scale(1.005), shadow increases
- Corner radius: 10px

## Card Type 2: Futures Card (Market)

Shows a prediction market (e.g. "NBA Championship Winner", "Will Bitcoin exceed $80,000?")

```
┌─────────────────────────────────────────┐
│ ┃ BASKETBALL  Championship  3 sources   │ ← top border accent in #8B5CF6
│                                         │
│ NBA Championship Winner 2025-26         │
│                                         │
│ ① Boston Celtics          22%  ↑ 1.3%  │
│ ██████████░░░░░░░░░░░░░░░░░░░           │
│ ② Oklahoma City Thunder   18%           │
│ ████████░░░░░░░░░░░░░░░░░░░░░           │
│ ③ Cleveland Cavaliers     12%  ↓ 0.5%  │
│ █████░░░░░░░░░░░░░░░░░░░░░░░░           │
│ ④ Denver Nuggets           9%           │
│ ⑤ Golden State Warriors    7%           │
│                                         │
│ Sportsbooks                   Updated 2h│
└─────────────────────────────────────────┘
```

### Design Details:
- Top border: 2px colored accent based on category (purple for sports, blue for politics, orange for crypto, yellow for entertainment, teal for economics)
- The #1 outcome has its name in white, its probability in bold white, and its mini progress bar in the category accent color at 70% opacity
- Other outcomes have names in #94A3B8, probabilities in #475569
- Movement arrows: green ↑ for positive, red ↓ for negative. Significant moves (>2%) pulse gently
- Mini progress bars: 4px tall, rounded, the leader's bar is the accent color, others are #475569 at 30%

## Micro-interactions & Animation
- Cards fade in with staggered animation (Framer Motion variants: parent uses staggerChildren: 0.05, children use opacity 0→1, y 8→0)
- Probability numbers animate between values using Framer Motion useSpring (stiffness: 80, damping: 20)
- The team-colored probability bar segments animate their width with a 500ms ease-out
- Live cards: the green pulse dot uses CSS `animate-pulse`
- EI badges on high-scoring games (>70) gently breathe: scale oscillates between 1 and 1.03

## Feed Card Variant (Compact)
The feed also has a more compact card variant used in the main ranked feed. Same data, tighter layout:

```
┌─────────────────────────────────────────┐
│ ● LIVE  NBA         78 - 72            │
│ [logo] Celtics      [logo] Heat        │
│ █████████████░░░░░ 71%    29%          │
│ Opened 62/38                           │
└─────────────────────────────────────────┘
```

This is a single-row team display (away vs home on one line) with the probability bar below, all more compact.

## Empty/Loading States
- Skeleton cards: pulse-animated rectangles matching the card layout shape. Use #1C2028 for skeleton blocks against #141820 card background.
- Error state: centered message with retry button in brand color.

## Overall Feel
- Information-dense but not cluttered — generous internal padding (16px), tight but readable spacing between elements
- Numbers are the hero — probabilities should be the first thing your eye goes to
- Team colors add life — the probability bar is the signature visual element, using each team's actual primary color
- Dark, premium, data-forward — not playful or sporty, more like a financial dashboard that happens to show sports
- The whole page should feel alive — subtle animations, pulsing live indicators, breathing EI badges — without being distracting
- Mobile-first: cards stack full-width on mobile, 2-column grid on tablet (640px+), 3-column on desktop (1024px+)

## What NOT to do
- No bright backgrounds or light mode
- No large hero images or splash graphics
- No betting terminology (no "odds", "lines", "spreads" — use "probability", "win chance")
- No gradients on cards (keep flat with subtle borders)
- No rounded-3xl or excessively rounded corners — keep it tight at 10px
- Don't make it look like a betting app — it should feel like an analytics dashboard

## Deliverable
Create the full page with:
1. The page layout with filter chips and sections
2. EventCard component (all 3 states: scheduled, live, finished)
3. FuturesCard component
4. CompactFeedCard variant
5. SkeletonCard loading state
6. Sample data to demonstrate all states

Use Tailwind classes, shadcn/ui Card where appropriate, and Framer Motion for animations. All in a single file.
