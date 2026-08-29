/**
 * UX-P165 — the /search category browser stops labelling markets "Other 100%"
 * and "Candidate Z 100%", for Alex's eyeball.
 *
 * ═══ WHAT A READER SEES TODAY ═══
 *
 * Read on the deployed build, 2026-08-29, over ALL 21,441 markets the browse
 * endpoint serves — a 100% sweep, not a sample:
 *
 *     FedEx Cup Playoffs: Winner                        ->  Other 100%
 *     2026 Men's US Open Winner (Tennis)                ->  Other 100%
 *     WNBA: 2026 MVP                                    ->  Other 100%
 *     Massachusetts Governor Republican Primary Winner  ->  Candidate Z 100%
 *     Which club will Cristiano Ronaldo play for next?  ->  Team B 100%
 *     Fed decisions (Jun-Sep)                           ->  Other 51%    (9-way)
 *
 *     dominant field row leading      181
 *     anonymized reserved slot         505
 *     sub-threshold field at plurality   9
 *     ---------------------------------------
 *                                      695   (3.24% of browse)
 *
 * ═══ WHY THIS CARD IS THE WORST PLACE FOR IT ═══
 *
 * `CompactMarketCard` reads `market.top_outcomes[0]` and NOTHING else. There is
 * no list here for a bad row to sit at the end of, and no second line to correct
 * it. Whatever the API puts in position 0 IS the market's entire description.
 * "Massachusetts Governor Republican Primary Winner — Candidate Z 100%" is the
 * whole card.
 *
 * ═══ WHY BROWSE HAD THE BUG AT ALL ═══
 *
 * It was the FOURTH divergent copy of the display rules — the one
 * `app/utils/outcome_display.py`'s docstring was written to prevent. It filtered
 * only the legacy `player AB` regex, then sorted raw. The directive that handed
 * this over pointed at `_format_market_summary` instead; that helper serves
 * `GET /api/futures`, which has no frontend or iOS consumer at all. Browse
 * inlines its own copy, and browse is the one with a reader.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * The SHIPPED `CompactMarketCard` from `components/CategoryBrowser.tsx`, which
 * `app/search/page.tsx:353` renders, with the app's own compiled stylesheet.
 * Neither payload is hand-written: `backend/tests/fixtures/uxp165_browse_leaders.json`
 * holds the real `futures_outcomes` rows for both markets, and its `before` block
 * is byte-equal to what production served (checked against the live sweep).
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=browseLeaderCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works, same as the sibling capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { CompactMarketCard } from "../../components/CategoryBrowser";
import type { FuturesBrowseItem } from "../../lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp165_browse_leaders.json",
);

type Row = { id: number; name: string; probability: number | null; movement: number | null };
type Arm = { top_outcomes: Row[]; outcome_count: number };
type Spec = {
  id: number;
  name: string;
  llm_sport_category: string;
  before: Arm;
  after: Arm;
};

const fixture: { _source: string; markets: Spec[] } = JSON.parse(
  fs.readFileSync(FIXTURE, "utf8"),
);

const spec = (id: number): Spec => {
  const found = fixture.markets.find((m) => m.id === id);
  if (!found) throw new Error(`fixture is missing market ${id}`);
  return found;
};

const FEDEX = spec(10853985);
const MASS_GOV = spec(113738);

/** The app's own compiled stylesheet, so the panels look like the product. */
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

function asBrowseItem(s: Spec, arm: "before" | "after"): FuturesBrowseItem {
  return {
    id: s.id,
    name: s.name,
    llm_sport_category: s.llm_sport_category,
    source: "polymarket",
    resolution_date: null,
    top_outcomes: s[arm].top_outcomes,
    outcome_count: s[arm].outcome_count,
  };
}

function renderCard(s: Spec, arm: "before" | "after"): string {
  return renderToStaticMarkup(<CompactMarketCard market={asBrowseItem(s, arm)} />);
}

/**
 * `renderToStaticMarkup` HTML-escapes, and the extractor must undo that before
 * reading copy back (UX-P046's `&lt;1%` sentinel trap, inherited).
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

describe("UX-P165 — the category browser stops describing markets by an unrankable row", () => {
  it("the fixture reproduces what production served", () => {
    expect(FEDEX.before.top_outcomes[0].name).toBe("Other");
    expect(FEDEX.before.top_outcomes[0].probability).toBe(1.0);
    expect(MASS_GOV.before.top_outcomes[0].name).toBe("Candidate Z");
    expect(MASS_GOV.before.top_outcomes[0].probability).toBe(1.0);
  });

  it("BEFORE: the shipped card describes a golf major by 'Other 100%'", () => {
    const text = visibleText(renderCard(FEDEX, "before"));
    expect(text).toContain("FedEx Cup Playoffs: Winner");
    expect(text).toContain("Other");
    expect(text).toMatch(/100\s*%/);
  });

  it("BEFORE: the shipped card describes a governor's primary by 'Candidate Z 100%'", () => {
    const text = visibleText(renderCard(MASS_GOV, "before"));
    expect(text).toContain("Candidate Z");
    expect(text).toMatch(/100\s*%/);
  });

  it("AFTER: the golf card leads with the real favourite at his book price", () => {
    const text = visibleText(renderCard(FEDEX, "after"));
    expect(text).toContain("Scottie Scheffler");
    expect(text).toMatch(/23\s*%/);
    expect(text).not.toContain("Other");
    expect(text).not.toMatch(/100\s*%/);
  });

  it("AFTER: the primary card leads with a named candidate", () => {
    const text = visibleText(renderCard(MASS_GOV, "after"));
    expect(text).toContain("Michael Minogue");
    expect(text).toMatch(/98\s*%/);
    expect(text).not.toContain("Candidate");
  });

  it("AFTER: the outcome-count badge stops counting rows the card cannot show", () => {
    // 30 raw rows, 26 of them anonymized slots. "30" was never a number a reader
    // could act on; 4 is.
    expect(MASS_GOV.before.outcome_count).toBe(30);
    expect(MASS_GOV.after.outcome_count).toBe(4);
    expect(visibleText(renderCard(MASS_GOV, "after"))).toContain("4");
  });

  it("AFTER: a market with no placeholders keeps its full count", () => {
    // FedEx loses "Other" from the served top-3 but not from the count — the drop
    // is a display rule about position 0, not a claim about market size.
    expect(FEDEX.after.outcome_count).toBe(31);
  });

  it("the card renders only position 0, which is why position 0 is the whole fix", () => {
    // Guards the premise this queue is built on. If the card ever starts showing
    // more than the leader, the reasoning in this file needs revisiting.
    const text = visibleText(renderCard(FEDEX, "after"));
    expect(text).toContain("Scottie Scheffler");
    expect(text).not.toContain("Chris Gotterup");
    expect(text).not.toContain("Collin Morikawa");
  });

  it("writes the capture artifact when asked", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) return;
    const panel = (title: string, note: string, html: string) => `
      <section class="panel">
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="card-frame">${html}</div>
      </section>`;
    const doc = `<!doctype html><meta charset="utf-8">
<title>UX-P165 — the category browser stops describing markets by an unrankable row</title>
<style>${appStylesheet()}
  body{font:14px/1.5 -apple-system,system-ui,sans-serif;background:#f6f7f9;margin:0;padding:32px;color:#111}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#555;margin:0 0 24px}
  .cols{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:1100px}
  .panel{background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:16px}
  h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 4px;color:#666}
  .note{font-size:12px;color:#777;margin:0 0 12px}
  .card-frame{border:1px dashed #d8dce1;border-radius:10px;padding:6px}
  .stat{max-width:1100px;margin:24px 0 0;font-size:13px;color:#444}
  code{background:#f0f2f4;padding:1px 4px;border-radius:4px}
</style>
<h1>UX-P165 — the /search category browser stops printing “Other 100%” and “Candidate Z 100%”</h1>
<p class="sub">Both panels are the shipped <code>CompactMarketCard</code>
(<code>components/CategoryBrowser.tsx</code>, rendered by <code>app/search/page.tsx:353</code>)
with the app’s compiled stylesheet. Payloads come from the real
<code>futures_outcomes</code> rows; the BEFORE arms are byte-equal to what production served
on 2026-08-29.</p>
<div class="cols">
${panel("BEFORE — FedEx Cup Playoffs", "A no-bid ask (bid 0.0000 / ask 1.0000) describes a golf major.", renderCard(FEDEX, "before"))}
${panel("AFTER — FedEx Cup Playoffs", "The real favourite, at his untouched book price.", renderCard(FEDEX, "after"))}
${panel("BEFORE — Massachusetts Governor Republican Primary", "26 of 30 rows are anonymized slots priced 1.0. One of them is the card.", renderCard(MASS_GOV, "before"))}
${panel("AFTER — Massachusetts Governor Republican Primary", "A named candidate, and a count of 4 instead of 30.", renderCard(MASS_GOV, "after"))}
</div>
<p class="stat">Measured over <strong>all 21,441</strong> markets the browse endpoint serves
(100% sweep, 2026-08-29): <strong>695 cards</strong> — 3.24% — led with an outcome the reader
cannot act on. 181 a dominant field row, 505 an anonymized reserved slot, 9 a sub-threshold
field outcome at plurality.</p>`;
    fs.mkdirSync(dir, { recursive: true });
    const out = path.join(dir, "ux-p165-browse-leader.html");
    fs.writeFileSync(out, doc);
    expect(fs.statSync(out).size).toBeGreaterThan(1000);
  });
});
