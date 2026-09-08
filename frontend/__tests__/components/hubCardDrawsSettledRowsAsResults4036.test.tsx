/**
 * #4036 — a hub card draws a GRADED row as a result, never as a live price.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production `/hub/tennis`, 390px, 2026-09-08, the card "Who will win a ATP
 * Grand Slam in 2026?":
 *
 *     Alexander Zverev    ████████░░  99%
 *     Jannik Sinner       ████████░░  99%
 *     Carlos Alcaraz      ███████░░░  97%
 *     Ben Shelton         █░░░░░░░░░   9%
 *
 * All four rows carried `settled: true`, and the first three carried
 * `is_winner: true`. Three men who had WON a 2026 Grand Slam, drawn as
 * contenders with live-book progress bars. Measured the same day across all five
 * hubs: of 426 cards carrying outcomes, 10 drew a settled leg as a percentage.
 *
 * ═══ 🔴 WHY THIS IS A ROUTE-THROUGH-COMPONENT GUARD ═══
 *
 * THE LOAD-BEARING PARAGRAPH. The defect was never in the settled vocabulary —
 * `PropGroupCard` had it right and `settledLadderLegsDoNotRenderAsOdds3868`
 * proves so. It was that the hub's own `OutcomeRow` never ASKED. The payload
 * carried `settled`/`is_winner` the whole time and one component read neither.
 *
 * So a unit test over `SettledOutcomeMark` would pass on the bug: the mark was
 * always correct, it was simply never rendered. Only rendering the real route
 * can fail on an unwired row. That is the same reason
 * `hubOutcomeRowNamesItsMarket3538` renders the page rather than a helper, and
 * this file reuses its harness deliberately.
 *
 * ═══ 🔴 WHY EVERY NEGATIVE ARM IS PAIRED ═══
 *
 * "The card no longer contains 99%" is satisfied by a component that renders
 * nothing at all. Every `not.toContain` below is paired with a positive — the
 * row's NAME is still on the card, and the grade is drawn — so an empty render
 * fails rather than passes.
 *
 * The mirrors matter as much as the complaint. A fix that drew "Won"/"Lost" on
 * every row would satisfy the complaint and destroy the card, so the live
 * contender is pinned in the SAME payload, on the same rail, and must come
 * through byte-identical: its percentage AND its bar. And a payload with no
 * `settled` field at all — the first half of any split deploy, since Vercel
 * ships before Heroku — must render exactly as it did before this ship.
 *
 * ═══ THE FIXTURES ARE THE REAL THING ═══
 *
 * `/api/hub/esports` market 13886735 and `/api/hub/tennis` market 224, read
 * verbatim 2026-09-08 ~12:30pm PT. The esports award is the mixed case and is
 * the important one: a settled winner, three settled losers and one genuinely
 * live nominee on a single card. Only a mixed card can show all three failures
 * at once.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    href,
    className,
    children,
  }: {
    href: string;
    className?: string;
    children: React.ReactNode;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

jest.mock("next/navigation", () => ({
  useParams: () => ({ competition: "esports" }),
}));

let currentPayload: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: currentPayload, error: undefined }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEvent: () => undefined }),
}));

import CompetitionHubPage from "../../app/hub/[competition]/page";

// ── Verbatim production rows ────────────────────────────────────────────────

type Row = {
  name: string;
  probability: number;
  settled?: boolean;
  is_winner?: boolean | null;
};

const EMMY_CARD = "Sports Emmy Award for Outstanding ESports Championship Coverage?";
/** The mixed case: one live nominee, one winner, three losers. */
const EMMY_ROWS: Row[] = [
  { name: "2025 Apex Legends Global Series Championship", probability: 0.19, settled: false, is_winner: false },
  { name: "2025 Call of Duty League Championship Weekend", probability: 0.99, settled: true, is_winner: true },
  { name: "League of Legends Worlds 2025 Final", probability: 0.37, settled: true, is_winner: false },
  { name: "VALORANT Champions 2025 Grand Final", probability: 0.16, settled: true, is_winner: false },
  { name: "Tie", probability: 0.03, settled: true, is_winner: false },
];

const SLAM_CARD = "Who will win a ATP Grand Slam in 2026?";
/** The headline card, all four visible rows settled, three of them won. */
const SLAM_ROWS: Row[] = [
  { name: "Alexander Zverev", probability: 0.99, settled: true, is_winner: true },
  { name: "Jannik Sinner", probability: 0.99, settled: true, is_winner: true },
  { name: "Carlos Alcaraz", probability: 0.97, settled: true, is_winner: true },
  { name: "Ben Shelton", probability: 0.085, settled: true, is_winner: false },
];

/**
 * The same Emmy card as an OLDER backend would serve it: no `settled`, no
 * `is_winner`. Not a hypothetical — this is what every payload in flight looks
 * like during a Vercel-first deploy.
 */
const EMMY_ROWS_PRE_3868: Row[] = EMMY_ROWS.map(({ name, probability }) => ({
  name,
  probability,
}));

const market = (id: number, name: string, rows: Row[]) => ({
  id,
  name,
  source: "kalshi",
  external_id: `X-${id}`,
  market_tier: 3,
  category: "entertainment",
  resolution_date: null,
  outcome_count: rows.length,
  top_outcomes: rows.map((r, i) => ({
    id: id * 100 + i,
    name: r.name,
    probability: r.probability,
    opening_probability: 0.2,
    rank: i + 1,
    movement_24h: null,
    team_id: null,
    ...("settled" in r ? { settled: r.settled, is_winner: r.is_winner } : {}),
  })),
  canonical_market_key: null,
  group_id: null,
  section: "awards",
});

const payloadWith = (awards: unknown[]) => ({
  competition: "esports",
  label: "Esports",
  title: "Esports",
  emoji: "🎮",
  blurb: "",
  sport_key: "esports",
  section_labels: {},
  upcoming_label: "Upcoming",
  upcoming_label_neutral: "Upcoming",
  upcoming: [],
  sections: { awards },
  total_markets: awards.length,
  tier: 3,
  pool_counts: {},
  section_counts: {
    awards: { total: awards.length, shown: awards.length, dropped: 0, answers: awards.length },
  },
  cache: null,
  availability: "fresh",
});

const render = () => renderToStaticMarkup(React.createElement(CompetitionHubPage));

/** The rendered card for a market, as a markup slice starting at its name. */
function cardFor(markup: string, name: string): string {
  const at = markup.indexOf(name);
  expect(at).toBeGreaterThan(-1);
  const start = markup.lastIndexOf("<a ", at);
  const next = markup.indexOf("<a ", at);
  return markup.slice(start, next === -1 ? markup.length : next);
}

const count = (haystack: string, needle: string): number =>
  haystack.split(needle).length - 1;

/** The live-book bar. A settled row must not draw one. */
const BAR = "bg-accent-brand";

describe("#4036 — a settled hub row is a result, not a price", () => {
  describe("the mixed card (the complaint)", () => {
    let card: string;
    beforeAll(() => {
      currentPayload = payloadWith([market(13886735, EMMY_CARD, EMMY_ROWS)]);
      card = cardFor(render(), EMMY_CARD);
    });

    it("draws the winner as Won, not as 99%", () => {
      // Paired: the row is still ON the card, and its grade replaced its price.
      expect(card).toContain("2025 Call of Duty League Championship Weekend");
      expect(card).toContain("Won");
      expect(card).not.toContain("99%");
    });

    it("draws the three eliminated nominees as Lost, not as stale prices", () => {
      for (const name of [
        "League of Legends Worlds 2025 Final",
        "VALORANT Champions 2025 Grand Final",
        "Tie",
      ]) {
        expect(card).toContain(name);
      }
      expect(count(card, "Lost")).toBe(3);
      // The prices a reader was being offered for questions already answered.
      expect(card).not.toContain("37%");
      expect(card).not.toContain("16%");
      expect(card).not.toContain("3%");
    });

    it("draws exactly one live-book bar — the one live nominee's", () => {
      // The bar is a reading of a live book. Four of these five rows have no
      // book left to read. Before this ship the card drew five.
      expect(count(card, BAR)).toBe(1);
    });

    it("CONTROL — the live nominee is untouched: its percentage AND its bar", () => {
      // The remedy must not become the regression. A fix that graded every row
      // would pass every arm above and destroy the card.
      expect(card).toContain("2025 Apex Legends Global Series Championship");
      expect(card).toContain("19%");
      expect(count(card, BAR)).toBe(1);
    });

    it("CONTROL — every outcome is still on the card", () => {
      // Rules out the empty render that would satisfy each `not.toContain`.
      for (const r of EMMY_ROWS) expect(card).toContain(r.name);
    });
  });

  describe("the headline card — all four rows settled, three of them won", () => {
    let card: string;
    beforeAll(() => {
      currentPayload = payloadWith([market(224, SLAM_CARD, SLAM_ROWS)]);
      card = cardFor(render(), SLAM_CARD);
    });

    it("Zverev, Sinner and Alcaraz read Won — not 99% / 99% / 97%", () => {
      for (const name of ["Alexander Zverev", "Jannik Sinner", "Carlos Alcaraz"]) {
        expect(card).toContain(name);
      }
      expect(count(card, "Won")).toBe(3);
      expect(card).not.toContain("99%");
      expect(card).not.toContain("97%");
    });

    it("Shelton, settled and beaten, reads Lost rather than 9%", () => {
      expect(card).toContain("Ben Shelton");
      expect(count(card, "Lost")).toBe(1);
      expect(card).not.toContain("9%");
    });

    it("draws no bars at all — there is no live book on this card", () => {
      expect(count(card, BAR)).toBe(0);
    });
  });

  describe("CONTROL — a payload from before #3868 renders exactly as it did", () => {
    let card: string;
    beforeAll(() => {
      currentPayload = payloadWith([market(13886735, EMMY_CARD, EMMY_ROWS_PRE_3868)]);
      card = cardFor(render(), EMMY_CARD);
    });

    it("prices every row and grades none", () => {
      // Vercel ships the frontend before Heroku. For the length of that window
      // the fields are absent, and absent is not `false` — it is "this backend
      // does not say", which must render as the status quo and never as Lost.
      expect(card).not.toContain("Won");
      expect(card).not.toContain("Lost");
      for (const pct of ["19%", "99%", "37%", "16%", "3%"]) {
        expect(card).toContain(pct);
      }
    });

    it("draws all five bars", () => {
      expect(count(card, BAR)).toBe(5);
    });
  });
});
