/**
 * #9401 — a market whose title names one of its own DATE legs headlines that
 * leg, not the price leader.
 *
 * Production 2026-09-28 16:0xZ, 390px, Discover page one, the Middle East
 * bundle, row 5, verbatim:
 *
 *     Will Iran target an Arab country by September 30, 2026?
 *     October 31 · Resolves within a week                       64%
 *
 * The 64% is the October 31 leg. The September 30 leg (the date the title asks
 * about) traded at 28.5%, served `rendered_percent: 29`.
 *
 * The fixture is that bundle, verbatim (`fixtures/heroTitleDateLeg9401.json`).
 * The render arm goes through the real entry point:
 * `DiscoverCard -> ThemeBundleCard -> FuturesCompactRow`.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import fixture from "../fixtures/heroTitleDateLeg9401.json";

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

function bundle(): FeedItem {
  const item = JSON.parse(JSON.stringify(fixture.middle_east)) as FeedItem;
  // #9642: a collapsed bundle now seats three rows (selected design A), and the
  // specimen was row 5 — behind "All N questions". Hoist the two rows under test
  // into the peek so the render arms still go through the real entry point; the
  // members themselves stay verbatim.
  const data = item.data as unknown as FeedBundleData;
  const members = data.items as unknown as FeedItem[];
  const underTest = (m: FeedItem) => [ARAB, IRAQ].includes((m.data as FeedFuturesData).name);
  (data as unknown as { items: FeedItem[] }).items = [...members.filter(underTest), ...members.filter((m) => !underTest(m))];
  return item;
}

function member(item: FeedItem, id: number): FeedFuturesData {
  const items = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
  const found = items.find((m) => (m.data as FeedFuturesData).id === id);
  if (!found) throw new Error(`member ${id} not in fixture`);
  return found.data as FeedFuturesData;
}

/** The text of the rendered row whose title is `title`, tags stripped. */
function rowText(html: string, title: string): string {
  const text = html.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/\s+/g, " ");
  const at = text.indexOf(title);
  if (at < 0) throw new Error(`row "${title}" not rendered`);
  return text.slice(at, at + title.length + 80);
}

const ARAB = "Will Iran target an Arab country by September 30, 2026?";
const IRAQ = "Will Iran target Iraq?";

describe("#9401 — the hero is the date leg the title names", () => {
  it("the fixture still carries the defect's shape (price leader is NOT the named leg)", () => {
    const data = member(bundle(), 60634731);
    expect(data.name).toBe(ARAB);
    expect(data.top_outcomes?.[0]?.name).toBe("October 31");
    expect(data.top_outcomes?.map((o) => o.name)).toContain("September 30");
  });

  it("heroOutcome picks the September 30 leg when told the title", () => {
    const data = member(bundle(), 60634731);
    expect(heroOutcome(data.top_outcomes, data.name)?.name).toBe("September 30");
    // Strawman: without the title the old answer comes back.
    expect(heroOutcome(data.top_outcomes)?.name).toBe("October 31");
  });

  it("the rendered row prints 29%, not 64%", () => {
    const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: bundle() }} positionIndex={0} />);
    const row = rowText(html, ARAB);
    expect(row).toMatch(/29%/);
    expect(row).not.toMatch(/64%/);
    expect(row).not.toMatch(/October 31/);
  });

  it("CONTROL: a title with no date keeps the served leader (Iraq row, October 31 · 65%)", () => {
    const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item: bundle() }} positionIndex={0} />);
    const row = rowText(html, IRAQ);
    expect(row).toMatch(/October 31/);
    expect(row).toMatch(/65%/);
  });
});

describe("#9401 — what the title rule refuses", () => {
  const legs = [
    { name: "October 31", probability: 0.635 },
    { name: "September 30", probability: 0.285 },
    { name: "September 15", probability: 0.089 },
  ];

  it("accepts a trailing year on the outcome and an abbreviated month in the title", () => {
    const withYear = [{ name: "October 31", probability: 0.6 }, { name: "Sep 30, 2026", probability: 0.3 }];
    expect(heroOutcome(withYear, "Will X happen before Sept. 30?")?.name).toBe("Sep 30, 2026");
  });

  it("needs a deadline preposition: a date elsewhere in the title does not count", () => {
    expect(heroOutcome(legs, "#1 Free App on September 30?")?.name).toBe("October 31");
  });

  it("the day must match, not just the month", () => {
    expect(heroOutcome(legs, "Will X happen by September 3?")?.name).toBe("October 31");
  });

  it("two legs reading the same date is not resolvable — served leader stays", () => {
    const twin = [...legs, { name: "September 30", probability: 0.3 }];
    expect(heroOutcome(twin, "by September 30?")?.name).toBe("October 31");
  });

  it("an unpriced named leg keeps the served leader", () => {
    const unpriced = [legs[0], { name: "September 30", probability: null }];
    expect(heroOutcome(unpriced, "by September 30?")?.name).toBe("October 31");
  });

  it("an outcome that merely STARTS with the date is not the date", () => {
    const worded = [{ name: "No", probability: 0.88 }, { name: "September 30 or later", probability: 0.12 }];
    expect(heroOutcome(worded, "by September 30?")?.name).toBe("No");
  });

  it("the UX-P238 negation swap still works with a title passed", () => {
    const pair = [{ name: "No", probability: 0.88 }, { name: "Yes", probability: 0.12 }];
    expect(heroOutcome(pair, "Houthis enter Aden by October 31, 2026?")?.name).toBe("Yes");
  });
});
