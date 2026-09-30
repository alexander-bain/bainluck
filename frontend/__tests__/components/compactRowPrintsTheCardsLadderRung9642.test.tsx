/**
 * #9642 — a collapsed group row on a ladder prints the rung the card it
 * expands into marks, not the highest rung.
 *
 * Production, 390px, 2026-09-30 ~13:00Z, the IPOS group on page one (futures
 * 30635376). Collapsed, the row read
 *
 *     Anthropic IPO?
 *     December 31, 2026                                         83%
 *
 * and tapping "Expand" drew the card with "November 30, 2026 — 60%" marked
 * under "More likely than not: November 30, 2026"; the page the row opens led
 * with the same 60%. The row took `heroOutcome` — the served first outcome,
 * the highest rung — which on a cumulative date ladder is the loosest question.
 * The card stopped doing that under #8647 (dates) and #8788 (at-least ladders);
 * its compact twin never did. The AI group on the same page showed the at-least
 * form: "40%+ … 95%" on a row whose card marks "50%+ — 65%".
 *
 * Each case renders BOTH components from one payload and asserts the row's
 * answer and number against the card's marked rung, so the guard fails if
 * either side moves alone.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard, FuturesCompactRow } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Point = { label: string; probability: number; value: number; source?: string };

function ladderData(name: string, points: Point[], format = "threshold_heatmap"): FeedFuturesData {
  return {
    id: 30635376,
    name,
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2027-07-01T00:00:00Z",
    // As served: the top three by price, highest first.
    top_outcomes: [...points]
      .sort((a, b) => b.probability - a.probability)
      .slice(0, 3)
      .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, rank: i + 1, movement: null })),
    outcome_count: points.length,
    volume_24h: 500_000,
    confidence_tier: "high",
    discover_card: { suggested_format: format, threshold_points: points },
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function row(data: FeedFuturesData): { answer: string | null; percent: string | null } {
  const html = renderToStaticMarkup(<FuturesCompactRow item={itemFor(data)} data={data} />);
  const answer = html.match(/data-testid="compact-row-answer">([^<]*)</)?.[1] ?? null;
  const percent = html.match(/data-testid="compact-row-percent">([^<]*)</)?.[1] ?? null;
  return { answer, percent };
}

/** The rung QuantityGroup draws on the tinted inset row — the card's mark. */
function cardMarkedRung(data: FeedFuturesData): string | null {
  const html = renderToStaticMarkup(
    <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
  const marks = Array.from(
    html.matchAll(/<div class="[^"]*bg-accent-brand\/\[0\.06\][^"]*" aria-label="([^"]*): [^"]*"/g),
    (m) => m[1],
  );
  return marks.length === 1 ? marks[0] : null;
}

const date = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  source: "date_bucket",
});
const rung = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  source: "outcome",
});

// The production specimen, verbatim from /api/feed 2026-09-30.
const ANTHROPIC_IPO = [
  date("September 30, 2026", 20260930, 0.0005),
  date("October 15, 2026", 20261015, 0.0085),
  date("October 31, 2026", 20261031, 0.0435),
  date("November 15, 2026", 20261115, 0.265),
  date("November 30, 2026", 20261130, 0.595),
  date("December 15, 2026", 20261215, 0.755),
  date("December 31, 2026", 20261231, 0.815),
];

describe("#9642 — a group row prints its card's ladder rung", () => {
  it("date ladder: the row names the earliest date over even, as the card marks it", () => {
    const data = ladderData("Anthropic IPO?", ANTHROPIC_IPO);
    expect(cardMarkedRung(data)).toBe("November 30, 2026");
    expect(row(data)).toEqual({ answer: "November 30, 2026", percent: "60%" });
  });

  it("at-least ladder: the row names the most specific rung over even", () => {
    const data = ladderData("Next Google Gemini Pro Model: Humanity's Last Exam Debut?", [
      rung("40%+", 40, 0.957),
      rung("45%+", 45, 0.9),
      rung("50%+", 50, 0.65),
      rung("55%+", 55, 0.385),
    ]);
    expect(cardMarkedRung(data)).toBe("50%+");
    expect(row(data)).toEqual({ answer: "50%+", percent: "65%" });
  });

  it("a marked rung outside the served top three is read off the ladder", () => {
    const data = ladderData("Saudi pipeline restarts?", [
      date("October 31", 20261031, 0.52),
      date("November 30", 20261130, 0.6),
      date("December 15", 20261215, 0.7),
      date("December 31", 20261231, 0.8),
    ]);
    expect(data.top_outcomes.map((o) => o.name)).not.toContain("October 31");
    expect(cardMarkedRung(data)).toBe("October 31");
    expect(row(data)).toEqual({ answer: "October 31", percent: "52%" });
  });

  // ── Unchanged shapes: the rule only replaces a default it disagrees with. ──

  it("a date ladder with no rung over even keeps the highest rung, as the card does", () => {
    const data = ladderData("Putin out as President of Russia?", [
      date("September 30, 2026", 20260930, 0.0005),
      date("December 31, 2026", 20261231, 0.027),
      date("June 30, 2027", 20270630, 0.105),
    ]);
    expect(cardMarkedRung(data)).toBe("June 30, 2027");
    expect(row(data)).toEqual({ answer: "June 30, 2027", percent: "11%" });
  });

  it("a plain outcome distribution keeps the served leader", () => {
    const data = ladderData("Fed decision in Oct 2026?", [
      rung("Cut 25bps", 1, 0.01),
      rung("Fed maintains rate", 2, 0.66),
      rung("Hike 25bps", 3, 0.33),
    ]);
    expect(row(data)).toEqual({ answer: "Fed maintains rate", percent: "66%" });
  });

  it("a title naming one date leg keeps that leg (#9401 still wins)", () => {
    const data = ladderData("Will Iran target an Arab country by September 30, 2026?", [
      date("September 30", 20260930, 0.285),
      date("October 31", 20261031, 0.64),
      date("December 31", 20261231, 0.9),
    ]);
    expect(row(data)).toEqual({ answer: "September 30", percent: "29%" });
  });

  it("a market the card does not draw as a ladder keeps the served leader", () => {
    const data = ladderData("Anthropic IPO?", ANTHROPIC_IPO, "leaderboard");
    expect(row(data).answer).toBe("December 31, 2026");
  });
});
