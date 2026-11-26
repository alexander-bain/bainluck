/**
 * #13102 (Decision 385: A) — /grade/scout morning blind deck component tests.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/grade/scout",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

jest.mock("@/components/admin/AdminAuthProvider", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  useAdminAuth: () => ({
    secret: "test-secret-000",
    mode: "secret",
    email: null,
    clearSecret: jest.fn(),
  }),
}));

import GradeScoutMorningDeckPage from "@/app/grade/scout/page";
import {
  SCOUT_DECK_DEFAULT_SURFACE,
  SCOUT_DECK_ITEM_TYPE,
  parseScoutDeckSearchParams,
} from "@/lib/ranking/scoutMorningDeck13102";

describe("#13102 — /grade/scout blind morning deck", () => {
  test("renders cleanly without dark classes or origin/source leakage", () => {
    const html = renderToStaticMarkup(React.createElement(GradeScoutMorningDeckPage));
    expect(html).toContain("Scout Morning Deck (385: A)");
    expect(html.toLowerCase()).not.toContain("kalshi");
    expect(html.toLowerCase()).not.toContain("polymarket");

    const pageSrc = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/scout/page.tsx"),
      "utf-8",
    );
    expect(pageSrc).not.toMatch(/\.source\b/);
    expect(pageSrc).not.toMatch(/\.origin\b/);
    expect(pageSrc).not.toMatch(/\bdark:/);
  });

  test("validates search params and matches RankingJudgment column limits", () => {
    expect(parseScoutDeckSearchParams("?date=2026-11-26&smoke_surface=grade_scout_smoke_run1")).toEqual({
      deckDate: "2026-11-26",
      activeSurface: "grade_scout_smoke_run1",
    });
    expect(parseScoutDeckSearchParams("?date=bad&smoke_surface=not_smoke")).toEqual({
      deckDate: null,
      activeSurface: "grade_scout_morning_deck",
    });
    expect(SCOUT_DECK_DEFAULT_SURFACE.length).toBeLessThanOrEqual(50);
    expect(SCOUT_DECK_ITEM_TYPE.length).toBeLessThanOrEqual(20);
    for (const label of ["Keep", "Fix", "Drop"]) {
      expect(label.length).toBeLessThanOrEqual(10);
    }
  });
});
