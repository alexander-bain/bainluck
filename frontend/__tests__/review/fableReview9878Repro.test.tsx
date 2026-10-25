/**
 * Regression suite for Fable's independent review findings on #9878 / #11040 (v4).
 *
 * Converts all 6 frontend reproductions from `fable-review-movement-story-slice1-v3-20261024`
 * (`B1`, `B4`, `B3`, `B6`, `B7`, `N1`) into required-behavior regression tests
 * exercising the real production mount path (`DiscoverCard -> ThemeBundleCard -> DeadlineFamilyCard`).
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) =>
      ReactLib.createElement("a", { href, ...rest }, children),
  };
});
jest.mock("next/image", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ alt }: { alt: string }) => ReactLib.createElement("img", { alt }) };
});
jest.mock("@/lib/analytics", () => ({ __esModule: true, trackEvent: () => {} }));
jest.mock("@/components/Analytics", () => ({ __esModule: true, useAnalyticsContext: () => ({ track: () => {} }) }));

import DiscoverCard from "../../components/DiscoverCard";
import { MovementBadge } from "../../components/discover/shared";
import {
  buildDeadlineFamilyCardModel,
  validateAndBuildDeadlineFamilyCardModel,
} from "../../lib/discover/deadlineFamilyCard";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "../../lib/types";

const DEFAULT_FROZEN_SCENARIOS_DIR =
  "/Users/bain/.gemini/antigravity/brain/e9c17473-1c3f-435c-9dbb-a744b792aa74/scratch/fable-review-movement-story-slice1-v3-20261024/evidence/scenarios";
const DIR = process.env.REVIEW_SCENARIOS_DIR || DEFAULT_FROZEN_SCENARIOS_DIR;

const scenario = (name: string, dir: string = DIR): FeedItem[] =>
  JSON.parse(fs.readFileSync(path.join(dir, `${name}.json`), "utf8")).displayed;
const bundleOf = (items: FeedItem[]) => items.find((i) => i.type === "bundle")!;
const mount = (item: FeedItem, props: { nowIso?: string; timeZone?: string } = {}) =>
  renderToStaticMarkup(
    <DiscoverCard
      groupedItem={{ type: "single", item }}
      positionIndex={0}
      nowIso={props.nowIso}
      timeZone={props.timeZone}
    />,
  );
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
const asInput = (b: FeedItem) => {
  const d = b.data as FeedBundleData;
  return {
    items: d.items,
    title: d.title,
    sharedQuestion: d.shared_question,
    storyKey: d.story_key,
    deadlineFamily: d.deadline_family,
  };
};

describe("B1 — a folded family never disappears when the specialized consumer rejects it", () => {
  it("Q8e & time-advancement fallback: consumer-rejected bundle falls back to generic ThemeBundleCard preserving members and links", () => {
    const served = scenario("Q8e_backend_admits_consumer_refuses");
    expect(served).toHaveLength(1);
    expect(served[0].type).toBe("bundle");
    expect((served[0].data as FeedBundleData).member_ids).toHaveLength(2);

    // Consumer rejects specialized model because `observed - basis` is 11.5h (< 12h min):
    const validation = validateAndBuildDeadlineFamilyCardModel(asInput(served[0]), {
      nowIso: "2026-10-14T23:51:09Z",
      timeZone: "America/Los_Angeles",
    });
    expect(validation.model).toBeNull();
    expect(validation.rejectionReason).toBe("no_eligible_open_priced_member");

    // Mounted through the production path (`DiscoverCard -> ThemeBundleCard`), it renders
    // the generic ThemeBundleCard fallback instead of disappearing:
    const html = mount(served[0], {
      nowIso: "2026-10-14T23:51:09Z",
      timeZone: "America/Los_Angeles",
    });
    expect(text(html)).not.toBe("");
    expect(html).not.toContain('data-testid="deadline-family-card"');
    expect(text(html)).toContain("Katie Zacharia out as Press Secretary");
    expect(text(html)).toContain("Katie Zacharia out as Press Secretary by October 31?");
    expect(text(html)).toContain("Katie Zacharia out as Press Secretary by December 31?");
    expect(html).toContain('href="/futures/2"');
    expect(html).toContain('href="/futures/3"');

    // Also verify live transition when time advances past the 24h basis window on a mounted Q8a family:
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-10-14T23:51:09Z"));
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
      const q8aBundle = bundleOf(scenario("Q8a_family_near_certain"));
      type El = {
        textContent?: string;
        childNodes: El[];
        [k: string]: unknown;
      };
      const descendants = (node: El): El[] => [
        node,
        ...Array.from(node.childNodes ?? []).flatMap((n) => descendants(n as El)),
      ];
      act(() => {
        root.render(<DiscoverCard groupedItem={{ type: "single", item: q8aBundle }} positionIndex={0} />);
      });
      expect(
        descendants(container as unknown as El).some(
          (el) => el["data-testid"] === "deadline-family-card",
        ),
      ).toBe(true);

      // Advance clock by 12 hours so the 19.3h-old basis ages to 31.3h (> 24h window):
      act(() => {
        jest.setSystemTime(new Date("2026-10-15T11:51:09Z"));
        jest.advanceTimersByTime(60_000);
      });
      const afterNodes = descendants(container as unknown as El);
      expect(
        afterNodes.some((el) => el["data-testid"] === "deadline-family-card"),
      ).toBe(false);
      expect(container.textContent).toContain("Katie Zacharia out as Press Secretary by October 31?");
      expect(container.textContent).toContain("Katie Zacharia out as Press Secretary by December 31?");
      const hrefs = afterNodes
        .map((el) => el["href"])
        .filter((h): h is string => typeof h === "string");
      expect(hrefs).toContain("/futures/2");
      expect(hrefs).toContain("/futures/3");
    } finally {
      act(() => {
        root.unmount();
      });
      document.body.removeChild(container);
      jest.useRealTimers();
    }
  });
});

describe("B4 — the production mount wires the reader's clock and timezone", () => {
  it("F1: PT reader at 12:15 AM Oct 15 sees 'since Oct 14' through the actual DiscoverCard mount (including accessible text)", () => {
    const b = bundleOf(scenario("F1_reader_midnight"));
    jest.useFakeTimers().setSystemTime(new Date("2026-10-15T07:15:00Z"));
    try {
      // Production builder without explicit `nowIso` reads `Date.now()`:
      const prod = buildDeadlineFamilyCardModel(asInput(b), { timeZone: "America/Los_Angeles" })!;
      expect(prod.representative.heroTimeframeText).toBe("since Oct 14");
      expect(prod.representative.narrativeCaption).toBe(
        "Down 6.5 points since Oct 14 — 24% chance by Dec 31",
      );
      expect(prod.representative.accessibleLabel).toContain(
        "Down 6.5 points since Oct 14",
      );

      // Actual production mount (`DiscoverCard -> ThemeBundleCard -> DeadlineFamilyCard`):
      const mountedHtml = mount(b, { timeZone: "America/Los_Angeles" });
      expect(mountedHtml).toContain("since Oct 14");
      expect(mountedHtml).toContain("Down 6.5 points since Oct 14 — 24% chance by Dec 31");
      expect(mountedHtml).not.toContain("today since 12:30 AM");
      expect(mountedHtml).toContain(
        'aria-label="Down 6.5 points since Oct 14"',
      );

      const src = fs.readFileSync(path.join(__dirname, "../../components/DiscoverCard.tsx"), "utf8");
      const call = src.slice(src.indexOf("<ThemeBundleCard"), src.indexOf("/>", src.indexOf("<ThemeBundleCard")));
      expect(call).toMatch(/nowIso/);
      expect(call).toMatch(/timeZone/);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("B3 — Q8 is scoped strictly to >=97% of a verified family and respects the 5% movement floor", () => {
  it("Q8d: a <=5% leg never shows a hero movement chip or row badge; hero and row agree", () => {
    const b = bundleOf(scenario("Q8d_near_zero_exempted"));
    const m = buildDeadlineFamilyCardModel(asInput(b), {
      nowIso: "2026-10-14T23:51:09Z",
      timeZone: "America/Los_Angeles",
    })!;
    // Oct 31 is at 2% (<= 5% placeholder floor): its -5 pt move is suppressed on both hero and row,
    // so Dec 31 (24%, nearest 50%) is selected as the level-led representative.
    const oct = m.members.find((x) => x.deadlineLabel === "By Oct 31")!;
    expect(oct.yesPercentText).toBe("2%");
    expect(oct.isNearCertain).toBe(false);
    expect(oct.movementStatus).toBe("none");
    expect(oct.showHeroMovementChip).toBe(false);
    expect(oct.showRowMovementBadge).toBe(false);
    expect(renderToStaticMarkup(<MovementBadge m={oct.rowMovementFraction} prob={oct.yesProbability} />)).toBe("");

    expect(m.selectionReason).toBe("nearest_50_pct_fallback");
    expect(m.representative.deadlineLabel).toBe("By Dec 31");
    expect(m.representative.yesPercentText).toBe("24%");
    expect(m.representative.showHeroMovementChip).toBe(false);
  });
});

describe("B6 — the family card consumes live price updates from /api/feed/price-cards", () => {
  it("LIVE: projected member bodies from LIVE_price_cards update 24% / 7% to 32% / 15% and revalidate movement", () => {
    const b = bundleOf(scenario("LIVE_served"));
    const fresh = JSON.parse(fs.readFileSync(path.join(DIR, "LIVE_price_cards.json"), "utf8")).items as FeedItem[];
    const d = b.data as FeedBundleData;

    // Before live refresh: Dec 31 is 24% (-6.5 pts hero move) and Oct 31 is 7%.
    const before = buildDeadlineFamilyCardModel(asInput(b), {
      nowIso: "2026-10-14T23:51:09Z",
      timeZone: "America/Los_Angeles",
    })!;
    expect(before.members.find((x) => x.marketId === 3)!.yesPercentText).toBe("24%");
    expect(before.members.find((x) => x.marketId === 2)!.yesPercentText).toBe("7%");
    expect(before.representative.marketId).toBe(3);
    expect(before.representative.heroMovementChipText).toBe("↓ 6.5 pts");

    // Apply `projectPriceGroups`-style member body replacement from `LIVE_price_cards.json`:
    const projected: FeedItem = {
      ...b,
      data: {
        ...d,
        items: d.items.map((it) => ({
          ...it,
          data: {
            ...(fresh.find(
              (f) =>
                (f.data as { id?: number }).id ===
                (it.data as { id?: number }).id,
            )!.data),
          },
        })),
      },
    } as FeedItem;

    const after = buildDeadlineFamilyCardModel(asInput(projected), {
      nowIso: "2026-10-14T23:54:09Z",
      timeZone: "America/Los_Angeles",
    })!;
    const decAfter = after.members.find((x) => x.marketId === 3)!;
    const octAfter = after.members.find((x) => x.marketId === 2)!;
    expect(decAfter.yesPercentText).toBe("32%");
    expect(octAfter.yesPercentText).toBe("15%");

    // Dec 31 moved from 0.31 basis to 0.32 (+1.0 pt -> sub_threshold, never the obsolete -6.5 pts!);
    // Oct 31 moved from 0.084 basis to 0.15 (+6.6 pts -> hero mover) and becomes the new representative!
    expect(decAfter.movementStatus).toBe("sub_threshold");
    expect(decAfter.showHeroMovementChip).toBe(false);
    expect(after.representative.marketId).toBe(2);
    expect(after.representative.yesPercentText).toBe("15%");
    expect(after.representative.heroMovementChipText).toBe("↑ 6.6 pts");

    const mountedHtml = mount(projected, {
      nowIso: "2026-10-14T23:54:09Z",
      timeZone: "America/Los_Angeles",
    });
    expect(mountedHtml).toContain("15%");
    expect(mountedHtml).toContain("↑ 6.6 pts");
    expect(mountedHtml).not.toContain("↓ 6.5 pts");
  });
});

describe("B7 — stale numbers show the existing futures age mark and clear on fresh update", () => {
  it("F2 vs F2b: 8h-old representative draws PriceAgeMark (cadence='futures', '8h ago') and clears when refreshed", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-10-14T23:51:09Z"));
    try {
      const family = mount(bundleOf(scenario("F2_prices_8h_old")));
      const standalone = mount(scenario("F2b_prices_8h_old_family_refused")[0]);
      expect(standalone).toMatch(/data-cadence="futures"/);
      expect(text(standalone)).toMatch(/8h ago/);

      expect(family).toMatch(/data-cadence="futures"/);
      expect(text(family)).toMatch(/8h ago/);
      expect(text(family)).toMatch(/Last number:/);

      // After a fresh price update (`2026-10-14T23:53:09Z`), the age mark disappears:
      const freshFamily = mount(bundleOf(scenario("LIVE_served")));
      expect(freshFamily).not.toMatch(/data-testid="price-age-mark"/);
      expect(text(freshFamily)).not.toMatch(/8h ago/);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("N1 — expanded member row MovementBadge matches the reader-local timeframe", () => {
  it("D2: hero and expanded row MovementBadge both state the reader-local interval instead of 'in the last 24h'", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-10-14T23:51:09Z"));
    try {
      const b = bundleOf(scenario("D2_synthetic_hero_dec31"));
      const m = buildDeadlineFamilyCardModel(asInput(b), {
        nowIso: "2026-10-14T23:51:09Z",
        timeZone: "America/Los_Angeles",
      })!;
      expect(m.representative.heroMovementAriaLabel).toBe("Down 6.5 points since yesterday");
      expect(m.representative.movementTimeframeLabel).toBe("since yesterday");

      const badgeHtml = renderToStaticMarkup(
        <MovementBadge
          m={m.representative.rowMovementFraction}
          prob={m.representative.yesProbability}
          timeframeLabel={m.representative.movementTimeframeLabel}
        />,
      );
      expect(badgeHtml).toContain("Down 6.5 points since yesterday");
      expect(badgeHtml).not.toContain("in the last 24h");
    } finally {
      jest.useRealTimers();
    }
  });
});
