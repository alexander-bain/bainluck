/**
 * #4396 — A BUNDLE ROW'S PERCENTAGE SAYS WHICH ANSWER IT BELONGS TO.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Page one at 390px, 2026-09-09 09:35 PT, edition `b433c96f31941ab7`, inside
 * the FED & RATES bundle:
 *
 *     Fed decision in Sep 2026?                        56%
 *       Hike 25bps leads at 56%
 *     How many Fed rate cuts in 2026?                  93%
 *       Well off its opening price
 *     How many dissent at the October Fed meeting?     25%
 *       As central banks grapple with rising inflation and economic…
 *
 * The 93% is the probability of `0 (0 bps)` — that there are NO cuts in 2026 —
 * and the row never says so. A reader scanning that line reads a confident yes
 * to a question whose answer is *none*. The first row is fine, and shows why:
 * its caption happens to be a leader sentence. The other two got a movement
 * line and a paragraph of hook prose — captions that fill the line and name no
 * answer — and their numbers were left speaking for no one.
 *
 * ── THE SPECIMEN IS THE SERVED OBJECT ───────────────────────────────────────
 *
 * `__tests__/fixtures/compactRowAnswer4396.json` is that bundle exactly as
 * `GET /api/feed?limit=250` returned it, member prices and captions untouched,
 * plus the 22-row census of every compact row the same response served.
 *
 * ── WHY IT ENTERS AT `DiscoverCard` ─────────────────────────────────────────
 *
 * The claim is about what a reader sees on page one, and page one routes a
 * bundle through `DiscoverCard -> ThemeBundleCard -> FuturesCompactRow`.
 * Handing a hand-built row straight to `FuturesCompactRow` would prove the
 * component and not the path — and this row is reached only in the COLLAPSED
 * bundle, which is the state the reader lands on.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. the orphaned 93% now names `0 (0 bps)`, and the orphaned 25% names `3`;
 *  2. CONTROL — the sibling row whose caption already said "Hike 25bps leads
 *     at 56%" does not print "Hike 25bps" twice;
 *  3. CONTROL — the why-now survives: "Well off its opening price" is still on
 *     the row that gained a label, so the fix added a fact and displaced none;
 *  4. the label is read off the payload, not held here: repricing the bundle so
 *     a different outcome leads moves the printed answer;
 *  5. CONTROL — a bare `Yes` hero on a question that states the affirmative
 *     stays as it is, so this cannot be passed by labelling everything.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedItem } from "@/lib/types";
import fixture from "../fixtures/compactRowAnswer4396.json";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";

/** The served FED & RATES bundle, deep-copied so an arm cannot leak into the next. */
function fedBundle(): FeedItem {
  return JSON.parse(JSON.stringify(fixture.bundle)) as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
}

/**
 * The text a reader sees in `fragment` — every run of characters that sits
 * outside a tag, concatenated.
 *
 * 🔴 NOT `replace(/<[^>]+>/g, "")`. That is the shape of an HTML sanitizer, and
 * CodeQL rules it a high-severity `js/incomplete-multi-character-sanitization`
 * (alert 2267 on this branch's first sha, `9dccfc26`) — correctly, in the sense
 * that the pattern is unsafe wherever the output is trusted. Here it never is,
 * but a standing gate refusal is not something to argue with in a test helper.
 * Walking `<`/`>` by index is the same reading with nothing sanitizer-shaped in
 * it. No entity decoding: `renderToStaticMarkup` escapes only `& < > " '`, and
 * none of the captions asserted below contain one.
 */
function visibleText(fragment: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const open = fragment.indexOf("<", i);
    out += open < 0 ? fragment.slice(i) : fragment.slice(i, open);
    if (open < 0) break;
    const close = fragment.indexOf(">", open);
    if (close < 0) break;
    i = close + 1;
  }
  return out.split(/\s+/).filter(Boolean).join(" ");
}

/** The caption block of the row whose question is `question`. */
function captionFor(html: string, question: string): string {
  const at = html.indexOf(question);
  if (at < 0) throw new Error(`the render never printed the row "${question}"`);
  // Each row is one `<a>`; the caption is the next caption div inside it.
  const rest = html.slice(at);
  const openedAt = rest.indexOf('data-testid="compact-row-caption"');
  if (openedAt < 0) return "";
  const from = rest.indexOf(">", openedAt) + 1;
  const to = rest.indexOf("</div>", from);
  return visibleText(rest.slice(from, to));
}

const CUTS = "How many Fed rate cuts in 2026?";
const DISSENT = "How many dissent at the October Fed meeting?";
const DECISION = "Fed decision in Sep 2026?";

describe("#4396 — the compact row names the answer its percentage is for", () => {
  it("is rendering the real served bundle, collapsed, with all three rows", () => {
    // A fixture that lost its members would make every arm below vacuous.
    const html = render(fedBundle());
    expect(html).toContain(CUTS);
    expect(html).toContain(DISSENT);
    expect(html).toContain(DECISION);
    expect(html).toContain("93%");
  });

  it("names `0 (0 bps)` on the 93% that a reader read as a yes", () => {
    expect(captionFor(render(fedBundle()), CUTS)).toContain("0 (0 bps)");
  });

  it("names `3` on the row whose caption is hook prose that answers nothing", () => {
    // `feedContextSnippet` falls through to `hook_description` here, so this
    // row's line is full and still says nothing about which answer is at 25%.
    const caption = captionFor(render(fedBundle()), DISSENT);
    expect(caption).toMatch(/^3 · As central banks grapple/);
  });

  it("CONTROL — the row whose caption already named its answer does not say it twice", () => {
    const caption = captionFor(render(fedBundle()), DECISION);
    expect(caption).toBe("Hike 25bps leads at 56%");
    expect(caption.match(/Hike 25bps/g)).toHaveLength(1);
  });

  it("CONTROL — the why-now survives beside the answer it now sits next to", () => {
    const caption = captionFor(render(fedBundle()), CUTS);
    expect(caption).toContain("Well off its opening price");
    expect(caption).toBe("0 (0 bps) · Well off its opening price");
  });

  it("reads the answer off the payload rather than holding one of its own", () => {
    const item = fedBundle();
    const members = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
    const cuts = members.find((m) => (m.data as { name: string }).name === CUTS)!;
    const outcomes = (cuts.data as unknown as { top_outcomes: { name: string; probability: number }[] }).top_outcomes;
    // The market reprices: two cuts becomes the leader.
    outcomes[0].probability = 0.05;
    outcomes[1].probability = 0.06;
    outcomes.sort((a, b) => b.probability - a.probability);

    const caption = captionFor(render(item), CUTS);
    expect(caption).toContain(outcomes[0].name);
    expect(caption).not.toContain("0 (0 bps)");
  });

  it("CONTROL — a bare `Yes` hero is left alone, because the question already states it", () => {
    const item = fedBundle();
    const members = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
    const cuts = members.find((m) => (m.data as { name: string }).name === CUTS)!;
    const cutsData = cuts.data as unknown as { name: string; top_outcomes: { name: string; probability: number }[] };
    // The shape of the three geopolitics rows in the same census.
    cutsData.name = "Will the U.S. invade Iran before 2027?";
    cutsData.top_outcomes = [
      { name: "Yes", probability: 0.12 },
      { name: "No", probability: 0.88 },
    ];

    const caption = captionFor(render(item), "Will the U.S. invade Iran before 2027?");
    expect(caption).toBe("Well off its opening price");
  });
});
