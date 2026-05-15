"use client";

import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { Button } from "@/components/ui/button";

/* ── Hardcoded data for the two stories ── */

const ALCARAZ_POINTS = [
  { x: 0, y: 55, label: "Match start" },
  { x: 8, y: 68 },
  { x: 16, y: 78 },
  { x: 22, y: 88, label: "Set 1 to Alcaraz" },
  { x: 30, y: 92 },
  { x: 38, y: 96, label: "Up 2 sets" },
  { x: 44, y: 88 },
  { x: 50, y: 72 },
  { x: 55, y: 52 },
  { x: 60, y: 34, label: "Injury sets in" },
  { x: 66, y: 20 },
  { x: 70, y: 13, label: "13% — Zverev serving for match" },
  { x: 74, y: 22 },
  { x: 78, y: 38, label: "Break back" },
  { x: 84, y: 55 },
  { x: 90, y: 72 },
  { x: 96, y: 88 },
  { x: 100, y: 100, label: "Alcaraz wins" },
];

const MASTERS_ROWS = [
  { pos: "T1", player: "Sam Burns", score: "-3", prob: "8.6%", highlight: false },
  { pos: "T1", player: "Collin Morikawa", score: "-3", prob: "5.2%", highlight: false },
  { pos: "T3", player: "Justin Thomas", score: "-2", prob: "3.8%", highlight: false },
  { pos: "T3", player: "Rory McIlroy", score: "-2", prob: "24.4%", highlight: true },
  { pos: "T6", player: "Scottie Scheffler", score: "-2", prob: "19.0%", highlight: true },
];

/* ── SVG Probability Chart ── */

function ProbabilityArc() {
  const W = 400;
  const H = 200;
  const PAD_L = 0;
  const PAD_R = 0;
  const PAD_T = 16;
  const PAD_B = 4;
  const chartW = W - PAD_L - PAD_R;
  const chartH = H - PAD_T - PAD_B;

  const toX = (pct: number) => PAD_L + (pct / 100) * chartW;
  const toY = (pct: number) => PAD_T + chartH - (pct / 100) * chartH;

  const pathD = ALCARAZ_POINTS.map((p, i) => {
    const x = toX(p.x);
    const y = toY(p.y);
    if (i === 0) return `M ${x} ${y}`;
    const prev = ALCARAZ_POINTS[i - 1];
    const cpx1 = toX(prev.x) + (toX(p.x) - toX(prev.x)) * 0.4;
    const cpx2 = toX(prev.x) + (toX(p.x) - toX(prev.x)) * 0.6;
    return `C ${cpx1} ${toY(prev.y)}, ${cpx2} ${y}, ${x} ${y}`;
  }).join(" ");

  // Gradient fill below the line
  const fillD = `${pathD} L ${toX(100)} ${toY(0)} L ${toX(0)} ${toY(0)} Z`;

  // Key moments to annotate (subset)
  const annotations = [
    { x: 38, y: 96, text: "96%", anchor: "middle" as const, dy: -8 },
    { x: 70, y: 13, text: "13%", anchor: "middle" as const, dy: 16 },
    { x: 100, y: 100, text: "Win", anchor: "end" as const, dy: -8 },
  ];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" aria-label="Alcaraz win probability over the match">
      <defs>
        <linearGradient id="prob-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent-brand)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--accent-brand)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* 50% reference line */}
      <line
        x1={toX(0)} y1={toY(50)} x2={toX(100)} y2={toY(50)}
        stroke="var(--surface-border)" strokeWidth="1" strokeDasharray="4 4"
      />
      <text x={toX(0) + 2} y={toY(50) - 4} fill="var(--text-muted)" fontSize="10">50%</text>
      {/* Fill */}
      <path d={fillD} fill="url(#prob-gradient)" />
      {/* Line */}
      <path d={pathD} fill="none" stroke="var(--accent-brand)" strokeWidth="2.5" strokeLinecap="round" />
      {/* Key dots + labels */}
      {annotations.map((a) => (
        <g key={a.text}>
          <circle cx={toX(a.x)} cy={toY(a.y)} r="4" fill="var(--accent-brand)" />
          <text
            x={toX(a.x)}
            y={toY(a.y) + a.dy}
            textAnchor={a.anchor}
            fill="var(--text-primary)"
            fontSize="12"
            fontWeight="700"
            fontFamily="var(--font-mono)"
          >
            {a.text}
          </text>
        </g>
      ))}
    </svg>
  );
}

/* ── Page ── */

export default function AboutPage() {
  usePageTracking({ pageType: "about", pageTitle: "About — Score Doesn't Tell the Full Story" });
  useScrollDepth({ pageType: "about" });
  useEngagementTime({ pageType: "about" });

  return (
    <div className="max-w-2xl mx-auto pb-16">
      {/* ── Hero ── */}
      <section className="text-center pt-4 pb-12 space-y-5">
        <h1 className="text-4xl sm:text-5xl font-bold text-text-primary tracking-tight leading-tight">
          The score doesn&apos;t tell<br />the full story
        </h1>
        <p className="text-lg text-text-secondary max-w-xl mx-auto leading-relaxed">
          Bain Luck translates betting and prediction markets into simple
          probabilities &mdash; so you see the real story behind every event,
          from sports to politics to economics.
        </p>
      </section>

      {/* ── Story 1: Alcaraz vs Zverev ── */}
      <section className="mb-14">
        <div className="bg-surface-card rounded-2xl border border-surface-border overflow-hidden">
          <div className="px-6 pt-6 pb-2">
            <p className="text-xs font-semibold tracking-wider text-accent-brand uppercase mb-2">
              Story 1
            </p>
            <h2 className="text-title-2 text-text-primary">
              Winning big, then barely surviving
            </h2>
            <p className="text-sm text-text-secondary mt-3 leading-relaxed">
              2026 Australian Open semifinal. Carlos Alcaraz raced to a two-set lead
              and hit <strong className="text-text-primary">96% win probability</strong>.
              Then an adductor injury struck. His odds cratered to{" "}
              <strong className="text-text-primary">13%</strong> as Alexander Zverev
              served for the match. Alcaraz broke back, fought through the fifth set,
              and won 7-5. The final scoreline &mdash; 3 sets to 2 &mdash; hides
              every twist. The probability chart tells the full story.
            </p>
          </div>
          <div className="px-4 pb-4 pt-2">
            <div className="bg-surface-deep rounded-xl p-4 border border-surface-border">
              <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-xs text-text-muted">Alcaraz Win Probability</span>
                <span className="text-xs text-text-muted">Match Progress</span>
              </div>
              <ProbabilityArc />
              <div className="flex justify-between mt-1 px-1">
                <span className="text-[10px] text-text-muted">Set 1</span>
                <span className="text-[10px] text-text-muted">Set 2</span>
                <span className="text-[10px] text-text-muted">Set 3</span>
                <span className="text-[10px] text-text-muted">Set 4</span>
                <span className="text-[10px] text-text-muted">Set 5</span>
              </div>
            </div>
          </div>
          <div className="px-6 pb-6">
            <p className="text-xs text-text-muted italic">
              A scoreline of 3-2 is close. A probability swing from 96% to 13% and
              back is extraordinary. That&apos;s what probability-first context reveals.
            </p>
          </div>
        </div>
      </section>

      {/* ── Story 2: Scheffler at the Masters ── */}
      <section className="mb-14">
        <div className="bg-surface-card rounded-2xl border border-surface-border overflow-hidden">
          <div className="px-6 pt-6 pb-4">
            <p className="text-xs font-semibold tracking-wider text-accent-brand uppercase mb-2">
              Story 2
            </p>
            <h2 className="text-title-2 text-text-primary">
              6th place, but the favorite
            </h2>
            <p className="text-sm text-text-secondary mt-3 leading-relaxed">
              2025 Masters, end of Round 1. Scottie Scheffler sat T6 at -2, one shot
              behind the co-leaders. A leaderboard said he was chasing. But prediction
              markets told a different story: Scheffler held{" "}
              <strong className="text-text-primary">19.0% win probability</strong> &mdash;
              more than double co-leader Burns at 8.6%. The model&apos;s top pick, Rory McIlroy
              at 24.4%, went on to win. Probability identified the real contenders;
              the leaderboard didn&apos;t.
            </p>
          </div>
          <div className="px-4 pb-4">
            <div className="bg-surface-deep rounded-xl border border-surface-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border">
                    <th className="text-left text-xs font-semibold text-text-muted px-4 py-2.5">Pos</th>
                    <th className="text-left text-xs font-semibold text-text-muted px-4 py-2.5">Player</th>
                    <th className="text-center text-xs font-semibold text-text-muted px-4 py-2.5">Score</th>
                    <th className="text-right text-xs font-semibold text-text-muted px-4 py-2.5">Win Prob</th>
                  </tr>
                </thead>
                <tbody>
                  {MASTERS_ROWS.map((row) => (
                    <tr
                      key={row.player}
                      className={`border-b border-surface-border last:border-b-0 ${
                        row.highlight ? "bg-emerald-50" : ""
                      }`}
                    >
                      <td className="px-4 py-2.5 text-text-muted font-mono text-xs">
                        {row.pos}
                      </td>
                      <td className="px-4 py-2.5 text-text-primary font-medium">
                        {row.player}
                        {row.player === "Rory McIlroy" && (
                          <span className="ml-1.5 text-[10px] text-accent-brand font-semibold align-top">
                            WON
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-center text-text-secondary font-mono">
                        {row.score}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono font-bold text-text-primary">
                        {row.prob}
                        {row.highlight && (
                          <div className="h-1 rounded-full bg-accent-brand mt-1" style={{
                            width: `${parseFloat(row.prob) * 3}%`,
                            marginLeft: "auto",
                          }} />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="px-6 pb-6">
            <p className="text-xs text-text-muted italic">
              Burns led the leaderboard but the market gave him 8.6%.
              McIlroy sat two shots back but had the highest probability &mdash;
              and won.
            </p>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="text-center space-y-4 pt-2">
        <h2 className="text-title-2 text-text-primary">
          Explore what the world thinks will happen
        </h2>
        <p className="text-sm text-text-secondary max-w-md mx-auto">
          Sports, politics, economics, entertainment, weather &mdash; every
          prediction, translated into probabilities.
        </p>
        <Link href="/discover">
          <Button variant="primary" size="lg">
            Open Discover
          </Button>
        </Link>
      </section>
    </div>
  );
}
