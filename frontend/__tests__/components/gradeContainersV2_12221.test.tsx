/**
 * Decision 386: A (#12221 Item 10 / Condition 6) — /grade/containers-v2:
 * SSR shell, light-mode token compliance, RankingJudgment VARCHAR guard,
 * and restore helper tests.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/grade/containers-v2",
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

import GradeContainersV2Page from "@/app/grade/containers-v2/page";
import type { KitContainerPageSpec } from "@/components/collections/KitContainerPageView";
import {
  buildContainerV2JudgmentPayload,
  CONTAINERS_V2_ITEM_TYPE,
  CONTAINERS_V2_SURFACE,
  restoreContainerV2Grades,
} from "@/lib/ranking/containersV2Grade12221";

const SAMPLE_DYNAMIC_PAGES: KitContainerPageSpec[] = [
  {
    kit_page_version: 1,
    state: "preview",
    slug: "orbital-research-goals",
    family_fingerprint: "fp-orbital-research",
    title: "Orbital Research",
    kicker: "SCIENCE",
    caption: "3 disjoint views across 8 open markets",
    snapshot_captured_at: "2026-11-24T22:00:00+00:00",
    market_count: 8,
    section_count: 3,
    variants: ["dated_tiles", "shared_scale", "one_in_n"],
    sections: [],
  },
  {
    kit_page_version: 1,
    state: "preview",
    slug: "global-policy-rates",
    family_fingerprint: "fp-policy-rates",
    title: "Policy Rates",
    kicker: "ECONOMICS",
    caption: "3 disjoint views across 10 open markets",
    snapshot_captured_at: "2026-11-24T22:00:00+00:00",
    market_count: 10,
    section_count: 3,
    variants: ["scoreboard_grid", "shared_scale", "countdown"],
    sections: [],
  },
];

describe("Decision 386: A (#12221) — /grade/containers-v2", () => {
  test("renders header copy, light-mode tokens only, and zero Condition 1 hardcoded strings", () => {
    const html = renderToStaticMarkup(React.createElement(GradeContainersV2Page));
    expect(html).toContain("Container pages v2 (#12221)");
    expect(html).toContain("Keep, Fix or Drop each page, with a note.");

    const pageSource = fs.readFileSync(
      path.resolve(__dirname, "../../app/grade/containers-v2/page.tsx"),
      "utf-8",
    );
    expect(pageSource).not.toMatch(/dark:[a-z]/);
    expect(pageSource).not.toMatch(/#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b/);
    expect(pageSource).toContain("usePageTracking");
    expect(pageSource).toContain("useScrollDepth");
    expect(pageSource).toContain("useEngagementTime");
  });

  test("builds POST payloads within RankingJudgment VARCHAR limits for Keep, Fix, and Drop", () => {
    expect(CONTAINERS_V2_SURFACE.length).toBeLessThanOrEqual(50);
    expect(CONTAINERS_V2_ITEM_TYPE.length).toBeLessThanOrEqual(20);

    const ts = "2026-11-25T00:00:00Z";
    for (const [idx, grade] of (["Keep", "Fix", "Drop"] as const).entries()) {
      const targetPage = SAMPLE_DYNAMIC_PAGES[idx % SAMPLE_DYNAMIC_PAGES.length];
      const payload = buildContainerV2JudgmentPayload(targetPage, grade, `Note for ${grade}`, ts);
      expect(payload.surface).toBe("grade_containers_v2");
      expect(payload.surface.length).toBeLessThanOrEqual(50);
      expect(payload.item_type).toBe("kit_container_v2");
      expect(payload.item_type.length).toBeLessThanOrEqual(20);
      expect(payload.label).toBe(grade);
      expect(payload.label.length).toBeLessThanOrEqual(10);
      expect(payload.reviewer.length).toBeLessThanOrEqual(100);
      expect(payload.market_name).toBe(targetPage.slug);
      expect(payload.notes).toBe(`Note for ${grade}`);
      expect(payload.label_metadata.ui_version).toBe(2);
      expect(payload.label_metadata.family_fingerprint).toBe(targetPage.family_fingerprint);
      expect(payload.label_metadata.grade).toBe(grade);
    }
  });

  test("restores newest valid grades per slug while ignoring malformed rows", () => {
    const restored = restoreContainerV2Grades([
      {
        market_name: "orbital-research-goals",
        label: "Keep",
        notes: "Strong three-view contrast",
        created_at: "2026-11-25T01:00:00Z",
        label_metadata: {
          ui_version: 2,
          slug: "orbital-research-goals",
          grade: "Keep",
          note: "Strong three-view contrast",
          timestamp: "2026-11-25T01:00:00Z",
        },
      },
      {
        market_name: "orbital-research-goals",
        label: "Fix",
        notes: "Older save that should not overwrite newest",
        created_at: "2026-11-25T00:10:00Z",
      },
      {
        market_name: "bad-row",
        label: "Invalid",
        notes: "Should be ignored",
      },
    ]);

    expect(Object.keys(restored)).toEqual(["orbital-research-goals"]);
    expect(restored["orbital-research-goals"]).toEqual({
      grade: "Keep",
      note: "Strong three-view contrast",
      updated_at: "2026-11-25T01:00:00Z",
    });
  });
});
