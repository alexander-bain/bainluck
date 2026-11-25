/**
 * #13544 / #13553 (Part A) — Blind sets v2 deck parity + zero provider leak check.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/grade/sets-v2",
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
    secret: "test-secret",
    mode: "secret",
    email: null,
    clearSecret: jest.fn(),
  }),
}));

import setsV2Deck from "@/data/fun_scout_blind_40_deck_v2_2026_11_23.json";
import GradeSetsV2DeckPage from "@/app/grade/sets-v2/page";

describe("#13553 Part A — /grade/sets-v2 blind 40-set grading page", () => {
  test("frontend deck JSON matches backend data file identically", () => {
    const backendPath = path.resolve(
      __dirname,
      "../../../backend/data/discover/fun_scout_blind_40_deck_v2_2026_11_23.json",
    );
    const frontendPath = path.resolve(
      __dirname,
      "../../data/fun_scout_blind_40_deck_v2_2026_11_23.json",
    );
    expect(fs.readFileSync(frontendPath, "utf-8")).toBe(
      fs.readFileSync(backendPath, "utf-8"),
    );
    expect(setsV2Deck.cards).toHaveLength(40);
  });

  test("renders card content cleanly while never printing source (kalshi/polymarket)", () => {
    const html = renderToStaticMarkup(React.createElement(GradeSetsV2DeckPage));
    const firstCard = setsV2Deck.cards[0];
    expect(html).toContain("Sets blind 40 v2 (#13544)");
    expect(html).toContain(firstCard.card_id);
    expect(html).toContain(firstCard.title);
    for (const member of firstCard.members) {
      expect(html).toContain(member.title);
    }
    expect(html.toLowerCase()).not.toContain("kalshi");
    expect(html.toLowerCase()).not.toContain("polymarket");

    // Ensure the page source itself never accesses or renders member.source.
    const pageSrc = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/sets-v2/page.tsx"),
      "utf-8",
    );
    expect(pageSrc).not.toMatch(/\.source\b/);
    expect(pageSrc).not.toMatch(/\["source"\]/);
  });

  test("POST payload strings fit RankingJudgment VARCHAR column limits", () => {
    const pageSrc = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/sets-v2/page.tsx"),
      "utf-8",
    );
    const surfaceMatch = pageSrc.match(/surface:\s*"([^"]+)"/);
    const itemTypeMatch = pageSrc.match(/item_type:\s*"([^"]+)"/);
    const reviewerMatch = pageSrc.match(/reviewer:\s*"([^"]+)"/);
    expect(surfaceMatch?.[1]).toBe("grade_sets_v2_deck");
    expect(surfaceMatch![1].length).toBeLessThanOrEqual(50);
    expect(itemTypeMatch?.[1]).toBe("sets_blind_40_v2");
    expect(itemTypeMatch![1].length).toBeLessThanOrEqual(20);
    expect(reviewerMatch![1].length).toBeLessThanOrEqual(100);
    for (const label of ["Keep", "Fix", "Drop"]) {
      expect(label.length).toBeLessThanOrEqual(10);
    }
  });
});
