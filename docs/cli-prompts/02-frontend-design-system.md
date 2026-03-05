# Prompt 2: Frontend Design System Foundation

**Terminal:** 2 of 2 (can run simultaneously with Prompt 1)
**Estimated time:** 2-3 hours
**Risk level:** Low (all additive, no existing code changes)
**Prerequisite:** Alex must run `npx shadcn-ui@latest init`, `npm install framer-motion`, and `npx shadcn-ui@latest add card badge button tooltip` in frontend/ BEFORE starting this prompt.

---

## Copy this entire prompt into Claude Code CLI:

```
I need you to set up a design system foundation for the Bain Luck frontend. Read docs/architecture-improvement-plan.md first for full context. This is all ADDITIVE work — do NOT modify any existing components yet.

IMPORTANT: shadcn/ui and framer-motion should already be installed. Verify:
  ls frontend/components/ui/
  grep "framer-motion" frontend/package.json

If either is missing, stop and tell me — I need to install them manually first.

## Step 1: Create design tokens

Create frontend/app/design-tokens.css with CSS custom properties for the entire design system:

```css
@layer base {
  :root {
    /* ===== STATUS COLORS ===== */
    --color-status-live: 239 68 68;        /* Pulsing red for live games */
    --color-status-upcoming: 139 92 246;    /* Violet for upcoming */
    --color-status-completed: 107 114 128;  /* Gray for completed */
    --color-status-closed: 75 85 99;        /* Darker gray for closed */
    --color-status-starting-soon: 234 179 8; /* Amber for starting soon */

    /* ===== EI SEVERITY SCALE ===== */
    --color-ei-incredible: 239 68 68;       /* 90+ */
    --color-ei-must-watch: 249 115 22;      /* 80+ */
    --color-ei-exciting: 251 146 60;        /* 70+ */
    --color-ei-engaging: 234 179 8;         /* 60+ */
    --color-ei-competitive: 163 163 163;    /* 50+ */
    --color-ei-average: 115 115 115;        /* 40+ */
    --color-ei-quiet: 82 82 82;             /* 25+ */
    --color-ei-flat: 64 64 64;              /* <25 */

    /* ===== BRAND ===== */
    --color-brand-bg: 255 255 255;          /* White background */
    --color-brand-surface: 248 250 252;     /* Slightly off-white cards */
    --color-brand-text: 15 23 42;           /* Near-black text */
    --color-brand-text-secondary: 100 116 139; /* Muted text */
    --color-brand-accent: 59 130 246;       /* Primary action blue */
    --color-brand-border: 226 232 240;      /* Subtle borders */

    /* ===== DYNAMIC TEAM COLORS ===== */
    /* Set per-component via style={{ '--team-home': '#007A33' }} */
    --team-home: 107 114 128;              /* Default gray */
    --team-away: 107 114 128;              /* Default gray */

    /* ===== PREDICTION MARKET SOURCES ===== */
    --color-source-odds: 15 23 42;          /* Dark - betting consensus */
    --color-source-espn: 249 115 22;        /* Orange - ESPN model */
    --color-source-model: 139 92 246;       /* Purple - Bain Luck model */
    --color-source-kalshi: 34 197 94;       /* Green - Kalshi */
    --color-source-polymarket: 59 130 246;  /* Blue - Polymarket */
    --color-source-mlb: 13 148 136;         /* Teal - MLB model */

    /* ===== SPACING SCALE ===== */
    /* Use: gap-[--space-md], p-[--space-sm], etc. */
    --space-2xs: 0.125rem;   /* 2px */
    --space-xs: 0.25rem;     /* 4px */
    --space-sm: 0.5rem;      /* 8px */
    --space-md: 0.75rem;     /* 12px */
    --space-lg: 1rem;        /* 16px */
    --space-xl: 1.5rem;      /* 24px */
    --space-2xl: 2rem;       /* 32px */
    --space-3xl: 3rem;       /* 48px */

    /* ===== ANIMATION ===== */
    --duration-instant: 100ms;
    --duration-fast: 150ms;
    --duration-normal: 250ms;
    --duration-slow: 400ms;
    --duration-glacial: 800ms;
    --ease-out: cubic-bezier(0.25, 0.46, 0.45, 0.94);
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);

    /* ===== ELEVATION (SHADOWS) ===== */
    --shadow-xs: 0 1px 2px rgb(0 0 0 / 0.04);
    --shadow-sm: 0 1px 3px rgb(0 0 0 / 0.06), 0 1px 2px rgb(0 0 0 / 0.04);
    --shadow-md: 0 4px 6px rgb(0 0 0 / 0.05), 0 2px 4px rgb(0 0 0 / 0.04);
    --shadow-lg: 0 10px 15px rgb(0 0 0 / 0.06), 0 4px 6px rgb(0 0 0 / 0.04);
    --shadow-xl: 0 20px 25px rgb(0 0 0 / 0.08), 0 8px 10px rgb(0 0 0 / 0.04);
    --shadow-glow-live: 0 0 12px rgb(239 68 68 / 0.3);   /* Red glow for live */
    --shadow-glow-ei: 0 0 20px rgb(249 115 22 / 0.25);    /* Orange glow for high EI */

    /* ===== TYPOGRAPHY ===== */
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;

    /* ===== BORDER RADIUS ===== */
    --radius-sm: 0.375rem;   /* 6px - badges, small elements */
    --radius-md: 0.5rem;     /* 8px - cards */
    --radius-lg: 0.75rem;    /* 12px - modals, large cards */
    --radius-full: 9999px;   /* pills, avatars */
  }

  /* ===== DARK MODE ===== */
  .dark {
    --color-brand-bg: 9 9 11;              /* Near-black bg */
    --color-brand-surface: 24 24 27;       /* Dark card bg */
    --color-brand-text: 250 250 250;       /* Near-white text */
    --color-brand-text-secondary: 161 161 170; /* Muted text */
    --color-brand-border: 39 39 42;        /* Dark borders */

    --shadow-xs: 0 1px 2px rgb(0 0 0 / 0.2);
    --shadow-sm: 0 1px 3px rgb(0 0 0 / 0.3);
    --shadow-md: 0 4px 6px rgb(0 0 0 / 0.25);
    --shadow-lg: 0 10px 15px rgb(0 0 0 / 0.3);
  }
}
```

Import this file at the TOP of frontend/app/globals.css (before any other imports):
  @import './design-tokens.css';

## Step 2: Create team color theming utility

Create frontend/lib/teamColors.ts:

```typescript
import type { CSSProperties } from 'react';

/**
 * Generate CSS custom properties for team colors.
 * Apply to a container element's `style` prop.
 * Child components can use var(--team-home) and var(--team-away).
 *
 * @example
 * <div style={teamColorStyle('#007A33', '#BA3B1D')}>
 *   <ProbabilityBar /> {/* automatically uses team colors */}
 * </div>
 */
export function teamColorStyle(
  homeColor?: string | null,
  awayColor?: string | null,
): CSSProperties {
  const style: Record<string, string> = {};

  if (homeColor) {
    style['--team-home'] = homeColor;
    style['--team-home-rgb'] = hexToRgb(homeColor);
  }
  if (awayColor) {
    style['--team-away'] = awayColor;
    style['--team-away-rgb'] = hexToRgb(awayColor);
  }

  return style as CSSProperties;
}

/**
 * Convert hex color to space-separated RGB values for use with Tailwind's
 * rgb() opacity syntax: `bg-[rgb(var(--team-home-rgb)/0.1)]`
 */
function hexToRgb(hex: string): string {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `${r} ${g} ${b}`;
}

/**
 * Get a readable text color (white or black) for a given background hex.
 * Uses relative luminance formula.
 */
export function contrastTextColor(hexBg: string): 'white' | 'black' {
  const clean = hexBg.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  // Relative luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5 ? 'black' : 'white';
}

/**
 * Generate a subtle gradient between two team colors.
 * Useful for card backgrounds.
 */
export function teamGradient(
  homeColor: string,
  awayColor: string,
  opacity: number = 0.08,
): string {
  return `linear-gradient(135deg, ${homeColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')}, ${awayColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')})`;
}
```

## Step 3: Create Framer Motion animation presets

Create frontend/lib/animations.ts:

```typescript
import type { Variants, Transition } from 'framer-motion';

/**
 * Shared animation presets for consistent motion across components.
 */

// Card entrance — stagger children in a list
export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] },
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: { duration: 0.15 },
  },
};

export const listVariants: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.05 },
  },
};

// Probability number transition (when odds update)
export const numberTransition: Transition = {
  type: 'spring',
  stiffness: 300,
  damping: 30,
  mass: 0.8,
};

// EI breathing animation — speed varies with score
export function eiBreatheVariants(eiScore: number): Variants {
  // Higher EI = faster breathing
  const beatMs = Math.max(550, 2000 - eiScore * 14.5);
  const duration = beatMs / 1000;

  return {
    breathe: {
      scale: [1, 1.04, 1],
      opacity: [1, 0.85, 1],
      transition: {
        duration,
        repeat: Infinity,
        ease: 'easeInOut',
      },
    },
  };
}

// Live pulse — subtle glow animation for live badges
export const livePulseVariants: Variants = {
  pulse: {
    boxShadow: [
      '0 0 0px rgba(239, 68, 68, 0)',
      '0 0 8px rgba(239, 68, 68, 0.4)',
      '0 0 0px rgba(239, 68, 68, 0)',
    ],
    transition: {
      duration: 2,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
};

// Fade in for lazy-loaded content
export const fadeInVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.3 },
  },
};

// Scale up for interactive elements (hover/tap)
export const scaleOnTap = {
  whileHover: { scale: 1.02 },
  whileTap: { scale: 0.98 },
  transition: { type: 'spring', stiffness: 400, damping: 25 },
};
```

## Step 4: Create EI color utility

Create frontend/lib/eiColors.ts:

```typescript
/**
 * EI (Excitement Index) color and label mapping.
 * Single source of truth — used by EIBadge, feed cards, TV mode.
 */

export interface EITheme {
  label: string;
  color: string;           // Hex color for the score
  bgColor: string;         // Background tint
  glowColor: string;       // Glow effect color
  cssVar: string;           // CSS variable name from design-tokens
}

const EI_THRESHOLDS: Array<{ min: number; theme: EITheme }> = [
  { min: 90, theme: { label: 'Incredible', color: '#ef4444', bgColor: '#fef2f2', glowColor: 'rgba(239,68,68,0.3)', cssVar: '--color-ei-incredible' } },
  { min: 80, theme: { label: 'Must-Watch', color: '#f97316', bgColor: '#fff7ed', glowColor: 'rgba(249,115,22,0.25)', cssVar: '--color-ei-must-watch' } },
  { min: 70, theme: { label: 'Exciting', color: '#fb923c', bgColor: '#fff7ed', glowColor: 'rgba(251,146,60,0.2)', cssVar: '--color-ei-exciting' } },
  { min: 60, theme: { label: 'Engaging', color: '#eab308', bgColor: '#fefce8', glowColor: 'rgba(234,179,8,0.15)', cssVar: '--color-ei-engaging' } },
  { min: 50, theme: { label: 'Competitive', color: '#a3a3a3', bgColor: '#fafafa', glowColor: 'none', cssVar: '--color-ei-competitive' } },
  { min: 40, theme: { label: 'Average', color: '#737373', bgColor: '#fafafa', glowColor: 'none', cssVar: '--color-ei-average' } },
  { min: 25, theme: { label: 'Quiet', color: '#525252', bgColor: '#fafafa', glowColor: 'none', cssVar: '--color-ei-quiet' } },
  { min: 0,  theme: { label: 'Flat', color: '#404040', bgColor: '#fafafa', glowColor: 'none', cssVar: '--color-ei-flat' } },
];

export function getEITheme(score: number): EITheme {
  for (const { min, theme } of EI_THRESHOLDS) {
    if (score >= min) return theme;
  }
  return EI_THRESHOLDS[EI_THRESHOLDS.length - 1].theme;
}

export function getEILabel(score: number): string {
  return getEITheme(score).label;
}

export function getEIColor(score: number): string {
  return getEITheme(score).color;
}
```

## Step 5: Create a status color utility

Create frontend/lib/statusColors.ts:

```typescript
/**
 * Event status color mapping.
 * Single source of truth for live/upcoming/completed/closed colors.
 */

export type EventStatus = 'scheduled' | 'live' | 'completed' | 'closed';

interface StatusTheme {
  label: string;
  color: string;        // Primary color
  bgColor: string;      // Light background
  borderColor: string;  // For badges/outlines
  animate: boolean;     // Whether to show pulse animation
}

const STATUS_THEMES: Record<EventStatus, StatusTheme> = {
  live: {
    label: 'Live',
    color: '#ef4444',
    bgColor: '#fef2f2',
    borderColor: '#fecaca',
    animate: true,
  },
  scheduled: {
    label: 'Upcoming',
    color: '#8b5cf6',
    bgColor: '#f5f3ff',
    borderColor: '#ddd6fe',
    animate: false,
  },
  completed: {
    label: 'Final',
    color: '#6b7280',
    bgColor: '#f9fafb',
    borderColor: '#e5e7eb',
    animate: false,
  },
  closed: {
    label: 'Final',
    color: '#4b5563',
    bgColor: '#f9fafb',
    borderColor: '#d1d5db',
    animate: false,
  },
};

export function getStatusTheme(status: EventStatus): StatusTheme {
  return STATUS_THEMES[status] || STATUS_THEMES.closed;
}
```

## Step 6: Verify everything builds

Run:
  cd frontend && npm run build

If the build succeeds, run:
  cd frontend && npx jest

All frontend tests should still pass — we haven't changed any existing files (except adding one import line to globals.css).

Report the build result and test count.
Do NOT commit — I will review and commit manually.
```
