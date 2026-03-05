# Prompt A: Visual Design Overhaul

## Context

You are working on a Next.js 14 sports odds visualization app called Bain Luck. Read `CLAUDE.md` for full context.

The app has a design system foundation that was recently installed but NOT applied to any visible components:
- **shadcn/ui** is initialized (`components.json`, `frontend/components/ui/card.tsx`, `badge.tsx`, `button.tsx`, `tooltip.tsx`) — but NONE of these are imported or used by any existing component
- **Framer Motion** is installed with presets in `frontend/lib/animations.ts` — only 3 presets are used (staggerContainer, staggerItem, eiBreathingTransition)
- **CSS variables** exist in `frontend/app/globals.css` (surfaces, text, accents, spacing) — but many components still use hardcoded colors
- **Tailwind config** (`frontend/tailwind.config.ts`) has semantic tokens (text-prob-hero, shadow-card, etc.) — partially used

Your job is to **make the site visually better** by migrating the 4 highest-impact components to use the design system. This is NOT a rewrite — preserve all existing behavior, data flow, props, and analytics. Only change styling and add animations.

## What "Better" Means

Bain Luck is a dark-mode-only scoreboard app. The design language should feel like:
- **ESPN GameCast** meets **Bloomberg Terminal** — data-dense but readable
- Team colors are the ONLY splash of color against a dark void
- Numbers should feel alive (transitions, not jumps)
- Cards should have subtle depth (shadows, borders, hover states)
- Live games should feel urgent; finished games should feel settled

## Step 1: Migrate EventCard.tsx

Read `frontend/components/EventCard.tsx` carefully. Then apply these changes:

### 1a. Wrap the outer container with shadcn Card
Replace the outer `<Link>` wrapper's div with shadcn's Card component:
```tsx
import { Card, CardContent } from '@/components/ui/card';
```
The Card provides consistent border-radius, border color, and padding. Keep the `<Link>` as the outermost element.

### 1b. Add Framer Motion entrance animation
```tsx
import { motion } from 'framer-motion';
import { fadeIn, transitionNormal } from '@/lib/animations';

// Wrap Card with motion
<motion.div variants={fadeIn} initial="initial" animate="animate" transition={transitionNormal}>
  <Card className="...">
```

### 1c. Animate probability numbers
When probability changes between renders, the number should count up/down smoothly instead of jumping. Add this inline component at the top of EventCard.tsx:

```tsx
'use client';
import { useEffect, useRef, useState } from 'react';
import { motion, useSpring, useTransform } from 'framer-motion';

function AnimatedProbability({ value, className }: { value: number; className?: string }) {
  const spring = useSpring(value, { stiffness: 100, damping: 30 });
  const display = useTransform(spring, (v) => `${Math.round(v)}%`);

  useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span className={className}>{display}</motion.span>;
}
```

Replace hardcoded `{Math.round(prob * 100)}%` displays with `<AnimatedProbability value={Math.round(prob * 100)} className="..." />` — but ONLY for the main probability numbers (home/away), not the opening odds footer.

### 1d. Improve the probability bar
The current probability bar is a plain div. Enhance it:
- Add a 1px gap between the two segments (creates visual separation)
- Add a subtle inner glow using the team's primary color: `box-shadow: inset 0 0 8px rgba(var(--team-home-primary), 0.3)`
- Animate width changes with CSS transition: `transition: width 400ms cubic-bezier(0.4, 0, 0.2, 1)`
- Round the bar ends: `border-radius: 4px` on the container, with `overflow: hidden`

### 1e. Add hover state
On hover, the card should:
- Elevate slightly: `shadow-card-hover` (already defined in Tailwind config)
- Scale very slightly: `transform: scale(1.005)` with `transition: transform 200ms`
- Border brightens: `border-surface-border` → `border-surface-elevated`

### 1f. Live game urgency
For live events, add a subtle left-border accent:
```tsx
{event.status === 'live' && (
  <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-accent-live rounded-l" />
)}
```

### 1g. Finished game settled feel
For completed/closed events, reduce card opacity slightly and remove hover elevation:
```tsx
className={cn(
  "relative overflow-hidden transition-all duration-200",
  event.status === 'completed' || event.status === 'closed'
    ? 'opacity-85 hover:opacity-95'
    : 'hover:shadow-card-hover hover:scale-[1.005]'
)}
```

**Test:** The homepage should show cards that fade in on load, have team-colored probability bars with smooth width transitions, and feel different for live vs. finished games.

## Step 2: Migrate FuturesCard.tsx

Read `frontend/components/FuturesCard.tsx`. Apply similar treatment:

### 2a. shadcn Card wrapper
Same as EventCard — wrap with `<Card>`.

### 2b. Framer Motion entrance
Same fadeIn + transitionNormal.

### 2c. Outcome row micro-animations
Each outcome row in the top-5 list should stagger in:
```tsx
import { staggerContainer, staggerItem } from '@/lib/animations';

<motion.div variants={staggerContainer} initial="initial" animate="animate">
  {outcomes.map((outcome, i) => (
    <motion.div key={outcome.id} variants={staggerItem}>
      {/* existing OutcomeRow content */}
    </motion.div>
  ))}
</motion.div>
```

### 2d. Movement indicator enhancement
The current movement indicators (up/down arrows) are static. Make positive movements pulse briefly on first render:
```tsx
<motion.span
  initial={{ scale: 1.3, opacity: 0.7 }}
  animate={{ scale: 1, opacity: 1 }}
  transition={{ duration: 0.4 }}
  className={movementColor}
>
  {arrow} {formattedChange}
</motion.span>
```

### 2e. Hover + category accent
Add a subtle top-border color based on category:
- Sports futures: `border-t-accent-futures` (purple)
- Politics: `border-t-blue-500`
- Entertainment: `border-t-yellow-500`
- Crypto: `border-t-orange-500`
- Default: `border-t-surface-elevated`

```tsx
const categoryAccent = {
  politics: 'border-t-blue-500',
  entertainment: 'border-t-yellow-500',
  crypto: 'border-t-orange-500',
}[market.llm_sport_category] ?? 'border-t-accent-futures';
```

## Step 3: Migrate EIBadge.tsx

Read `frontend/components/EIBadge.tsx`. It already uses `eiBreathingTransition`. Enhance:

### 3a. Color scale based on EI score
The badge should visually communicate the score through color, not just the number. Add to `frontend/lib/eiColors.ts` (create if missing):

```tsx
export const EI_THRESHOLDS = [
  { min: 90, label: 'Incredible', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)', ring: 'ring-red-500/30' },
  { min: 80, label: 'Must-Watch', color: '#f97316', bg: 'rgba(249, 115, 22, 0.15)', ring: 'ring-orange-500/30' },
  { min: 70, label: 'Exciting', color: '#eab308', bg: 'rgba(234, 179, 8, 0.15)', ring: 'ring-yellow-500/30' },
  { min: 60, label: 'Engaging', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.12)', ring: 'ring-green-500/30' },
  { min: 50, label: 'Competitive', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.12)', ring: 'ring-blue-500/30' },
  { min: 40, label: 'Average', color: '#6b7280', bg: 'rgba(107, 114, 128, 0.12)', ring: 'ring-gray-500/20' },
  { min: 25, label: 'Quiet', color: '#4b5563', bg: 'rgba(75, 85, 99, 0.10)', ring: 'ring-gray-600/20' },
  { min: 0, label: 'Flat', color: '#374151', bg: 'rgba(55, 65, 81, 0.08)', ring: 'ring-gray-700/15' },
] as const;

export function getEITheme(score: number) {
  return EI_THRESHOLDS.find(t => score >= t.min) ?? EI_THRESHOLDS[EI_THRESHOLDS.length - 1];
}
```

### 3b. Apply theme in EIBadge
Replace the current static color classes with dynamic theming:
```tsx
const theme = getEITheme(ei.score);
// Use theme.color for text, theme.bg for background, theme.ring for glow ring
```

### 3c. Ring glow for high-EI live games
For live games with EI ≥ 70, add a pulsing ring:
```tsx
{isLive && ei.score >= 70 && (
  <motion.div
    className={`absolute inset-0 rounded-full ring-2 ${theme.ring}`}
    animate={{ opacity: [0.5, 1, 0.5] }}
    transition={{ duration: 2, repeat: Infinity }}
  />
)}
```

## Step 4: Extract and enhance ProbabilityBar

The probability bar is currently inline in EventCard. Extract it into its own component for reuse:

Create `frontend/components/ProbabilityBar.tsx`:

```tsx
'use client';

import { motion } from 'framer-motion';

interface ProbabilityBarProps {
  homeProbability: number;
  homeColor: string;    // CSS rgb value like "59, 130, 246"
  awayColor: string;
  height?: number;
  animated?: boolean;
  className?: string;
}

export function ProbabilityBar({
  homeProbability,
  homeColor,
  awayColor,
  height = 6,
  animated = true,
  className = '',
}: ProbabilityBarProps) {
  const homeWidth = Math.max(2, Math.min(98, homeProbability * 100));
  const awayWidth = 100 - homeWidth;

  return (
    <div
      className={`flex rounded-full overflow-hidden ${className}`}
      style={{ height, gap: '1.5px' }}
    >
      <motion.div
        className="rounded-l-full"
        style={{
          backgroundColor: `rgb(${homeColor})`,
          boxShadow: `inset 0 0 8px rgba(${homeColor}, 0.4)`,
        }}
        initial={animated ? { width: '50%' } : false}
        animate={{ width: `${homeWidth}%` }}
        transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }}
      />
      <motion.div
        className="rounded-r-full"
        style={{
          backgroundColor: `rgb(${awayColor})`,
          boxShadow: `inset 0 0 8px rgba(${awayColor}, 0.4)`,
        }}
        initial={animated ? { width: '50%' } : false}
        animate={{ width: `${awayWidth}%` }}
        transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }}
      />
    </div>
  );
}
```

Then replace the inline probability bar in EventCard with `<ProbabilityBar>`. Also use it in the event detail page.

## Step 5: Homepage feed stagger polish

Read `frontend/app/page.tsx`. The stagger animation is already there but needs refinement:

### 5a. Section headers should fade in before their cards
```tsx
<motion.h2
  initial={{ opacity: 0, y: -8 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3 }}
  className="..."
>
  {sectionTitle}
</motion.h2>
```

### 5b. Cards should stagger with slight upward motion
Update the staggerItem variant usage so cards slide up as they fade:
```tsx
// In the grid wrapper for each section
<motion.div
  variants={staggerContainer}
  initial="initial"
  animate="animate"
  className="grid ..."
>
  {items.map((item, i) => (
    <motion.div
      key={item.id}
      variants={{
        initial: { opacity: 0, y: 12 },
        animate: { opacity: 1, y: 0, transition: { duration: 0.3, delay: i * 0.05 } },
      }}
    >
      {/* EventCard or FuturesCard */}
    </motion.div>
  ))}
</motion.div>
```

Cap the stagger delay at 10 items (`delay: Math.min(i, 10) * 0.05`) so the page doesn't feel slow for large feeds.

### 5c. Section dividers
Add subtle dividers between feed sections:
```tsx
<div className="border-t border-surface-border/50 my-6" />
```

## Verification

After all changes, check:
1. `cd frontend && npx next build` — must build with zero errors
2. Open the homepage — cards should fade in with stagger, probability bars should animate
3. Find a live game — it should have a green left accent and the EI badge should pulse with color
4. Find a finished game — it should look settled (slightly dimmed, no hover lift)
5. Open a futures card — outcomes should stagger in, movement indicators should pulse on load
6. Resize to mobile — everything should still look correct

**Do NOT commit. Leave all changes unstaged so I can review the diff.**
