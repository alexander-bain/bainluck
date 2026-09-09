/**
 * #4428 — A GROUPED CARD OFFERS THE READER SOMETHING TO DO WITH IT.
 *
 * Alex, reading Discover on bainluck.com the morning of 2026-09-09 (Fable-5's
 * 10:05am PT note, item 3): grouped cards "have no share".
 *
 * ═══ THE DEFECT, MEASURED ═══
 *
 * Production page one at 390px that morning:
 *
 *   bundles      Share 0 of 5   Like 0 of 5
 *   single cards Share 13 of 14 Like 13 of 14
 *
 * `ActionBar` (`discover/shared.tsx`) carries Like / Pin / Share and is rendered
 * by the card variants inside `FuturesCard`, `EventCard` and friends. Neither
 * `ThemeBundleCard` nor `GroupCard` rendered one:
 *
 *   - COLLAPSED, a bundle mounts no member card at all — the rows are
 *     `FuturesCompactRow` peeks — so there was no `ActionBar` anywhere in the
 *     subtree. This is the state page one serves, which is why the measurement
 *     above is 0 of 5 and not 0 of some.
 *   - EXPANDED, each member brings its own, so a reader could share *a member*
 *     and never the group the header names ("Who wins in 2028?"), which is the
 *     thing they are actually reading.
 *
 * ═══ WHY THE EXPANDED STATE IS PROVED BY STRUCTURE, NOT BY A RENDER ═══
 *
 * `expanded` is `useState(false)` with no prop override, and this suite renders
 * through `renderToStaticMarkup`, which runs no effects and no clicks (the same
 * wall #4425 hit). The expanded branch is unreachable from a render test.
 *
 * So the collapsed render proves the affordance exists in the state the reader
 * actually met, and a STRUCTURAL guard proves it exists in the other one: the
 * `<BundleActionBar>` call site is located by brace-matching the two conditional
 * blocks and asserting it falls outside BOTH. Move it inside either and the
 * guard goes red. Its positive control is `<ThemeBundleMember>`, which the same
 * scanner must find INSIDE the expanded block — without that, a scanner that
 * matched nothing would pass every "is outside" assertion in this file.
 *
 * ═══ BOTH SIBLINGS, ONE COMPONENT ═══
 *
 * `ThemeBundleCard` and `GroupCard` are the two bundle shapes and they are the
 * same hazard #4425 was: sibling branches, one wired and one forgotten. They are
 * asserted separately here and share one implementation, so a fix cannot land in
 * half the surface again.
 *
 * FIXTURES ARE VERBATIM PRODUCTION PAYLOADS — `GET /api/feed?limit=25`,
 * 2026-09-09 ~13:05 PT (`__tests__/fixtures/discoverBundles.20260909.json`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import type { FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { ThemeBundleCard } from "@/components/discover/ThemeBundleCard";
import { GroupCard } from "@/components/discover/GroupCard";
import BUNDLES from "../fixtures/discoverBundles.20260909.json";

const DISCOVER_DIR = join(__dirname, "..", "..", "components", "discover");
const THEME_SOURCE = readFileSync(join(DISCOVER_DIR, "ThemeBundleCard.tsx"), "utf8");
const GROUP_SOURCE = readFileSync(join(DISCOVER_DIR, "GroupCard.tsx"), "utf8");

const ELECTION = (BUNDLES as { election2028: { data: Record<string, unknown> } }).election2028.data;
const MEMBERS = ELECTION.items as unknown as FeedItem[];
const QUESTION = ELECTION.shared_question as string;
const TITLE = ELECTION.title as string;

/**
 * The half-open range of the JSX expression container that starts at `marker`,
 * found by matching braces. Returns null when the marker is absent, which the
 * caller must treat as a failure rather than as "outside".
 */
function braceBlock(src: string, marker: string): [number, number] | null {
  const start = src.indexOf(marker);
  if (start < 0) return null;
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") {
      depth -= 1;
      if (depth === 0) return [start, i + 1];
    }
  }
  return null;
}

function isInside(index: number, block: [number, number] | null): boolean {
  return block != null && index >= block[0] && index < block[1];
}

describe("#4428 — a theme bundle has a Like and a Share of its own", () => {
  const markup = renderToStaticMarkup(
    <ThemeBundleCard
      items={MEMBERS}
      title={TITLE}
      sharedQuestion={QUESTION}
      storyKey={ELECTION.story_key as string}
      positionIndex={5}
    />
  );

  it("CONTROL: the render reached a real collapsed bundle", () => {
    // Asserted BEFORE any claim about the action bar. An empty render, or one
    // that threw its way to a stub, would otherwise satisfy nothing and look
    // like nothing — and this file's remaining arms are all presence checks,
    // which is exactly the shape a blank render passes by accident elsewhere.
    expect(markup).toContain(QUESTION);
    expect(markup).toContain("2028 U.S. Presidential Election winner?");
    // Collapsed is the state page one serves: the peek rows, not member cards.
    expect(markup).toContain("Expand");
  });

  it("🔴 THE SHIP: the bundle renders an action bar", () => {
    // Pre-fix this was absent from every bundle on page one.
    expect(markup).toContain('data-testid="bundle-action-bar"');
  });

  it("🔴 the reader can Share the group, not only its members", () => {
    expect(markup).toContain('aria-label="Share this card"');
  });

  it("🔴 the reader can Like the group", () => {
    expect(markup).toMatch(/>Like</);
  });

  it("exactly one action bar — the bundle's own, not one per member", () => {
    const bars = [...markup.matchAll(/data-testid="bundle-action-bar"/g)];
    expect(bars.length).toBe(1);
  });

  it("no Pin: a bundle has no futures id to pin", () => {
    // Paired with the positive above — Share and Like ARE present in this same
    // markup, so this absence is a decision and not an empty render.
    expect(markup).not.toContain('data-testid="pin-button"');
  });
});

describe("#4428 — the comparison sibling gets the same footer", () => {
  const markup = renderToStaticMarkup(
    <GroupCard items={MEMBERS} title={TITLE} sharedQuestion={QUESTION} positionIndex={7} />
  );

  it("CONTROL: the render reached a real GroupCard", () => {
    expect(markup).toContain(QUESTION);
    expect(markup).toContain("Show 1 more");
  });

  it("🔴 THE SIBLING SHIP: GroupCard renders the bundle action bar too", () => {
    // #4425's lesson, one component out: four sibling branches, three wired.
    // GroupCard renders NO member card in either state, so without this it has
    // no action bar anywhere at all.
    expect(markup).toContain('data-testid="bundle-action-bar"');
    expect(markup).toContain('aria-label="Share this card"');
  });
});

describe("#4428 — the expanded state, which no render test can reach", () => {
  const expandedBlock = braceBlock(THEME_SOURCE, "{expanded && (");
  const collapsedBlock = braceBlock(THEME_SOURCE, "{!expanded && (");
  const barAt = THEME_SOURCE.indexOf("<BundleActionBar");

  it("CONTROL: the scanner finds both conditional blocks and the call site", () => {
    expect(expandedBlock).not.toBeNull();
    expect(collapsedBlock).not.toBeNull();
    expect(barAt).toBeGreaterThan(-1);
  });

  it("CONTROL: the scanner really does resolve block interiors", () => {
    // Without this, a `braceBlock` that returned a zero-width range would make
    // every "is outside" assertion below vacuously true.
    expect(isInside(THEME_SOURCE.indexOf("<ThemeBundleMember"), expandedBlock)).toBe(true);
    expect(isInside(THEME_SOURCE.indexOf("<FuturesCompactRow"), collapsedBlock)).toBe(true);
  });

  it("🔴 the action bar sits OUTSIDE both branches, so it shows in either state", () => {
    expect(isInside(barAt, expandedBlock)).toBe(false);
    expect(isInside(barAt, collapsedBlock)).toBe(false);
  });
});

describe("#4428 — one implementation, so a sibling cannot be forgotten again", () => {
  it("both bundle shapes render the same component", () => {
    expect(THEME_SOURCE).toContain("<BundleActionBar");
    expect(GROUP_SOURCE).toContain("<BundleActionBar");
  });

  it("neither grew its own copy of ActionBar", () => {
    // Paired positive: `<BundleActionBar` IS present in both (arm above), so
    // this is not passing on a file that renders nothing.
    expect(THEME_SOURCE).not.toContain("<ActionBar");
    expect(GROUP_SOURCE).not.toContain("<ActionBar");
  });
});
