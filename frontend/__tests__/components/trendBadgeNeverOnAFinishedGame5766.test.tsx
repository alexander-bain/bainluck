// #5766 — A FINISHED GAME NEVER WEARS THE "🔥 TRENDING" FLAME.
//
// MEASURED ON PRODUCTION 2026-09-12 22:05Z, Discover page one at 390px. A DOM
// probe over `[data-trend-placement]` found 16 trend badges on the page. The
// only two sitting on a card whose body reads `Final` were the two finished
// games seated at slots 10 and 11:
//
//   🔥 TRENDING  ⚾ MLB   3 Final 4  Pittsburgh Pirates @ Chicago Cubs   ei 100
//   🔥 TRENDING  ⚽ LIGA  1 Final 1  Elche CF @ Athletic Bilbao          ei  70
//
// Those are the whole of the hourly bus's "Discover: 2 dead / 20". They are on
// the page deliberately (D118 = B, #4681 admission, #5100 placement); what was
// wrong is that they were dressed as live.
//
// WHY THE FIX IS IN THE PREDICATE AND NOT IN THE CARD. `_recent_marquee_final_ids`
// picks the finals it seats by EI RANK, and `isTrending`'s event arm fired on
// `ei.score >= 70` with no status test. The seating arm therefore selects, by
// construction, exactly the cards the badge arm calls trending — so every future
// seated final would wear the flame too. The two specimens below are the real
// production `ei` readings, and the second one is the boundary value.
//
// BOTH DIRECTIONS (gotcha #43): the settled card loses the flame AND the live /
// high-EI-scheduled cards are asserted to keep it, so a fix that simply stopped
// rendering trend badges on event cards fails here.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem, FeedEventData } from "@/lib/types";

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

import DiscoverCard from "../../components/DiscoverCard";
import { isTrending } from "../../components/discover/utils";

/** The served shape of the two seated finals, trimmed to the fields in play. */
function eventItem(
  dataOverrides: Partial<FeedEventData>,
  itemOverrides: Partial<FeedItem> = {},
): FeedItem {
  return {
    type: "event",
    headline: null,
    reason: "",
    context_summary: null,
    score: 68,
    data: {
      id: 15310365,
      status: "completed",
      commence_time: "2026-09-12T18:20:00Z",
      away_team: "Pittsburgh Pirates",
      home_team: "Chicago Cubs",
      away_score: 3,
      home_score: 4,
      sport: "baseball_mlb",
      sport_name: "MLB",
      ei: { score: 100, label: "Incredible" },
      home_team_data: { team_id: 10714, abbreviation: "CHC" },
      away_team_data: { team_id: 10715, abbreviation: "PIT" },
      ...dataOverrides,
    } as unknown as FeedEventData,
    ...itemOverrides,
  } as unknown as FeedItem;
}

/** Pittsburgh Pirates @ Chicago Cubs, 3-4 final, `ei.score` 100. */
const CUBS_FINAL = eventItem({});

/** Elche CF @ Athletic Bilbao, 1-1 final, `ei.score` 70 — the boundary. */
const LIGA_FINAL = eventItem({
  id: 15298237,
  status: "completed",
  commence_time: "2026-09-12T16:30:00Z",
  away_team: "Elche CF",
  home_team: "Athletic Bilbao",
  away_score: 1,
  home_score: 1,
  sport: "soccer_spain_la_liga",
  sport_name: "La Liga - Spain",
  ei: { score: 70, label: "Engaging" },
});

function render(item: FeedItem): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item }} />,
  );
}

/** The badge's own marker, not the emoji — `TrendBadge` stamps it in both placements. */
function hasTrendBadge(html: string): boolean {
  return html.includes('data-trend-placement');
}

describe("#5766 — the trend badge on a settled Discover event card", () => {
  it("is gone from the MLB final the bus counted dead, EI 100 and all", () => {
    expect(isTrending(CUBS_FINAL)).toBe(false);
    expect(hasTrendBadge(render(CUBS_FINAL))).toBe(false);
  });

  it("is gone from the La Liga final sitting exactly on the EI threshold", () => {
    expect(isTrending(LIGA_FINAL)).toBe(false);
    expect(hasTrendBadge(render(LIGA_FINAL))).toBe(false);
  });

  it("is gone from a `closed` event too, not only a `completed` one", () => {
    // The two settled statuses travel together everywhere else in this module
    // (`eventIsSettled`), and a predicate that knew only one of them would be
    // the drift this file keeps paying for.
    const closed = eventItem({ status: "closed" });

    expect(isTrending(closed)).toBe(false);
    expect(hasTrendBadge(render(closed))).toBe(false);
  });

  it("still fires on the live game the badge exists for, at a LOW EI", () => {
    // The `status === "live"` arm, isolated: EI 10 is far below the threshold,
    // so this can only pass through the live arm. A fix that stopped rendering
    // the badge on event cards at all fails here.
    const live = eventItem({ status: "live", ei: { score: 10, label: "Quiet" } });

    expect(isTrending(live)).toBe(true);
    expect(hasTrendBadge(render(live))).toBe(true);
  });

  it("still fires on an unstarted game carried by EI alone", () => {
    // The EI arm, isolated from the live arm: scheduled, EI 70. This is the arm
    // the fix narrows, and narrowing it any further than "settled" breaks here.
    const scheduled = eventItem({
      status: "scheduled",
      away_score: null,
      home_score: null,
      ei: { score: 70, label: "Engaging" },
    });

    expect(isTrending(scheduled)).toBe(true);
    expect(hasTrendBadge(render(scheduled))).toBe(true);
  });

  it("leaves a scheduled game below the EI threshold alone, as before", () => {
    const quiet = eventItem({
      status: "scheduled",
      away_score: null,
      home_score: null,
      ei: { score: 69, label: "Quiet" },
    });

    expect(isTrending(quiet)).toBe(false);
    expect(hasTrendBadge(render(quiet))).toBe(false);
  });
});
