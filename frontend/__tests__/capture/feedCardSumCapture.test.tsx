/**
 * UX-P160 — THE CARD RULE REACHES THE FEED, for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * #2060 gave a two-outcome card ONE rounding. UX-P159 (#2088) gave the pair that
 * legitimately does not total 100 a sentence saying so. Both shipped on the two
 * LABELING serializers only — the surfaces Alex grades on, not the ones a stranger
 * reads. #2088's third acceptance criterion asks that the served feed agree with the
 * labeling card, and it could not, because the feed had no card rule to agree with:
 * before this queue `grep rendered_percent backend/app/routes/feed.py` returned
 * nothing, and `FeedCard.tsx` printed `Math.round(outcome.probability * 100)` per
 * outcome, independently.
 *
 * ═══ WHICH SURFACE, MEASURED RATHER THAN ASSUMED ═══
 *
 * NOT Discover. `components/discover/FuturesCard.tsx` prints only the hero leader, so
 * a two-outcome card shows ONE number there and no sum is visible. The pair is printed
 * by `components/FeedCard.tsx`, which serves the category pages, the sports page and
 * my-stuff. Both are fed by `GET /api/feed`, so this is one server change; the
 * reader-visible payoff is on the category and sports pages.
 *
 * AMENDED BY UX-P162: still true about the SUM — Discover prints one number, so no
 * total is visible there — but that hero was rounding its own raw probability while
 * this card took the rule, so the two surfaces could disagree by a point on the SAME
 * market. The hero now calls `renderedLeaderPercent` too. See
 * `__tests__/components/discoverHeroAgreesWithFeedCard.test.tsx`.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * Every card here is the SHIPPED `FeedCard` component with the app's own compiled
 * stylesheet, and every number comes from
 * `backend/tests/fixtures/feed_futures_cards_20260829.json` — the LIVE output of
 * `GET /api/feed` captured 2026-08-29 across every pair-printing surface. Nothing on
 * this page is drawn by hand.
 *
 *   • Panel 1 — the two cards that print 101 today, BEFORE and AFTER.
 *   • Panel 2 — the four cards that print an unexplained non-100, BEFORE and AFTER.
 *   • Panel 3 — the whole two-outcome pool, so the DENSITY of the change is visible
 *     rather than asserted: which cards change, which gain a line, which do neither.
 *
 * BEFORE is reconstructed by serving the OLD arithmetic — one independent
 * `Math.round(p * 100)` per side — and stripping the sentence, because that is
 * literally what the previous build printed. It cannot be produced by omitting the
 * served fields: an absent key makes the component DERIVE them, which is the
 * deliberate pre-deploy fallback and would render an "after" labelled "before".
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=feedCardSumCapture
 *
 * With no env var set it is an ordinary test that renders every panel and asserts the
 * rig works, same as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

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

import FeedCard from "@/components/FeedCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { CARD_SUM_EXPLANATION } from "@/lib/cardSum";
import {
  SUM_INDEPENDENT_PRICES,
  cardSumReason,
  renderedCardPercents,
} from "@/lib/renderedPercent";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const POOL_PATH = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "feed_futures_cards_20260829.json"
);

/** The two cards that print 101 on the deployed build. */
const PRINTS_101 = [108621, 57792416];
/** The four that print a real, unexplained non-100. */
const UNEXPLAINED = [20569379, 109349, 59699903, 52756062];
/** The one two-outcome card that is already right and must stay silent. */
const ALREADY_CORRECT = 56722520;

interface PoolOutcome {
  id: number;
  name: string;
  probability: number | null;
}
interface PoolRow {
  id: number;
  name: string;
  source?: string;
  outcome_count?: number;
  top_outcomes: PoolOutcome[];
}

function pool(): PoolRow[] {
  return JSON.parse(fs.readFileSync(POOL_PATH, "utf8")).items as PoolRow[];
}

/** The printed slice — what both feed serializers build and what a reader sees. */
function printed(row: PoolRow): PoolOutcome[] {
  return row.top_outcomes.slice(0, 3);
}

function twoOutcome(): PoolRow[] {
  return pool().filter((r) => printed(r).length === 2);
}

/** What the browser prints TODAY: one independent `Math.round(p * 100)` per side. */
function oldPercent(p: number | null): number | null {
  return p === null ? null : Math.floor(p * 100 + 0.5);
}

/** A pool row → the feed item the server now serves, card rule applied. */
function itemFor(row: PoolRow, before = false): FeedItem {
  const outcomes = printed(row);
  const probabilities = outcomes.map((o) => o.probability);
  const percents = before
    ? probabilities.map(oldPercent)
    : renderedCardPercents(probabilities);
  const data: Record<string, unknown> = {
    id: row.id,
    name: row.name,
    source: row.source ?? null,
    outcome_count: row.outcome_count ?? outcomes.length,
    status: "open",
    top_outcomes: outcomes.map((o, i) => ({
      id: o.id,
      name: o.name,
      probability: o.probability,
      rank: i + 1,
      movement: null,
      rendered_percent: percents[i],
    })),
    // BEFORE served no reason at all, and the key must be PRESENT-and-null rather
    // than absent — absent would make the component derive it, producing an "after".
    card_sum_reason: before ? null : cardSumReason(probabilities),
  };
  return { type: "futures", data: data as unknown as FeedFuturesData } as FeedItem;
}

const html = (row: PoolRow, before = false) =>
  renderToStaticMarkup(<FeedCard item={itemFor(row, before)} />);

/** The percents a rendered card actually prints, in printed order. */
function printedNumbers(markup: string): number[] {
  return [...markup.matchAll(/>(\d+)%</g)].map((m) => Number(m[1]));
}

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

describe("UX-P160 — the card rule reaches the feed", () => {
  it("the fixture is the real captured pool and still holds the cards this queue measured", () => {
    // If this stops holding, every panel below is rendering something else.
    const all = pool();
    expect(all.length).toBe(87);
    const rows = twoOutcome();
    expect(rows.length).toBe(7);
    for (const id of [...PRINTS_101, ...UNEXPLAINED, ALREADY_CORRECT]) {
      expect(rows.find((r) => r.id === id)).toBeDefined();
    }
  });

  it("the two 101 cards print 101 BEFORE and exactly 100 AFTER", () => {
    for (const id of PRINTS_101) {
      const row = twoOutcome().find((r) => r.id === id)!;
      // The mini-list rows are the last two percents on the card; the first is the
      // headline, which is the leader's number repeated.
      const before = printedNumbers(html(row, true));
      const after = printedNumbers(html(row));
      expect(before.slice(-2).reduce((a, b) => a + b, 0)).toBe(101);
      expect(after.slice(-2).reduce((a, b) => a + b, 0)).toBe(100);
    }
  });

  it("the headline never disagrees with its own row, before or after", () => {
    // Queue 283's invariant. The headline is printed first and repeats the leader.
    for (const row of twoOutcome()) {
      for (const before of [true, false]) {
        const nums = printedNumbers(html(row, before));
        expect(nums[0]).toBe(nums[1]);
      }
    }
  });

  it("the four disagreeing cards keep their numbers and gain a sentence", () => {
    for (const id of UNEXPLAINED) {
      const row = twoOutcome().find((r) => r.id === id)!;
      const before = html(row, true);
      const after = html(row);
      // The numbers are IDENTICAL. This queue EXPLAINS these cards; it does not
      // normalize them, and a rig that quietly fixed them would be selling a
      // different change from the one that ships.
      expect(printedNumbers(before)).toEqual(printedNumbers(after));
      expect(before).not.toContain('data-testid="card-sum-explanation"');
      expect(after).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    }
  });

  it("SIX of the seven two-outcome cards change; the seventh deliberately does not", () => {
    // The density question, answered against the real capture rather than guessed.
    const rows = twoOutcome();
    const changed = rows.filter((r) => html(r, true) !== html(r));
    expect(changed.map((r) => r.id).sort()).toEqual(
      [...PRINTS_101, ...UNEXPLAINED].sort()
    );
    const correct = rows.find((r) => r.id === ALREADY_CORRECT)!;
    expect(html(correct, true)).toBe(html(correct));
    expect(html(correct)).not.toContain('data-testid="card-sum-explanation"');
  });

  it("the 80 multi-outcome cards in the pool are untouched", () => {
    // The un-fired direction, at population scale. A cap whose guard only proves it
    // fires is how the Sports tab got emptied (gotcha #43).
    const others = pool().filter((r) => printed(r).length !== 2);
    expect(others.length).toBe(80);
    for (const row of others) {
      expect(html(row)).not.toContain('data-testid="card-sum-explanation"');
    }
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) return;

    const css = appStylesheet();
    const rows = twoOutcome();

    const panel = (ids: number[]) =>
      ids
        .map((id) => {
          const row = rows.find((r) => r.id === id)!;
          const probabilities = printed(row).map((o) => o.probability);
          const beforeNums = probabilities.map(oldPercent);
          const afterNums = renderedCardPercents(probabilities);
          const sum = (ns: Array<number | null>) =>
            ns.reduce<number>((a, b) => a + (b ?? 0), 0);
          return `
      <div class="pair">
        <div class="meta">
          <span class="mono">${row.id}</span>
          <strong>${row.name}</strong>
          <span class="src">${row.source ?? "—"}</span>
        </div>
        <div class="cols">
          <div class="col">
            <div class="tag bad">BEFORE — sums to ${sum(beforeNums)}</div>
            ${html(row, true)}
          </div>
          <div class="col">
            <div class="tag good">AFTER — sums to ${sum(afterNums)}${
              cardSumReason(probabilities) ? ", and says why" : ""
            }</div>
            ${html(row)}
          </div>
        </div>
      </div>`;
        })
        .join("\n");

    const poolRow = (row: PoolRow) => {
      const probabilities = printed(row).map((o) => o.probability);
      const before = probabilities.map(oldPercent);
      const after = renderedCardPercents(probabilities);
      const reason = cardSumReason(probabilities);
      const changed = JSON.stringify(before) !== JSON.stringify(after);
      return `<tr class="${changed ? "hit" : reason ? "warn" : ""}">
        <td class="mono">${row.id}</td>
        <td>${row.name}</td>
        <td class="mono num">${before.join(" / ")}</td>
        <td class="mono num">${after.join(" / ")}</td>
        <td class="mono num">${after.reduce<number>((a, b) => a + (b ?? 0), 0)}</td>
        <td>${reason ? "explained" : changed ? "corrected" : "unchanged"}</td>
      </tr>`;
    };

    const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>UX-P160 — the card rule reaches the feed</title>
<style>${css}</style>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 28px 32px; background: #f6f7f9; color: #14161a; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; margin: 32px 0 12px; }
  .lede { font-size: 13px; line-height: 1.6; color: #374151; max-width: 78ch; margin: 0 0 8px; }
  .pair { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; margin-bottom: 14px; }
  .meta { display: flex; gap: 10px; align-items: baseline; font-size: 12px; margin-bottom: 10px; color: #6b7280; }
  .meta strong { color: #14161a; font-size: 13px; }
  .src { margin-left: auto; text-transform: uppercase; letter-spacing: .05em; font-size: 10px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .tag { font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; margin-bottom: 6px; }
  .tag.bad { color: #b91c1c; } .tag.good { color: #15803d; }
  table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #f1f2f4; }
  th { background: #fafbfc; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
  tr.hit { background: #fef6f6; } tr.warn { background: #fffbeb; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .num { text-align: right; white-space: nowrap; }
</style>
</head><body>
<h1>UX-P160 — the card rule reaches the feed</h1>
<p class="lede">
  Every card below is the shipped <code>FeedCard</code> component with the app's own
  compiled stylesheet. Every number comes from <code>GET /api/feed</code> captured
  2026-08-29 across the default feed, the politics / economics / entertainment category
  tags and sports mode — 87 futures cards, 7 of which print a pair. Nothing here is
  drawn by hand. This is the component behind <code>/categories/*</code>,
  <code>/sports</code> and <code>/my-stuff</code>; Discover's own futures card prints
  only the hero leader, so no sum is visible there.
</p>
<p class="lede">
  <strong>BEFORE</strong> is the previous build's arithmetic — one independent
  <code>Math.round(p&nbsp;×&nbsp;100)</code> per side and no sentence.
</p>

<h2>1 · The two cards that print 101 today</h2>
${panel(PRINTS_101)}

<h2>2 · The four that print an unexplained non-100</h2>
<p class="lede">
  These numbers do not change and must not: normalizing a pair that sums to 41 would
  invent fifty-nine points of probability. The defect was never the arithmetic — it
  was that a reader could not tell this apart from the 101 above.
</p>
${panel(UNEXPLAINED)}

<h2>3 · The whole two-outcome pool — the density of the change</h2>
<table>
  <thead><tr><th>id</th><th>market</th><th class="num">before</th><th class="num">after</th><th class="num">sum</th><th>outcome</th></tr></thead>
  <tbody>${rows.map(poolRow).join("\n")}</tbody>
</table>
<p class="lede" style="margin-top:10px">
  Six of seven change. <code>${ALREADY_CORRECT}</code> already totals 100 and is left
  exactly as it was — the un-fired direction, asserted as explicitly as the fired one.
  The other 80 cards in the capture print three or more outcomes and are untouched:
  arity other than two returns no reason, meaning "no claim about a total" rather than
  "checked and fine".
</p>
</body></html>`;

    fs.mkdirSync(dir, { recursive: true });
    const out = path.join(dir, "p160-feed-card-sum.html");
    fs.writeFileSync(out, page);

    // The rig asserts its OWN artifact — a generator that writes a page nobody
    // checked is how a drawing gets mistaken for a render.
    const written = fs.readFileSync(out, "utf8");
    expect(written).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    expect(written.length).toBeGreaterThan(20_000);
    for (const id of [...PRINTS_101, ...UNEXPLAINED]) {
      expect(written).toContain(String(id));
    }
    // The stylesheet actually loaded, so the panels are styled rather than bare.
    expect(css.length).toBeGreaterThan(1_000);
  });
});
