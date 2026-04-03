# Prompt 5: Design Component Migration

**Terminal:** Any (run AFTER Prompts 1 and 2 complete)
**Estimated time:** 3-4 hours
**Risk level:** Low (styling changes only, no behavioral changes)
**Depends on:** Prompt 2 (design tokens must exist)

---

## Copy this entire prompt into Claude Code CLI:

```
I need you to migrate existing frontend components to use the new design system. Read docs/architecture-improvement-plan.md for context. The design tokens (frontend/app/design-tokens.css), team color utility (frontend/lib/teamColors.ts), animation presets (frontend/lib/animations.ts), EI colors (frontend/lib/eiColors.ts), and status colors (frontend/lib/statusColors.ts) should already exist.

VERIFY before starting:
  ls frontend/lib/teamColors.ts frontend/lib/animations.ts frontend/lib/eiColors.ts frontend/lib/statusColors.ts frontend/app/design-tokens.css

If any are missing, stop and tell me.

CRITICAL RULES:
1. Do NOT change any component behavior — only styling
2. Do NOT change API calls, data flow, or state management
3. Keep all existing props and interfaces
4. Each component migration should be a testable unit — verify after each
5. If a component looks good already, skip it

## Step 1: Migrate EIBadge.tsx

Read frontend/components/EIBadge.tsx.

Replace any hardcoded EI color logic with imports from frontend/lib/eiColors.ts:
  import { getEITheme } from '@/lib/eiColors';

Replace any hardcoded animation with Framer Motion breathing:
  import { motion } from 'framer-motion';
  import { eiBreatheVariants } from '@/lib/animations';

The badge should:
- Use getEITheme(score) for all colors
- Use eiBreatheVariants(score) for the breathing animation (live events only)
- Use design token shadows (--shadow-glow-ei for high EI badges)

Build after: cd frontend && npm run build

## Step 2: Migrate EventCard.tsx

Read frontend/components/EventCard.tsx.

Add team color theming:
  import { teamColorStyle } from '@/lib/teamColors';

Wrap the card container with:
  <div style={teamColorStyle(homeTeam?.primaryColor, awayTeam?.primaryColor)}>

Replace any hardcoded status colors with:
  import { getStatusTheme } from '@/lib/statusColors';

The live badge should use Framer Motion:
  import { motion } from 'framer-motion';
  import { livePulseVariants, cardVariants } from '@/lib/animations';

Add card entrance animation:
  <motion.div variants={cardVariants} initial="hidden" animate="visible">

Use design token shadows:
  - Default card: var(--shadow-sm)
  - Live card: var(--shadow-glow-live)
  - Hovered: var(--shadow-md)

Build after: cd frontend && npm run build
Run tests: cd frontend && npx jest -- --testPathPattern=EventCard

## Step 3: Migrate ProbabilityBar component

Read whatever probability bar component exists (might be inline in EventCard or a separate component).

The probability bar should use CSS custom properties for team colors:
  background: linear-gradient(
    to right,
    var(--team-home) 0%,
    var(--team-home) {homeProb}%,
    var(--team-away) {homeProb}%,
    var(--team-away) 100%
  );

If no separate ProbabilityBar component exists, extract one from EventCard:
  frontend/components/ProbabilityBar.tsx

Props:
  interface ProbabilityBarProps {
    homeProbability: number;  // 0-1
    awayProbability: number;  // 0-1
    homeColor?: string;       // hex
    awayColor?: string;       // hex
    animated?: boolean;       // true for live games
    height?: 'sm' | 'md' | 'lg';
  }

If animated, use Framer Motion to transition the probability split smoothly when odds change.

Build after: cd frontend && npm run build

## Step 4: Migrate FuturesCard.tsx

Read frontend/components/FuturesCard.tsx.

Similar treatment as EventCard:
- Design token shadows
- Card entrance animation
- Status color utility for any badges

Build after: cd frontend && npm run build

## Step 5: Add card list animations to homepage

Read frontend/app/page.tsx (the homepage).

Where cards are rendered in a list/grid, add staggered entrance animation:

```tsx
import { motion } from 'framer-motion';
import { listVariants, cardVariants } from '@/lib/animations';

<motion.div
  variants={listVariants}
  initial="hidden"
  animate="visible"
  className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
>
  {events.map(event => (
    <motion.div key={event.id} variants={cardVariants}>
      <EventCard event={event} />
    </motion.div>
  ))}
</motion.div>
```

This gives a subtle staggered fade-in when cards load.

Build after: cd frontend && npm run build

## Final verification

Run full frontend build: cd frontend && npm run build
Run all frontend tests: cd frontend && npx jest

Report results.
Do NOT commit — I will review and commit manually.
```
