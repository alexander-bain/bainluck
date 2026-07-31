/**
 * Shared narrative content — the single source of truth for Bain Luck's public
 * story. Rendered by the public `/about` page and previewed inside `/admin/story`
 * so the two never drift (L2-143 Item 3: "one source of truth for the narrative
 * blocks — no copy drift between admin and public").
 *
 * Plain data module — NO "use client" — safe to import from server or client
 * components. Editorial spec: .claude/handoff/story_about_editorial.md.
 *
 * All case-study numbers are documented, real exhibits. The Alcaraz line chart
 * is a real, downsampled win-probability series pulled from Polymarket's CLOB
 * price history for the cited market (every plotted point is an actual observed
 * price — no interpolation, no fabrication; L2-145 Item 2, Alex's ruling). The
 * McIlroy bars are three documented point-in-time win-prob values (DataGolf +
 * Kalshi futures). Nothing here is schematic.
 *
 * Belt-and-suspenders (L2-146 Item 2): the Alcaraz series lives in a committed
 * JSON archive (`lib/data/alcaraz-ao-2026-series.json`) so the exhibit is
 * reproducible even if Polymarket ever prunes its CLOB history — the chart
 * reads the archived points, not an inline copy. The archive also carries the
 * full provenance (slug, market id, fetch recipe) so anyone can re-derive it.
 */

import alcarazSeries from "./data/alcaraz-ao-2026-series.json";

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
      /** 0–100 win-probability points across the event — a real, downsampled
       *  series (each point is an actual observed market price). */
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
      "Alcaraz won in five sets. So why did his odds run from 98% up two sets to 14% — the brink of elimination — before he won?",
    scoreSaid: "Final: Alcaraz d. Zverev 6-4, 7-6, 6-7, 6-7, 7-5.",
    moment:
      "A pre-match favorite around 84%, Alcaraz went up two sets and the market pushed him to 98%. Then an adductor injury — and across the next two sets it watched him crash to 14%, the edge of elimination, before he broke back in the fifth to win. The market tracked every swing.",
    takeaway:
      "The scoreline says close. The probability line says he won, nearly lost, and won again. That's the night we show you.",
    // Alex ruling 2026-07-30: no dollar-volume social proof anywhere in the
    // product. Trading volume frames this as a betting venue; the exhibit is
    // about what the probability line knew. The word "odds" is fine — it is
    // PRICE formats (-140 / +3000) and dollar framing that are out.
    source: "Polymarket · atp-alcaraz-zverev-2026-01-30 · real price series",
    chart: {
      type: "line",
      // Read from the committed archive so the exhibit survives Poly pruning
      // (L2-146 Item 2). The archive IS the source of truth for these numbers.
      caption: alcarazSeries.caption,
      points: alcarazSeries.points,
      annotationIndex: alcarazSeries.annotation_index,
      annotationLabel: alcarazSeries.annotation_label,
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
