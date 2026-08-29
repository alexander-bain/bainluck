/**
 * UX-P162 — ONE NUMBER PER QUESTION, ACROSS SURFACES, for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * The same futures market, from the same `GET /api/feed` payload, is drawn by two
 * components: `FeedCard` (the category pages, `/sports`, `/my-stuff`) and
 * `discover/FuturesCard` (Discover, the default landing page). Since #2060/UX-P160
 * the first takes the CARD RULE and the second rounded the leader's raw
 * probability, so the two could print different integers for one question — the
 * "blend is the product" thesis broken between surfaces rather than within a card.
 *
 * ═══ THE HONEST HEADLINE: THIS IS LATENT ═══
 *
 * Measured on the deployed feed 2026-08-29 across all five feed surfaces: 114
 * unique futures cards, 7 two-outcome, and ZERO disagree — every live pair sums to
 * exactly 1.00, where the rule and the raw arithmetic agree by construction.
 * Panel 2 is that fact, drawn rather than asserted: the whole live pool, before and
 * after, identical. Nothing a reader can see changed today.
 *
 * Panel 1 is why it was fixed anyway — the structural case, which is one pair away.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * Every card is the SHIPPED component with the app's own compiled stylesheet.
 * Panel 2's numbers come from `backend/tests/fixtures/feed_futures_cards_20260829.json`,
 * the live `GET /api/feed` capture UX-P160 committed. Nothing is drawn by hand.
 *
 * BEFORE is reconstructed by swapping the printed hero back to the pre-queue
 * expression's output — `formatProbabilityPercent(prob)` with no `{ rendered }`
 * channel — because that is literally what the previous build printed. It cannot be
 * produced by omitting the served field: an absent key makes the component DERIVE
 * the rule, which is the deliberate pre-deploy fallback and would render an "after"
 * labelled "before".
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=discoverHeroAgreementCapture
 *
 * With no env var set it is an ordinary test that renders every panel and asserts
 * the rig works, same as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";
import { FuturesCard } from "../../components/discover/FuturesCard";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "feed_futures_cards_20260829.json",
);

type FixtureOutcome = { id: number; name: string; probability: number | null; rank?: number };
type FixtureCard = { id: number; name: string; top_outcomes: FixtureOutcome[] };

function liveCards(): FixtureCard[] {
  return JSON.parse(fs.readFileSync(FIXTURE, "utf8")).items;
}

/** The app's own compiled stylesheet, so the cards look like the product. */
function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

function asData(card: FixtureCard): FeedFuturesData {
  return {
    llm_sport_category: "politics",
    sport_name: "Politics",
    status: "open",
    source: "kalshi",
    resolution_date: "2026-11-03T00:00:00Z",
    outcome_count: card.top_outcomes.length,
    ...card,
    top_outcomes: card.top_outcomes.map((o, i) => ({ rank: i + 1, movement: null, ...o })),
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

const HERO_RE = /(data-testid="futures-hero-probability"[^>]*>)([^<]+)(<)/;

function discoverHtml(data: FeedFuturesData): string {
  return renderToStaticMarkup(
    <FuturesCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

function heroText(html: string): string | null {
  const m = html.match(HERO_RE);
  return m ? m[2] : null;
}

/** The pre-queue expression, verbatim: one inline round, UX-P046's floor, no rule. */
function oldHeroPrinted(p: number): string {
  const rounded = Math.round(p * 100);
  if (rounded <= 0 && p > 0) return "&lt;1%";
  if (rounded >= 100 && p < 1) return "&gt;99%";
  return `${rounded}%`;
}

/**
 * BEFORE: the real render, with ONLY the hero swapped back to the pre-queue
 * output. Scoped to the hero span rather than replaced globally, so an also-ran
 * row that happens to print the same integer is not rewritten too.
 */
function beforeDiscoverHtml(data: FeedFuturesData): string {
  const html = discoverHtml(data);
  const prob = data.top_outcomes?.[0]?.probability;
  if (prob == null) return html;
  return html.replace(HERO_RE, (_m, open, _val, close) => `${open}${oldHeroPrinted(prob)}${close}`);
}

function feedCardHtml(data: FeedFuturesData): string {
  return renderToStaticMarkup(<FeedCard item={itemFor(data)} />);
}

// ── Panel 1: the structural case ─────────────────────────────────────────────
//
// 0.5525 + 0.4425 = 0.995 — inside the [0.99, 1.01] complement band, so the card
// rule normalizes by the true total: 0.5525 / 0.995 = 0.555276… → 56. Raw half-up
// on the served probability gives floor(55.25 + 0.5) = 55. Two surfaces, one
// question, two numbers.
const STRUCTURAL: FixtureCard = {
  id: 999001,
  name: "Which party will win the U.S. House?",
  top_outcomes: [
    { id: 1, name: "Democratic Party", probability: 0.5525 },
    { id: 2, name: "Republican Party", probability: 0.4425 },
  ],
};

function panelOne(): string {
  const data = asData(STRUCTURAL);
  const before = beforeDiscoverHtml(data);
  const after = discoverHtml(data);
  const feed = feedCardHtml(data);
  return `<section>
  <h2>Panel 1 — the structural case: a pair summing to 0.995</h2>
  <p class="note bad">BEFORE, Discover headlined <b>${heroText(before)}</b> while the category page
  printed <b>56%</b> for the same market from the same payload. AFTER, both read <b>56%</b>.</p>
  <table>
    <thead><tr>
      <th>Discover — BEFORE (deployed)</th>
      <th>Discover — AFTER (this branch)</th>
      <th>/categories/politics — unchanged</th>
    </tr></thead>
    <tbody><tr>
      <td class="col">${before}</td>
      <td class="col">${after}</td>
      <td class="col">${feed}</td>
    </tr></tbody>
  </table>
</section>`;
}

// ── Panel 2: the live pool, proving the change is latent ─────────────────────

function twoOutcomeLiveCards(): FixtureCard[] {
  return liveCards().filter((c) => (c.top_outcomes ?? []).length === 2);
}

function panelTwo(): string {
  const cards = twoOutcomeLiveCards();
  const rows = cards
    .map((c) => {
      const data = asData(c);
      const before = beforeDiscoverHtml(data);
      const after = discoverHtml(data);
      const same = heroText(before) === heroText(after);
      return `<tr>
        <td class="name">${c.name}<br><small>${(c.top_outcomes ?? [])
          .map((o) => o.probability)
          .join(" + ")} = ${(c.top_outcomes ?? []).reduce((a, o) => a + (o.probability ?? 0), 0)}</small></td>
        <td class="col">${before}</td>
        <td class="col">${after}</td>
        <td class="${same ? "ok" : "bad"}">${same ? "unchanged" : "CHANGED"}</td>
      </tr>`;
    })
    .join("\n");
  return `<section>
  <h2>Panel 2 — the whole live two-outcome pool (${cards.length} cards)</h2>
  <p class="note ok">Every live pair sums to exactly 1.00, where the rule and the raw
  arithmetic agree by construction. Nothing a reader can see changed today — that is
  the finding, drawn rather than asserted.</p>
  <table>
    <thead><tr><th>Market</th><th>BEFORE</th><th>AFTER</th><th>Diff</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
</section>`;
}

function page(): string {
  return `<!doctype html>
<meta charset="utf-8">
<title>UX-P162 — the Discover hero agrees with the category page</title>
<style>${appStylesheet()}</style>
<style>
  body { font: 14px/1.5 -apple-system, system-ui, sans-serif; margin: 32px; background: #fff; color: #111; }
  h1 { font-size: 22px; } h2 { font-size: 16px; margin-top: 34px; }
  table { border-collapse: collapse; margin-top: 12px; }
  th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #666; padding: 6px 10px; }
  td { vertical-align: top; padding: 10px; border-top: 1px solid #eee; }
  td.col { width: 340px; }
  td.name { width: 230px; font-size: 12px; }
  small { color: #777; font-family: ui-monospace, monospace; }
  .note { max-width: 760px; } .ok { color: #0a7d38; } .bad { color: #b4232c; }
</style>
<h1>UX-P162 — one number per question, across surfaces</h1>
<p class="note">Discover's hero rounded the leader's raw probability while the category
page took the card rule. Both now call one function, so agreement is a property of the
code rather than of two hand-copies.</p>
${panelOne()}
${panelTwo()}
`;
}

describe("UX-P162 capture", () => {
  it("the structural case disagrees before and agrees after", () => {
    const data = asData(STRUCTURAL);
    expect(heroText(beforeDiscoverHtml(data))).toBe("55%");
    expect(heroText(discoverHtml(data))).toBe("56%");
    // The category page never moved — it already had the rule.
    expect(feedCardHtml(data)).toContain("56%");
  });

  it("the live pool is unchanged, which is the honest headline", () => {
    const cards = twoOutcomeLiveCards();
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) {
      const data = asData(c);
      expect(heroText(beforeDiscoverHtml(data))).toBe(heroText(discoverHtml(data)));
    }
  });

  it("renders the page, and writes it when UX_CAPTURE_DIR is set", () => {
    const html = page();
    expect(html).toContain("Panel 1");
    expect(html).toContain("Panel 2");
    const dir = process.env.UX_CAPTURE_DIR;
    if (dir) {
      fs.mkdirSync(dir, { recursive: true });
      const out = path.join(dir, "ux-p162-discover-hero-agreement.html");
      fs.writeFileSync(out, html, "utf8");
      // eslint-disable-next-line no-console
      console.log(`capture written: ${out}`);
    }
  });
});
