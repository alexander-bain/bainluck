/**
 * Shared narrative content — the single source of truth for Bain Luck's public
 * story. Rendered by the public `/about` page and previewed inside `/admin/story`
 * so the two never drift (L2-143 Item 3: "one source of truth for the narrative
 * blocks — no copy drift between admin and public").
 *
 * Plain data module — NO "use client" — safe to import from server or client
 * components. Editorial spec: .claude/handoff/story_about_editorial.md.
 *
 * All case-study numbers are documented, real exhibits (Kalshi ticker + DataGolf
 * sources cited). The chart point arrays are schematic illustrations of the
 * documented arc (underdog → dominant → desperate → champion; tied-but-3x-apart)
 * — the exact live series live at the cited sources.
 */

/* ── 1. THE ONE-LINER ── */
export const STORY_ONE_LINER =
  "Every game, election, and premiere has a number — the world's honest guess at what happens next. We find it, blend it, and show it clean.";

/* ── 2. THE ANTI-THESIS ── */
export const STORY_ANTI_THESIS = {
  heading: "The same knowledge as a betting app. None of the pull.",
  lines: [
    "You see exactly what the sharpest markets know — who's likely to win, what's likely to happen, how the odds are moving right now.",
    "But there's zero enticement. No odds formats, ever. Nothing to deposit, nothing to buy. Just the probability, clean.",
  ],
};

/* ── 3. THE BLEND (+ public calibration proof) ── */
export const STORY_BLEND = {
  heading: "Six sources. One number.",
  body:
    "Sportsbooks, ESPN, Kalshi, Polymarket, and live stat models each have a guess. We weight them by track record and blend them into a single probability — the whole market's honest opinion, not one book's.",
  // Proof line is written to survive without live stats; the page fills in the
  // exact figure when the calibration API responds.
  proofLead: "And we grade ourselves in public:",
  proofBody:
    "across nearly a million resolved outcomes, our numbers land within about two points of what actually happened.",
  proofCta: "Check our calibration",
};

/* ── 4. THE STORY THESIS ── */
export const STORY_THESIS = {
  heading: "The score doesn't tell the full story.",
  body:
    "A final score is one fact. The probability line is the whole night — every swing, every scare, every moment the outcome hung in the balance. Two nights the number saw more than the box score:",
};

/* ── 5. WHO BUILDS IT ── */
export const STORY_HUMAN_LINE =
  "Built end to end by one person who thinks a clean probability is more honest — and more fun — than a betting slip.";

/* ── Case studies (the punch template) ── */
export type CaseStudyChart =
  | {
      type: "line";
      caption: string;
      /** 0–100 win-probability points across the event, schematic of the documented arc. */
      points: number[];
      /** Index of the ONE annotated moment. */
      annotationIndex: number;
      annotationLabel: string;
    }
  | {
      type: "bars";
      caption: string;
      bars: { label: string; value: number; highlight?: boolean }[];
      annotationLabel: string;
    };

export interface CaseStudy {
  id: string;
  kicker: string; // sport · event
  /** Beat 0 — the paradox, one sentence, numbers in it. */
  headline: string;
  /** Beat 1 — what the score said (one line). */
  scoreSaid: string;
  /** Beat 2 — what the number knew (the annotated moment, prose). */
  moment: string;
  /** Beat 3 — the takeaway, ≤2 lines. */
  takeaway: string;
  source: string;
  chart: CaseStudyChart;
}

export const CASE_STUDIES: CaseStudy[] = [
  {
    id: "alcaraz-ao-2026",
    kicker: "Tennis · 2026 Australian Open semifinal",
    headline:
      "Alcaraz won in five sets. So why did his odds run from 20% to 85% to the brink — and back?",
    scoreSaid: "Final: Alcaraz d. Zverev 6-4, 7-6, 6-7, 6-7, 7-5.",
    moment:
      "Up two sets, Alcaraz hit 85%. Then an adductor injury — and across the next two sets the market watched him slide to the edge of elimination before he broke back in the fifth to win. $27M changed hands on Kalshi tracking every swing.",
    takeaway:
      "The scoreline says close. The probability line says he won, nearly lost, and won again. That's the night we show you.",
    source: "Kalshi · kxatpmatch-26jan29alczve · $27M volume",
    chart: {
      type: "line",
      caption: "Alcaraz win probability through the match",
      points: [20, 52, 76, 85, 60, 33, 15, 24, 49, 73, 100],
      annotationIndex: 3,
      annotationLabel: "Up 2 sets — 85%, then the injury",
    },
  },
  {
    id: "mcilroy-masters-2025",
    kicker: "Golf · 2025 Masters, after Round 1",
    headline:
      "Two players were tied for the lead. Why did the market give one 24% and the other 9%?",
    scoreSaid: "End of Round 1: McIlroy and Burns both T1. Scheffler sat T6, a shot back.",
    moment:
      "The market gave McIlroy 24.4% and co-leader Burns just 8.6% — while Scheffler, below them on the board, drew 19.0%. A spot on the leaderboard isn't the same as the odds of winning.",
    takeaway:
      "McIlroy won. The board showed who was ahead; the number showed who was actually most likely to close.",
    source: "DataGolf win-probability model + Kalshi futures",
    chart: {
      type: "bars",
      caption: "Win probability, end of Round 1",
      bars: [
        { label: "McIlroy (T1)", value: 24.4, highlight: true },
        { label: "Scheffler (T6)", value: 19.0 },
        { label: "Burns (T1)", value: 8.6 },
      ],
      annotationLabel: "Tied on the board — nearly 3× apart in the market",
    },
  },
];
