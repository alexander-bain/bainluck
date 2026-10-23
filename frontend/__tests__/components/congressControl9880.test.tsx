/**
 * Regression tests for the Congress control theme bundle and Option A two-sided
 * party row (#9880 / #9237 / #10354).
 *
 * Covers Acceptance Cases W1-W14 and Negative Controls N1-N2 from
 * FABLE-CONGRESS-GROUPING-HANDOFF.md / ACCEPTANCE-CASES.md and
 * CONGRESS-SCOPING-REVIEW.md.
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";

const mockTrackEvent = jest.fn();

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
      [k: string]: unknown;
    }) => ReactLib.createElement("a", { href, ...rest }, children),
  };
});

jest.mock("next/image", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ alt }: { alt: string }) => ReactLib.createElement("img", { alt }),
  };
});

jest.mock("@/lib/analytics", () => ({
  __esModule: true,
  trackEvent: (...args: unknown[]) => mockTrackEvent(...args),
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";
import { ThemeBundleCard } from "../../components/discover/ThemeBundleCard";
import { rememberThemeCollectionReturn } from "../../components/discover/shared";
import {
  PARTY_CONTROL_SLOT_COLORS,
  isCongressControlStoryKey,
  partyControlRowProps,
  stripVisiblePartyLeadClause,
} from "../../lib/discover/partyControlRow";

const store = new Map<string, string>();
beforeAll(() => {
  (globalThis as unknown as { sessionStorage: Storage }).sessionStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    get length() {
      return store.size;
    },
  } as Storage;
});

beforeEach(() => {
  store.clear();
  mockTrackEvent.mockClear();
});

const REAL_SENATE_ITEM: FeedItem = {
  type: "futures",
  score: 94,
  reason:
    "Democratic Party is up 26 points since Feb 18 in Which party will win the U.S. Senate?",
  headline: "Democratic Party leads at 66%, up 26 points since Feb 18",
  context_summary: "Democratic Party leads at 66%, up 26 points since Feb 18",
  data: {
    id: 108620,
    name: "Which party will win the U.S. Senate?",
    sport: null,
    sport_name: null,
    llm_sport_category: "politics",
    source: "kalshi",
    source_count: 2,
    sources: ["kalshi", "polymarket"],
    market_tier: 2,
    market_type: "duel",
    status: "open",
    resolution_date: "2027-02-01T15:00:00+00:00",
    price_observed_at: "2026-10-21T23:11:46+00:00",
    top_outcomes: [
      {
        id: 1593959,
        name: "Democratic Party",
        probability: 0.655,
        rank: 1,
        movement: null,
        rendered_percent: 66,
      },
      {
        id: 1593958,
        name: "Republican Party",
        probability: 0.335,
        rank: 2,
        movement: null,
        rendered_percent: 34,
      },
    ],
    card_sum_reason: null,
    outcome_count: 2,
    canonical_market_key: "politics:US:championship:2027",
    group_id: "kalshi:CONTROLS-2026",
    group_type: "kalshi_event",
    discover_card: {
      suggested_format: "binary_probability",
      bundle_candidate: false,
      comparison_theme: null,
      threshold_points: [],
      ladder_treatment_refused: false,
      field_is_a_race: true,
      distribution_outcomes: [
        { label: "Democratic Party", probability: 0.655, movement: null },
        { label: "Republican Party", probability: 0.335, movement: null },
      ],
      distribution_order: "probability",
      remaining_outcome_count: 0,
      qa_signals: ["multi_source_consistency_check"],
      public_source_disagreement: false,
      reasons: [],
    },
  } as unknown as FeedFuturesData,
};

const REAL_HOUSE_ITEM: FeedItem = {
  type: "futures",
  score: 92,
  reason:
    "Democratic Party is up 13.7 points since Feb 18 in Which party will win the U.S. House?",
  headline: "Democratic Party leads at 91%, up 13.7 points since Feb 18",
  context_summary: "Democratic Party leads at 91%, up 13.7 points since Feb 18",
  data: {
    id: 108621,
    name: "Which party will win the U.S. House?",
    sport: null,
    sport_name: null,
    llm_sport_category: "politics",
    source: "kalshi",
    source_count: 1,
    sources: ["kalshi"],
    market_tier: 2,
    market_type: "duel",
    status: "open",
    resolution_date: "2027-02-01T15:00:00+00:00",
    price_observed_at: "2026-10-21T23:11:47+00:00",
    top_outcomes: [
      {
        id: 1593960,
        name: "Democratic Party",
        probability: 0.9125,
        rank: 1,
        movement: null,
        rendered_percent: 91,
      },
      {
        id: 1593961,
        name: "Republican Party",
        probability: 0.0875,
        rank: 2,
        movement: null,
        rendered_percent: 9,
      },
    ],
    card_sum_reason: null,
    outcome_count: 2,
    canonical_market_key: "politics::championship:2027",
    group_id: "kalshi:CONTROLH-2026",
    group_type: "kalshi_event",
    discover_card: {
      suggested_format: "binary_probability",
      bundle_candidate: false,
      comparison_theme: null,
      threshold_points: [],
      ladder_treatment_refused: false,
      field_is_a_race: true,
      distribution_outcomes: [
        { label: "Democratic Party", probability: 0.9125, movement: null },
        { label: "Republican Party", probability: 0.0875, movement: null },
      ],
      distribution_order: "probability",
      remaining_outcome_count: 0,
      qa_signals: [],
      public_source_disagreement: false,
      reasons: [],
    },
  } as unknown as FeedFuturesData,
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function makeCongressBundleItem(members: FeedItem[]): FeedItem {
  return {
    type: "bundle",
    score: 94,
    reason: "Who wins control of Congress?",
    headline: "Congress",
    data: {
      id: "theme:story:us_congress_control:2026:108620-108621",
      title: "Congress",
      kind: "theme",
      story_key: "story:us_congress_control:2026",
      shared_question: "Who wins control of Congress?",
      item_count: members.length,
      member_ids: members.map((m) => (m.data as FeedFuturesData).id),
      items: members,
    } as FeedBundleData,
  };
}

function renderBundle(item: FeedItem): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
  );
}

type El = {
  tagName?: string;
  textContent?: string;
  childNodes: El[];
  [k: string]: unknown;
};

function descendants(node: El): El[] {
  return [
    node,
    ...Array.from(node.childNodes ?? []).flatMap((n) => descendants(n as El)),
  ];
}

function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return node[key] as Record<string, (arg?: unknown) => void>;
}

describe("Congress control bundle & PartyControlRow (#9880)", () => {
  test("W1 & W2: normal rendering draws two two-sided party rows with served percents, split bar, residual, and fixed blue/red slot order", () => {
    const senate = clone(REAL_SENATE_ITEM);
    const house = clone(REAL_HOUSE_ITEM);
    const html = renderBundle(makeCongressBundleItem([senate, house]));

    expect(html).toContain("Who wins control of Congress?");
    expect(html).toContain("Congress");

    const twoSidedLinks = Array.from(
      html.matchAll(/<a [^>]*data-row-kind="two-sided"[^>]*>/g),
    );
    expect(twoSidedLinks).toHaveLength(2);

    // Both rows name Democratic Party left, Republican Party right, in text-text-primary
    const leftNames = Array.from(
      html.matchAll(/data-testid="party-control-name-left">([^<]+)</g),
    ).map((m) => m[1]);
    const rightNames = Array.from(
      html.matchAll(/data-testid="party-control-name-right">([^<]+)</g),
    ).map((m) => m[1]);
    expect(leftNames).toEqual(["Democratic Party", "Democratic Party"]);
    expect(rightNames).toEqual(["Republican Party", "Republican Party"]);

    // Served rendered_percent printed (66% / 34% and 91% / 9%), leader 22px, trail 15px
    const leftPercents = Array.from(
      html.matchAll(
        /<div class="([^"]*)" data-probability="([^"]+)" data-rendered-percent="([^"]+)" data-leader="([^"]+)" data-testid="party-control-percent-left">([^<]+)<\/div>/g,
      ),
    );
    const rightPercents = Array.from(
      html.matchAll(
        /<div class="([^"]*)" data-probability="([^"]+)" data-rendered-percent="([^"]+)" data-leader="([^"]+)" data-testid="party-control-percent-right">([^<]+)<\/div>/g,
      ),
    );
    expect(leftPercents).toHaveLength(2);
    expect(rightPercents).toHaveLength(2);

    expect(leftPercents[0].slice(2)).toEqual(["0.655", "66", "true", "66%"]);
    expect(leftPercents[0][1]).toContain("text-[22px]");
    expect(leftPercents[0][1]).toContain("text-text-primary");

    expect(rightPercents[0].slice(2)).toEqual(["0.335", "34", "false", "34%"]);
    expect(rightPercents[0][1]).toContain("text-[15px]");
    expect(rightPercents[0][1]).toContain("text-text-primary");

    expect(leftPercents[1].slice(2)).toEqual(["0.9125", "91", "true", "91%"]);
    expect(rightPercents[1].slice(2)).toEqual(["0.0875", "9", "false", "9%"]);

    // W2: Bar widths = served probabilities (65.50% / 33.50% and 91.25% / 8.75%), residual = 0.0100 and 0.0000
    expect(html).toContain('data-residual="0.0100"');
    expect(html).toContain('data-residual="0.0000"');
    expect(html).toContain("bg-surface-border");
    expect(html).toContain(
      `style="width:65.50%;background-color:${PARTY_CONTROL_SLOT_COLORS[0]}"`,
    );
    expect(html).toContain(
      `style="width:33.50%;background-color:${PARTY_CONTROL_SLOT_COLORS[1]}"`,
    );
    expect(html).toContain(
      `style="width:91.25%;background-color:${PARTY_CONTROL_SLOT_COLORS[0]}"`,
    );
    expect(html).toContain(
      `style="width:8.75%;background-color:${PARTY_CONTROL_SLOT_COLORS[1]}"`,
    );

    // Fixed slot order holds even when Republican Party is first in top_outcomes and leads
    const gopLead = clone(REAL_SENATE_ITEM.data as FeedFuturesData);
    gopLead.top_outcomes = [
      {
        id: 1,
        name: "Republican Party",
        probability: 0.61,
        rank: 1,
        movement: null,
        rendered_percent: 61,
      },
      {
        id: 2,
        name: "Democratic Party",
        probability: 0.39,
        rank: 2,
        movement: null,
        rendered_percent: 39,
      },
    ];
    const model = partyControlRowProps(gopLead);
    expect(model).not.toBeNull();
    expect(model?.a.name).toBe("Democratic Party");
    expect(model?.a.color).toBe(PARTY_CONTROL_SLOT_COLORS[0]);
    expect(model?.a.isLeader).toBe(false);
    expect(model?.b.name).toBe("Republican Party");
    expect(model?.b.color).toBe(PARTY_CONTROL_SLOT_COLORS[1]);
    expect(model?.b.isLeader).toBe(true);

    // S3 / Tightening #5: Senate source_count=2 vs 1 produces byte-identical markup and prints no source count claim
    const senateSingleSource = clone(REAL_SENATE_ITEM);
    (senateSingleSource.data as FeedFuturesData).source_count = 1;
    (senateSingleSource.data as FeedFuturesData & { sources?: string[] }).sources = [
      "kalshi",
    ];
    const htmlWithOne = renderBundle(
      makeCongressBundleItem([senateSingleSource, clone(REAL_HOUSE_ITEM)]),
    );
    expect(html).toBe(htmlWithOne);
    expect(html).not.toContain("2 sources");
  });

  test("W3: missing rendered_percent refuses two-sided row and falls back to FuturesCompactRow without client arithmetic", () => {
    const senate = clone(REAL_SENATE_ITEM);
    delete (senate.data as FeedFuturesData).top_outcomes[1].rendered_percent;
    const house = clone(REAL_HOUSE_ITEM);

    expect(partyControlRowProps(senate.data as FeedFuturesData)).toBeNull();

    const html = renderBundle(makeCongressBundleItem([senate, house]));
    expect(
      Array.from(html.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(1);
    expect(
      Array.from(html.matchAll(/data-testid="compact-row-title"/g)),
    ).toHaveLength(1);
    expect(html).toContain('data-testid="compact-row-percent">66%<');
    expect(html).not.toContain("34%");
  });

  test("W4: pair total over 100% (0.52 + 0.50 = 1.02) is refused rather than normalized or squeezed", () => {
    const senate = clone(REAL_SENATE_ITEM);
    const sData = senate.data as FeedFuturesData;
    sData.top_outcomes[0].probability = 0.52;
    sData.top_outcomes[0].rendered_percent = 51;
    sData.top_outcomes[1].probability = 0.5;
    sData.top_outcomes[1].rendered_percent = 49;
    senate.context_summary = "Democratic Party leads at 51%";

    expect(partyControlRowProps(sData)).toBeNull();

    const html = renderBundle(
      makeCongressBundleItem([senate, clone(REAL_HOUSE_ITEM)]),
    );
    expect(
      Array.from(html.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(1);
    expect(html).toContain('data-testid="compact-row-percent">51%<');
  });

  test("W5: withheld / null probabilities fall back to FuturesCompactRow printing em-dash", () => {
    const senate = clone(REAL_SENATE_ITEM);
    const house = clone(REAL_HOUSE_ITEM);
    const hData = house.data as FeedFuturesData;
    for (const o of hData.top_outcomes) {
      (o as { probability: number | null }).probability = null;
      delete o.rendered_percent;
    }
    house.context_summary = "Resolves Feb 1, 2027";
    house.headline = null;
    house.reason = "";

    const html = renderBundle(makeCongressBundleItem([senate, house]));
    expect(
      Array.from(html.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(1);
    expect(html).toContain('data-testid="compact-row-percent">—<');
  });

  test("W6 & W7: one or both members resolved render Resolved · <winner> with no bar", () => {
    const senate = clone(REAL_SENATE_ITEM);
    const houseResolved = clone(REAL_HOUSE_ITEM);
    (houseResolved.data as FeedFuturesData).winner = "Democratic Party";
    (houseResolved.data as FeedFuturesData).status = "settled";

    const oneHtml = renderBundle(
      makeCongressBundleItem([senate, houseResolved]),
    );
    expect(
      Array.from(oneHtml.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(1);
    expect(oneHtml).toContain(
      'data-testid="compact-row-assigned-result">Resolved · Democratic Party<',
    );

    const senateResolved = clone(REAL_SENATE_ITEM);
    (senateResolved.data as FeedFuturesData).winner = "Republican Party";
    (senateResolved.data as FeedFuturesData).status = "settled";

    const bothHtml = renderBundle(
      makeCongressBundleItem([senateResolved, houseResolved]),
    );
    expect(
      Array.from(bothHtml.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(0);
    expect(bothHtml).toContain(
      'data-testid="compact-row-assigned-result">Resolved · Republican Party<',
    );
    expect(bothHtml).toContain(
      'data-testid="compact-row-assigned-result">Resolved · Democratic Party<',
    );
  });

  test("W8, N1, N2: unknown party alias, duplicate party alias, third outcome, non-party duel, and non-Congress story key use compact rows", () => {
    // SYN-7: duplicate alias ("Democrats" + "Dem") and 3-outcome House
    const senateDupAlias = clone(REAL_SENATE_ITEM);
    (senateDupAlias.data as FeedFuturesData).top_outcomes[0].name = "Democrats";
    (senateDupAlias.data as FeedFuturesData).top_outcomes[1].name = "Dem";

    const houseThree = clone(REAL_HOUSE_ITEM);
    const hData = houseThree.data as FeedFuturesData;
    hData.outcome_count = 3;
    hData.top_outcomes.push({
      id: 99,
      name: "Independent",
      probability: 0.004,
      rank: 3,
      movement: null,
      rendered_percent: 0,
    });

    const invalidHtml = renderBundle(
      makeCongressBundleItem([senateDupAlias, houseThree]),
    );
    expect(
      Array.from(invalidHtml.matchAll(/data-row-kind="two-sided"/g)),
    ).toHaveLength(0);
    expect(
      Array.from(invalidHtml.matchAll(/data-testid="compact-row-title"/g)),
    ).toHaveLength(2);

    // N1: Non-political duel with "Blue Team" / "Red Team"
    const sportsDuel = clone(REAL_SENATE_ITEM.data as FeedFuturesData);
    sportsDuel.name = "Which team wins?";
    sportsDuel.top_outcomes[0].name = "Blue Team";
    sportsDuel.top_outcomes[1].name = "Red Team";
    expect(partyControlRowProps(sportsDuel)).toBeNull();

    // N2: Party duel inside a non-Congress story ("story:us_state_races") renders FuturesCompactRow
    expect(isCongressControlStoryKey("story:us_state_races")).toBe(false);
    const stateRaceHtml = renderToStaticMarkup(
      <ThemeBundleCard
        items={[clone(REAL_SENATE_ITEM), clone(REAL_HOUSE_ITEM)]}
        title="State Races"
        sharedQuestion="Who wins the big state races?"
        storyKey="story:us_state_races"
      />,
    );
    expect(stateRaceHtml).not.toContain('data-row-kind="two-sided"');
    expect(
      Array.from(stateRaceHtml.matchAll(/data-testid="compact-row-title"/g)),
    ).toHaveLength(2);
  });

  test("W9, W10, W11: caption guard deletes only exact visible party lead clause and leaves mismatches untouched", () => {
    const visible = [
      { name: "Democratic Party", pct: "66%" },
      { name: "Republican Party", pct: "34%" },
    ];

    // W9: positive deletion
    const pos = stripVisiblePartyLeadClause(
      "Democratic Party leads at 66%, up 26 points since Feb 18",
      visible,
    );
    expect(pos).toEqual({
      text: "Democratic Party up 26 points since Feb 18",
      party: "Democratic Party",
      rest: " up 26 points since Feb 18",
      deleted: "leads at 66%,",
    });

    // W10: mismatched percent (65% vs printed 66%) -> untouched
    const mismatchPct = stripVisiblePartyLeadClause(
      "Democratic Party leads at 65%, up 26 points since Feb 18",
      visible,
    );
    expect(mismatchPct).toEqual({
      text: "Democratic Party leads at 65%, up 26 points since Feb 18",
      party: null,
      rest: "Democratic Party leads at 65%, up 26 points since Feb 18",
      deleted: null,
    });

    // W11: other party's name with leader's percent, or "New favorite" shape -> untouched
    const wrongParty = stripVisiblePartyLeadClause(
      "Republican Party leads at 66%, up 26 points since Feb 18",
      visible,
    );
    expect(wrongParty.deleted).toBeNull();
    expect(wrongParty.text).toBe(
      "Republican Party leads at 66%, up 26 points since Feb 18",
    );

    const newFav = stripVisiblePartyLeadClause(
      "New favorite: Republican Party (52%)",
      visible,
    );
    expect(newFav.deleted).toBeNull();
    expect(newFav.text).toBe("New favorite: Republican Party (52%)");
  });

  test("W12 & W13: long labels wrap without clamping; links, Expand, and Back restoration work as expected", () => {
    const senateLong = clone(REAL_SENATE_ITEM);
    (senateLong.data as FeedFuturesData).name =
      "Which party will hold a majority of seats in the United States Senate after the November 2026 midterm elections are certified?";
    const houseLong = clone(REAL_HOUSE_ITEM);
    (houseLong.data as FeedFuturesData).top_outcomes[0].name =
      "The Democratic Party";
    (houseLong.data as FeedFuturesData).top_outcomes[1].name =
      "The Republican Party";
    houseLong.context_summary =
      "The Democratic Party leads at 91%, up 13.7 points since Feb 18";

    const staticHtml = renderToStaticMarkup(
      <ThemeBundleCard
        items={[senateLong, houseLong]}
        title="Congress"
        sharedQuestion="Who wins control of Congress?"
        storyKey="story:us_congress_control:2026"
      />,
    );

    const titleClasses = Array.from(
      staticHtml.matchAll(
        /<div class="([^"]*)" data-testid="party-control-row-title">/g,
      ),
    ).map((m) => m[1]);
    expect(titleClasses).toHaveLength(2);
    expect(titleClasses[0]).not.toContain("line-clamp");
    expect(titleClasses[0]).toContain("break-words");

    expect(staticHtml).toContain(
      'data-caption-deleted="leads at 66%," data-testid="party-control-caption"><b class="font-semibold text-text-secondary">Democratic Party</b> up 26 points since Feb 18</div>',
    );
    expect(staticHtml).toContain(
      'data-caption-deleted="leads at 91%," data-testid="party-control-caption"><b class="font-semibold text-text-secondary">The Democratic Party</b> up 13.7 points since Feb 18</div>',
    );

    // W13: Row links point to /futures/108620 and /futures/108621
    const links = Array.from(
      staticHtml.matchAll(/<a href="([^"]+)"[^>]*data-row-kind="two-sided"/g),
    ).map((m) => m[1]);
    expect(links).toEqual(["/futures/108620", "/futures/108621"]);

    // Interactive mount: Expand toggles full member cards and fires theme_bundle_expand; Back restoration works
    const bundleId = "theme:story:us_congress_control:2026:108620-108621";
    const host = document.createElement("div") as unknown as El;
    document.body.appendChild(host as unknown as Node);
    let root = createRoot(host as unknown as Element);

    act(() => {
      root.render(
        <ThemeBundleCard
          items={[senateLong, houseLong]}
          title="Congress"
          sharedQuestion="Who wins control of Congress?"
          storyKey="story:us_congress_control:2026"
          bundleId={bundleId}
        />,
      );
    });

    const expandBtn = () =>
      descendants(host).find(
        (n) => n.tagName === "BUTTON" && n.textContent === "Expand",
      );
    expect(expandBtn()).toBeDefined();

    act(() => {
      reactProps(expandBtn()!).onClick();
    });
    expect(expandBtn()).toBeUndefined();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      "theme_bundle_expand",
      expect.objectContaining({
        story_key: "story:us_congress_control:2026",
        member_count: 2,
      }),
    );

    // Simulate returning Back after remembering expanded state
    rememberThemeCollectionReturn(bundleId, true);
    act(() => root.unmount());
    root = createRoot(host as unknown as Element);
    act(() => {
      root.render(
        <ThemeBundleCard
          items={[senateLong, houseLong]}
          title="Congress"
          sharedQuestion="Who wins control of Congress?"
          storyKey="story:us_congress_control:2026"
          bundleId={bundleId}
        />,
      );
    });
    expect(expandBtn()).toBeUndefined();

    act(() => root.unmount());
    document.body.removeChild(host as unknown as Node);
  });

  test("W14: non-Congress theme families and comparison GroupCards are byte-identical and refused by partyControlRowProps", () => {
    const fedMember: FeedItem = {
      type: "futures",
      score: 80,
      reason: "",
      headline: "Keep rates unchanged leads at 67%",
      context_summary: "Keep rates unchanged leads at 67%",
      data: {
        id: 501,
        name: "Fed decision in December?",
        llm_sport_category: "economics",
        market_type: "field",
        outcome_count: 3,
        top_outcomes: [
          {
            id: 1,
            name: "Keep rates unchanged",
            probability: 0.67,
            movement: null,
            rendered_percent: 67,
          },
        ],
      } as unknown as FeedFuturesData,
    };

    for (const storyKey of [
      "story:ai",
      "story:macro_rates",
      "story:middle_east_conflict",
      "story:russia_ukraine",
      "story:major_entertainment_events",
      "story:ufc_events",
      "story:grand_slam_tennis",
      "story:us_state_races",
    ]) {
      expect(isCongressControlStoryKey(storyKey)).toBe(false);
    }
    expect(partyControlRowProps(fedMember.data as FeedFuturesData)).toBeNull();

    const themeHtml = renderBundle({
      type: "bundle",
      score: 80,
      reason: "What does the Fed do next?",
      headline: "Fed & Rates",
      data: {
        id: "theme:story:macro_rates:501",
        title: "Fed & Rates",
        kind: "theme",
        story_key: "story:macro_rates",
        shared_question: "What does the Fed do next?",
        item_count: 1,
        member_ids: [501],
        items: [fedMember],
      } as FeedBundleData,
    });
    expect(themeHtml).not.toContain('data-row-kind="two-sided"');
    expect(themeHtml).toContain('data-testid="compact-row-title"');

    // ForYouChip renders on PartyControlRow when net-boosted and stays silent when downranked
    const boostedSenate = {
      ...clone(REAL_SENATE_ITEM),
      personalized: true,
      multiplier: 1.35,
      personalization_reasons: ["your_team:0.35"],
    } as unknown as FeedItem;
    const downrankedHouse = {
      ...clone(REAL_HOUSE_ITEM),
      personalized: true,
      multiplier: 0.9,
      personalization_reasons: ["your_team:0.35", "sport_suppress:-0.50"],
    } as unknown as FeedItem;
    const boostedHtml = renderBundle(
      makeCongressBundleItem([boostedSenate, downrankedHouse]),
    );
    expect(
      Array.from(boostedHtml.matchAll(/data-testid="for-you-cue"/g)),
    ).toHaveLength(1);
  });
});
