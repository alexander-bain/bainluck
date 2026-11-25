/**
 * #13550 (363: A) — /grade/forms v2 blind pile-sort UI, copy, empty Pile 1,
 * Start over reset, and stale pre-fix row filtering tests.
 */
import fs from "node:fs";
import path from "node:path";
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

import formsDeck from "@/data/forms_blind_deck_public_2026_11_23.json";
import GradeFormsDeckPage from "@/app/grade/forms/page";
import {
  addEmptyPile,
  createInitialEmptyPiles,
  createPileWithCard,
  GRADE_FORMS_VALID_AFTER_ISO,
  isPostFixFormsJudgmentRow,
  moveCardToPilePreservingEmpty,
  pruneEmptyPilesForSave,
  removeCardPreservingEmptyPiles,
} from "@/lib/ranking/blindDeckGrade363a";

describe("#13550 (363: A) — /grade/forms v2 pile sort", () => {
  test("renders empty Pile 1, worked example, Start over, and verbatim instructions on initial load", () => {
    const html = renderToStaticMarkup(React.createElement(GradeFormsDeckPage));
    const initial = createInitialEmptyPiles();
    expect(initial).toHaveLength(1);
    expect(initial[0].item_ids).toEqual([]);

    expect(html).toContain("Forms deck");
    expect(html).toContain(
      "Put cards that look like the same kind of card in the same pile. We are counting how many different looks a reader sees.",
    );
    expect(html).toContain("Worked example");
    expect(html).toContain("Pile 1 · Bars &amp; rows");
    expect(html).toContain("Pile 2 · Calendar grid");
    expect(html).toContain("Different layout");
    expect(html).toContain(`data-testid="start-over-btn"`);
    expect(html).toContain("Start over");
    expect(html).toContain(`data-testid="pile-bucket-${initial[0].pile_id}"`);
    expect(html).toContain("Pile 1 · 0 cards");
    expect(html).toContain(`data-testid="save-panel"`);
    expect(html).toContain(`data-testid="progress-summary"`);
    expect(html).toContain(`0 of ${formsDeck.forms.length} placed`);
    expect(html).toContain(`data-testid="new-pile-dropzone"`);

    for (const card of formsDeck.forms) {
      expect(html).toContain(`data-testid="unsorted-card-${card.item_id}"`);
    }

    const forbiddenTokens = [
      "form_id",
      "display_name",
      "source_slug",
      "nominations",
      "mvp",
      "ladder",
    ];
    for (const token of forbiddenTokens) {
      expect(html.toLowerCase()).not.toContain(token);
    }
  });

  test("preserves empty piles during edits and Start over, while pruning empty piles only on save", () => {
    const start = createInitialEmptyPiles();
    const pile1Id = start[0].pile_id;
    const withPile2 = addEmptyPile(start);
    expect(withPile2).toHaveLength(2);

    const movedToPile1 = moveCardToPilePreservingEmpty(withPile2, "card-a", pile1Id);
    expect(movedToPile1.find((p) => p.pile_id === pile1Id)?.item_ids).toEqual(["card-a"]);

    const pile2Id = withPile2[1].pile_id;
    const movedToPile2 = moveCardToPilePreservingEmpty(movedToPile1, "card-a", pile2Id);
    // Pile 1 stays visible (empty) rather than disappearing under the user's hands.
    expect(movedToPile2).toHaveLength(2);
    expect(movedToPile2.find((p) => p.pile_id === pile1Id)?.item_ids).toEqual([]);
    expect(movedToPile2.find((p) => p.pile_id === pile2Id)?.item_ids).toEqual(["card-a"]);

    const unsorted = removeCardPreservingEmptyPiles(movedToPile2, "card-a");
    expect(unsorted).toHaveLength(2);
    expect(unsorted.every((p) => p.item_ids.length === 0)).toBe(true);

    const withNew = createPileWithCard(movedToPile2, "card-b");
    const pruned = pruneEmptyPilesForSave(withNew);
    expect(pruned.every((p) => p.item_ids.length > 0)).toBe(true);
    expect(pruned.some((p) => p.pile_id === pile1Id)).toBe(false);
    expect(pruned.map((p) => p.item_ids).flat().sort()).toEqual(["card-a", "card-b"]);

    const reset = createInitialEmptyPiles();
    expect(reset).toHaveLength(1);
    expect(reset[0].item_ids).toEqual([]);
  });

  test("isPostFixFormsJudgmentRow ignores pre-fix or pre-reset saves without deleting them", () => {
    expect(GRADE_FORMS_VALID_AFTER_ISO).toBe("2026-11-24T22:00:00Z");

    const validPiles = [{ pile_id: "pile-1", label: "Pile 1", item_ids: ["f01"] }];
    // Pre-fix ui_version (v1 or omitted) even after cutoff -> ignored
    expect(
      isPostFixFormsJudgmentRow({
        created_at: "2026-11-24T23:00:00Z",
        label_metadata: { piles: validPiles, timestamp: "2026-11-24T23:00:00Z" },
      }),
    ).toBe(false);

    // Pre-cutoff row even with ui_version: 2 -> ignored
    expect(
      isPostFixFormsJudgmentRow({
        created_at: "2026-11-24T21:59:59Z",
        label_metadata: { ui_version: 2, piles: validPiles, timestamp: "2026-11-24T21:59:59Z" },
      }),
    ).toBe(false);

    // Post-cutoff ui_version: 2 row -> accepted when no newer reset
    expect(
      isPostFixFormsJudgmentRow({
        created_at: "2026-11-24T22:05:00Z",
        label_metadata: { ui_version: 2, piles: validPiles, timestamp: "2026-11-24T22:05:00Z" },
      }),
    ).toBe(true);

    // Same row is ignored once user clicked Start over at 22:10:00Z
    expect(
      isPostFixFormsJudgmentRow(
        {
          created_at: "2026-11-24T22:05:00Z",
          label_metadata: { ui_version: 2, piles: validPiles, timestamp: "2026-11-24T22:05:00Z" },
        },
        "2026-11-24T22:10:00Z",
      ),
    ).toBe(false);

    // A fresh save after Start over -> accepted
    expect(
      isPostFixFormsJudgmentRow(
        {
          created_at: "2026-11-24T22:11:00Z",
          label_metadata: { ui_version: 2, piles: validPiles, timestamp: "2026-11-24T22:11:00Z" },
        },
        "2026-11-24T22:10:00Z",
      ),
    ).toBe(true);
  });

  test("POST payload strings fit RankingJudgment VARCHAR column limits", () => {
    const pageSrc = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/forms/page.tsx"),
      "utf-8",
    );
    const surfaceMatch = pageSrc.match(/surface:\s*"([^"]+)"/);
    const itemTypeMatch = pageSrc.match(/item_type:\s*"([^"]+)"/);
    const reviewerMatch = pageSrc.match(/reviewer:\s*"([^"]+)"/);
    expect(surfaceMatch?.[1]).toBe("grade_forms_deck");
    expect(surfaceMatch![1].length).toBeLessThanOrEqual(50);
    expect(itemTypeMatch?.[1]).toBe("forms_pile_sort");
    expect(itemTypeMatch![1].length).toBeLessThanOrEqual(20);
    expect(reviewerMatch![1].length).toBeLessThanOrEqual(100);
    expect(pageSrc).toContain('label: allPlaced ? "complete" : "draft"');
    for (const label of ["complete", "draft"]) {
      expect(label.length).toBeLessThanOrEqual(10);
    }
  });

  test("mobile quick-place pile buttons show the first card thumbnail when a pile is non-empty", () => {
    const pageSrc = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/forms/page.tsx"),
      "utf-8",
    );
    expect(pageSrc).toContain("const firstCard = pile.item_ids[0] ? byId[pile.item_ids[0]] : null");
    expect(pageSrc).toContain('data-testid={`quick-place-${pile.pile_id}`}');
    expect(pageSrc).toContain('data-testid={`quick-place-thumb-${pile.pile_id}`}');
    expect(pageSrc).toContain("src={firstCard.image_url}");
    expect(pageSrc).toContain("draggable={false}");
  });
});
