/**
 * #13550 (363: A) — Blind forms pile-sort & 20-container grader unit + render checks.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/grade/forms",
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

import formsPublicDeck from "@/data/forms_blind_deck_public_2026_11_23.json";
import containersPublicDeck from "@/data/containers_blind_20_deck_2026_11_23.json";
import {
  assignCardToPile,
  buildCardToPileMap,
  canonicalContainerGradesString,
  computeSha256Hex,
  createPileWithCard,
  removeCardFromPiles,
  shuffleBlindForms,
  type ContainerGradeEntry,
  type PileBucket,
} from "@/lib/ranking/blindDeckGrade363a";
import GradeFormsDeckPage from "@/app/grade/forms/page";
import GradeContainersDeckPage from "@/app/grade/containers/page";

describe("363: A blind decks grading helpers and pages", () => {
  test("shuffleBlindForms is deterministic for seed and preserves all items", () => {
    const first = shuffleBlindForms(formsPublicDeck.forms, formsPublicDeck.seed);
    const second = shuffleBlindForms(formsPublicDeck.forms, formsPublicDeck.seed);
    expect(first.map((f) => f.item_id)).toEqual(second.map((f) => f.item_id));
    expect(first).toHaveLength(14);
    expect(new Set(first.map((f) => f.item_id)).size).toBe(14);
    expect(first.map((f) => f.item_id)).not.toEqual(
      formsPublicDeck.forms.map((f) => f.item_id),
    );
  });

  test("pile helpers create, move, and clear cards cleanly", () => {
    let piles: PileBucket[] = createPileWithCard([], "f01");
    expect(piles).toEqual([{ pile_id: "pile-1", label: "Pile 1", item_ids: ["f01"] }]);

    piles = createPileWithCard(piles, "f02");
    expect(piles).toHaveLength(2);

    piles = assignCardToPile(piles, "f02", "pile-1");
    expect(piles).toEqual([{ pile_id: "pile-1", label: "Pile 1", item_ids: ["f01", "f02"] }]);
    expect(buildCardToPileMap(piles)).toEqual({ f01: "pile-1", f02: "pile-1" });

    piles = removeCardFromPiles(piles, "f01");
    piles = removeCardFromPiles(piles, "f02");
    expect(piles).toEqual([]);
  });

  test("canonicalContainerGradesString orders item keys deterministically and hashes", async () => {
    const a: Record<string, ContainerGradeEntry> = {
      c02: { grade: "Fix", note: " crop bottom ", updated_at: "2026-11-23T01:00:00Z" },
      c01: { grade: "Keep", note: "", updated_at: "2026-11-23T00:00:00Z" },
    };
    const b: Record<string, ContainerGradeEntry> = {
      c01: { grade: "Keep", note: "", updated_at: "2026-11-24T05:00:00Z" },
      c02: { grade: "Fix", note: "crop bottom", updated_at: "2026-11-24T06:00:00Z" },
    };
    const sa = canonicalContainerGradesString(containersPublicDeck.deck_id, a);
    const sb = canonicalContainerGradesString(containersPublicDeck.deck_id, b);
    expect(sa).toBe(sb);

    const h1 = await computeSha256Hex(sa);
    const h2 = await computeSha256Hex(sb);
    expect(h1).toBe(h2);
    expect(h1.length).toBeGreaterThanOrEqual(8);
  });

  test("public forms and containers SSR markup leaks no form_id or set metadata", () => {
    const formsHtml = renderToStaticMarkup(<GradeFormsDeckPage />);
    const containersHtml = renderToStaticMarkup(<GradeContainersDeckPage />);

    expect(formsHtml).toContain("Forms deck");
    expect(containersHtml).toContain("Containers blind 20");
    expect(containersHtml).toContain("Keep");
    expect(containersHtml).toContain("Fix");
    expect(containersHtml).toContain("Drop");
    for (const forbidden of [
      "form_id",
      "display_name",
      "source_slug",
      "golden-globes",
      "march-madness",
      "presidential",
    ]) {
      expect(formsHtml.toLowerCase()).not.toContain(forbidden);
      expect(containersHtml.toLowerCase()).not.toContain(forbidden);
    }
  });
});
