/**
 * #13550 (363: A) — Blind forms pile-sort & 20-container grader unit + render checks.
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

  test("frontend blind manifests have no leaks and match backend manifests", () => {
    const feDataDir = path.join(process.cwd(), "data");
    const beDataDir = path.resolve(process.cwd(), "..", "backend", "data", "discover");

    const publicFormsRaw = fs.readFileSync(
      path.join(feDataDir, "forms_blind_deck_public_2026_11_23.json"),
      "utf-8",
    );
    const backendForms = JSON.parse(
      fs.readFileSync(path.join(beDataDir, "forms_blind_deck_2026_11_23.json"), "utf-8"),
    );
    const publicForms = JSON.parse(publicFormsRaw);

    expect(publicForms.deck_id).toBe("forms-blind-deck-2026-11-23");
    expect(publicForms.blind).toBe(true);
    expect(publicForms.seed).toBe(2026112304);
    expect(publicForms.sheet_image_url).toBeUndefined();
    expect(publicForms.forms).toHaveLength(14);
    expect(backendForms.forms).toHaveLength(14);

    const lowered = publicFormsRaw.toLowerCase();
    for (const secretKey of [
      "form_id",
      "display_name",
      "source_slug",
      "nominations",
      "mvp",
      "ladder",
    ]) {
      expect(lowered).not.toContain(secretKey);
    }

    const byId = Object.fromEntries(
      backendForms.forms.map((f: Record<string, unknown>) => [f.item_id, f]),
    );
    for (const item of publicForms.forms) {
      expect(Object.keys(item).sort()).toEqual(["height_px", "image_url", "item_id", "width_px"]);
      const ref = byId[item.item_id];
      expect(item.image_url).toBe(ref.image_url);
      expect(item.width_px).toBe(ref.width_px);
      expect(item.height_px).toBe(ref.height_px);
    }

    const feContainersRaw = fs.readFileSync(
      path.join(feDataDir, "containers_blind_20_deck_2026_11_23.json"),
      "utf-8",
    );
    const beContainersRaw = fs.readFileSync(
      path.join(beDataDir, "containers_blind_20_deck_2026_11_23.json"),
      "utf-8",
    );
    expect(feContainersRaw).toBe(beContainersRaw);
  });

  test("#13551 Friday 11-card light blind forms deck is uniform, unlabelled, and key stays out of repo", () => {
    const feDataDir = path.join(process.cwd(), "data");
    const beDataDir = path.resolve(process.cwd(), "..", "backend", "data", "discover");
    const nov27Raw = fs.readFileSync(
      path.join(feDataDir, "forms_blind_deck_public_2026_11_27.json"),
      "utf-8",
    );
    const nov27 = JSON.parse(nov27Raw);

    expect(nov27.deck_id).toBe("forms-blind-deck-2026-11-27");
    expect(nov27.blind).toBe(true);
    expect(nov27.color_scheme).toBe("light");
    expect(nov27.image_width_px).toBe(780);
    expect(nov27.css_width_px).toBe(390);
    expect(nov27.sealed_checksum_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(nov27.forms).toHaveLength(11);

    const lowered = nov27Raw.toLowerCase();
    for (const secretKey of [
      "form_id",
      "display_name",
      "source_slug",
      "kit",
      "anchor",
      "candidate",
      "scoreboard",
      "dated_tiles",
      "one_in_n",
      "casting_sheet",
      "bond",
      "elon",
      "cfb",
      "ceasefire",
    ]) {
      expect(lowered).not.toContain(secretKey);
    }

    const ids = new Set<string>();
    const urls = new Set<string>();
    for (const item of nov27.forms) {
      expect(Object.keys(item).sort()).toEqual(["height_px", "image_url", "item_id", "width_px"]);
      expect(item.item_id).toMatch(/^s\d{2}$/);
      expect(item.width_px).toBe(780);
      expect(item.height_px).toBeGreaterThan(200);
      expect(item.image_url).toContain("/forms-deck-2026-11-27/card-");
      ids.add(item.item_id);
      urls.add(item.image_url);
    }
    expect(ids.size).toBe(11);
    expect(urls.size).toBe(11);

    const leaked = [
      ...fs.readdirSync(feDataDir),
      ...fs.readdirSync(beDataDir),
    ].filter((name) => name.includes("2026_11_27") && name.includes("key"));
    expect(leaked).toEqual([]);
  });
});
