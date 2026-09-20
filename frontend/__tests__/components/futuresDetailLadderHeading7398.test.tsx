// #7398 — THE PAGE-LEVEL PROOF.
//
// The lib test pins the rule; this one renders `app/futures/[id]/page.tsx`
// against the REAL production payloads of market 60653756 ("How low will the
// 30Y US Treasury yield get by Sep 30, 2026?"), captured verbatim on
// 2026-09-20 into
//   __tests__/fixtures/futuresDetail60653756Production.json   (the detail route)
//   __tests__/fixtures/futuresGroup60653756Production.json    (the group route)
// and counts what a reader sees.
//
// It exists because the claim is about a PAGE, and because a helper returning
// `undefined` proves nothing if the page never calls it — the defect WAS the
// call site (`title={stem}`), not the helper. A guard on the lib alone would
// pass on the blocked bytes.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/* eslint-disable @typescript-eslint/no-var-requires */
const DETAIL = require("../fixtures/futuresDetail60653756Production.json");
const GROUP = require("../fixtures/futuresGroup60653756Production.json");
/* eslint-enable @typescript-eslint/no-var-requires */

let detail: Record<string, unknown> = DETAIL;
let group: Record<string, unknown> = GROUP;

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") return { data: detail, error: null, isLoading: false };
    if (tag === "futures-group") return { data: group, error: null, isLoading: false };
    return { data: undefined, error: null, isLoading: false };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, pinned: [] }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({}),
}));

import FuturesDetailPage from "@/app/futures/[id]/page";

function render(
  d: Record<string, unknown> = DETAIL,
  g: Record<string, unknown> = GROUP,
): string {
  detail = d;
  group = g;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "60653756" }} />);
}

const H1 = "How low will the 30Y US Treasury yield get by Sep 30, 2026?";
const SCOPE_KEY = "# or below";

describe("the specimen still holds this issue's premise", () => {
  test("production keys this market's only threshold group by a scope key", () => {
    // If the backend ever starts keying these groups by prose, THIS is the test
    // that says so — and the fix below becomes a no-op rather than a lie.
    const groups = GROUP.threshold_groups as Record<string, unknown[]>;
    expect(Object.keys(groups)).toEqual([SCOPE_KEY]);
    expect(groups[SCOPE_KEY]).toHaveLength(20);
  });

  test("the payload's own group_title is the page's <h1>, word for word", () => {
    // Which is why the answer here is NO heading rather than `group_title`.
    expect(GROUP.group_title).toBe(H1);
    expect(DETAIL.name).toBe(H1);
  });
});

describe("what a reader sees", () => {
  test("🔴 the scope key is GONE from the rendered page", () => {
    const html = render();
    expect(html.toLowerCase()).not.toContain(SCOPE_KEY);
    // The uppercase form is what the screenshot shows; the component applies
    // `uppercase` in CSS, so the lowercase check above is the load-bearing one
    // and this is belt and braces against a future hand-cased title.
    expect(html).not.toContain("# OR BELOW");
  });

  test("the ladder itself is untouched — all 20 rungs still render, in order", () => {
    const html = render();
    const at = (s: string) => html.indexOf(`aria-label="${s}:`);
    expect(at("≤ 5.05%")).toBeGreaterThan(-1);
    expect(at("≤ 5.24%")).toBeGreaterThan(-1);
    expect(at("≤ 5.05%")).toBeLessThan(at("≤ 5.24%"));
    const rungs = (GROUP.threshold_groups as Record<string, unknown[]>)[SCOPE_KEY];
    expect(rungs.every((r) => at(`≤ ${(r as { threshold_value: number }).threshold_value}%`) > -1))
      .toBe(true);
  });

  test("the question is still on the page once — in the <h1>, not twice", () => {
    const html = render();
    expect(html).toContain(H1);
    // `>{H1}<` is the hero's own text node. A `group_title` heading echoing it
    // would add a second one.
    expect(html.split(`>${H1}<`).length - 1).toBe(1);
  });

  test("a group_title the <h1> does NOT already say is kept as the heading", () => {
    // The cross-market case. Without it, this fix would silently strip the one
    // heading that carries context — so the removal above is scoped, not blanket.
    const html = render(DETAIL, { ...GROUP, group_title: "Treasury yield ladder — September" });
    expect(html).toContain("Treasury yield ladder — September");
  });
});
