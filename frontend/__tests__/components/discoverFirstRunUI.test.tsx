// Queue 309 Items 1-2 — the rendered first-run surfaces, plus the wiring guards
// that keep the page's side of the contract honest.
//
// This repo's jest runs in `node` with `renderToStaticMarkup` and has no jsdom
// or React Testing Library (and the npm registry is unreachable from the build
// sandbox, so adding them is not a same-session option). So the DECISION logic
// is proven in __tests__/lib/discoverFirstRun.test.ts, the two RENDERED pieces
// are proven here as presentational components, and the page's wiring — which
// no unit test can execute — is asserted against its source.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import FirstRunOrientation from "../../components/discover/FirstRunOrientation";
import { FuturesCard } from "../../components/discover/FuturesCard";
import { BRAND_TAGLINE } from "@/lib/brandCopy";
import { HERO_PROBABILITY_HINT } from "@/lib/discoverFirstRun";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

const PAGE_SOURCE = readFileSync(
  join(__dirname, "..", "..", "app", "discover", "page.tsx"),
  "utf8",
);

function futuresData(overrides: Partial<FeedFuturesData> = {}): FeedFuturesData {
  return {
    id: 4242,
    name: "Will the incumbent win the 2026 election?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2026-11-03T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 6_600_000,
    confidence_tier: "high",
    ...overrides,
  } as unknown as FeedFuturesData;
}

function renderCard(data: FeedFuturesData, showProbabilityHint?: boolean): string {
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard
      item={item}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
      showProbabilityHint={showProbabilityHint}
    />,
  );
}

describe("Item 1 — the orientation line", () => {
  it("renders the shared tagline for the first-run cohort", () => {
    const html = renderToStaticMarkup(<FirstRunOrientation visible />);
    expect(html).toContain('data-testid="discover-orientation"');
    expect(html).toContain("Probability, not betting.");
    expect(html).toContain("honest guess at what happens next");
  });

  it("renders NOTHING for a returning or signed-in reader", () => {
    expect(renderToStaticMarkup(<FirstRunOrientation visible={false} />)).toBe("");
  });

  it("uses design-system tokens, no raw color and no dark-mode class", () => {
    const html = renderToStaticMarkup(<FirstRunOrientation visible />);
    expect(html).toMatch(/text-text-(muted|secondary)/);
    expect(html).not.toMatch(/\bdark:/);
    expect(html).not.toMatch(/text-(gray|slate|zinc|neutral)-\d/);
  });

  it("is quiet: no card chrome, no icon, no dismiss affordance", () => {
    const html = renderToStaticMarkup(<FirstRunOrientation visible />);
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<svg");
    expect(html).not.toMatch(/\bborder\b/);
  });

  it("shares ONE constant with the footer, so the two cannot drift", () => {
    const footer = readFileSync(
      join(__dirname, "..", "..", "components", "Footer.tsx"),
      "utf8",
    );
    expect(footer).toContain("BRAND_TAGLINE");
    expect(footer).not.toContain("Probability, not betting");
    expect(renderToStaticMarkup(<FirstRunOrientation visible />)).toContain(
      BRAND_TAGLINE.replace(/'/g, "’").split(".")[0],
    );
  });
});

describe("Item 2 — the first-card hero hint", () => {
  it("labels the hero percentage when the page asks for it", () => {
    // Both card variants carry a hero; exercise whichever this id hashes to.
    const html = renderCard(futuresData(), true);
    expect(html).toContain('data-testid="hero-probability-hint"');
    expect(html).toContain(HERO_PROBABILITY_HINT);
  });

  it("renders no hint by default — every card but the first one", () => {
    const html = renderCard(futuresData());
    expect(html).not.toContain('data-testid="hero-probability-hint"');
    expect(html).not.toContain(HERO_PROBABILITY_HINT);
  });

  it("is a plain label, not a tooltip or a popover with a dismiss control", () => {
    const html = renderCard(futuresData(), true);
    expect(html).not.toContain('role="tooltip"');
    expect(html).not.toContain('role="dialog"');
  });
});

describe("page wiring (source-level — the page cannot be mounted in this harness)", () => {
  it("shows the orientation line only to the first-run cohort", () => {
    expect(PAGE_SOURCE).toContain("<FirstRunOrientation visible={isFirstRunAnon} />");
  });

  it("hints only the FIRST card, and only for that cohort", () => {
    expect(PAGE_SOURCE).toContain("showProbabilityHint={isFirstPosition && isFirstRunAnon}");
  });

  it("gates BOTH games on one boolean", () => {
    expect(PAGE_SOURCE).toContain("!isLoading && gamesUnlocked && processedItems.length > 0");
    expect(PAGE_SOURCE).toMatch(/const isGuessSlot = gamesUnlocked &&/);
  });

  it("a locked quiz slot falls through to a normal card, never an empty cell", () => {
    // `isGuessSlot` chooses between GuessCard and DiscoverCard inside one
    // ternary; there is no branch that renders neither.
    expect(PAGE_SOURCE).toMatch(/isGuessSlot \?[\s\S]{0,400}?<DiscoverCard/);
  });

  it("reads first-run storage in the SAME mount effect as the swipe hint", () => {
    const mountEffect = PAGE_SOURCE.slice(
      PAGE_SOURCE.indexOf("setDismissed(getDismissed());"),
      PAGE_SOURCE.indexOf("const refreshProfile"),
    );
    expect(mountEffect).toContain("discover_has_swiped");
    expect(mountEffect).toContain("setFirstRunStorage(readFirstRunStorage())");
  });

  it("NEVER puts the orientation state on a timer (the P3 trap)", () => {
    // The page's only timer is the pre-existing 5s swipe-hint dismissal. If a
    // second one appears, this fails and whoever added it has to prove it does
    // not touch the orientation cohort.
    const timers = PAGE_SOURCE.match(/setTimeout\(/g) ?? [];
    expect(timers).toHaveLength(1);
    expect(PAGE_SOURCE).toContain("window.setTimeout(dismissHint, 5000)");
    for (const symbol of ["markFirstRunEngaged", "setEngagedThisSession", "setFirstRunStorage"]) {
      expect(PAGE_SOURCE).not.toMatch(new RegExp(`setTimeout\\([^)]*${symbol}`));
    }
  });

  it("leaves the shared-anon warm-feed resolver alone (L2-242 / C133)", () => {
    expect(PAGE_SOURCE).toContain("const sharedAnonEligibleRef = useRef(true);");
    expect(PAGE_SOURCE).not.toMatch(/sharedAnonEligibleRef[^\n]*isFirstRunAnon/);
    expect(PAGE_SOURCE).not.toMatch(/isFirstRunAnon[^\n]*sharedAnonEligibleRef/);
  });
});
