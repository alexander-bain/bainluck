/**
 * Decision 386: A (#12221 Item 9) — Frontend unit & SSR checks for KitContainerPageView
 * and /admin/containers-kit-preview.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/admin/containers-kit-preview",
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

import {
  KitContainerPageView,
  type KitContainerPageSpec,
} from "@/components/collections/KitContainerPageView";
import AdminContainersKitPreviewPage from "@/app/admin/containers-kit-preview/page";

const SAMPLE_PAGE: KitContainerPageSpec = {
  kit_page_version: 1,
  state: "preview",
  slug: "global-policy-rates",
  title: "Policy Rates",
  kicker: "ECONOMICS",
  caption: "3 disjoint views across 8 live markets",
  snapshot_captured_at: "2026-11-24T22:06:28+00:00",
  market_count: 8,
  section_count: 3,
  variants: ["scoreboard_grid", "shared_scale", "one_in_n"],
  sections: [
    {
      kit_version: 1,
      id: "rates-grid",
      layout: "grid",
      variant: "scoreboard_grid",
      kicker: "ECONOMICS · MEETINGS",
      common_headline: "Central Bank Decisions",
      stat_caption: "A +25 bp hike leads Dec '26 Meeting at 92%",
      source_mark: { label: "2 sources", count: 2 },
      refusal_reason: null,
      body: {
        leading_label: "Meeting",
        show_column_headers: true,
        row_layout: "matrix",
        columns: [
          { key: "plus_25", label: "+25 bp" },
          { key: "hold", label: "Hold" },
        ],
        rows: [
          {
            id: "policy-1",
            leading: [
              { mark: "word", text: "Dec '26 Meeting", style: "row", tone: "primary", align: "left", width: "flex", bold: true },
            ],
            cells: [
              {
                column_key: "plus_25",
                marks: [{ mark: "tile", shade: 0.92, center_label: "92%" }],
              },
              {
                column_key: "hold",
                marks: [{ mark: "tile", shade: 0.04, center_label: "4%", muted: true }],
              },
            ],
          },
        ],
      },
    },
    {
      kit_version: 1,
      id: "rates-scale",
      layout: "axis",
      variant: "shared_scale",
      kicker: "ECONOMICS · MACRO RISK",
      common_headline: "Recession Odds",
      stat_caption: "US recession by end of 2027 leads at 40%",
      source_mark: { label: "2 sources", count: 2 },
      refusal_reason: null,
      body: {
        scale: {
          scale_kind: "percent",
          unit: "%",
          min: 0,
          max: 100,
          ticks: [
            { x: 0, label: "0%" },
            { x: 50, label: "50%" },
            { x: 100, label: "100%" },
          ],
        },
        series: [
          {
            id: "recess-us",
            leading: [
              { mark: "word", text: "US recession by end of 2027", style: "row", tone: "primary", align: "left", width: "flex", bold: true },
            ],
            marks: [
              { mark: "bar", bar_style: "single", fill: 0.4, width: "flex" },
              { mark: "number", value: 40, display: "40%", unit: "%", tone: "primary", prominence: "primary", align: "right", width: "sm" },
            ],
          },
        ],
      },
    },
    {
      kit_version: 1,
      id: "rates-oin",
      layout: "stack",
      variant: "one_in_n",
      kicker: "ECONOMICS · OUTLIERS",
      common_headline: "Macro Tail Risks",
      stat_caption: "Governor leaves central bank board carries a 1 in 11 (9%) chance",
      source_mark: { label: "2 sources", count: 2 },
      refusal_reason: null,
      body: {
        header_layout: "none",
        header_marks: [],
        items: [
          {
            id: "oin-1",
            marks: [
              { mark: "word", text: "Governor leaves central bank board", style: "row", tone: "primary", align: "left", width: "flex" },
              { mark: "number", value: 11, display: "1 in 11", unit: "one_in_n", tone: "accent", prominence: "primary", align: "right", width: "auto" },
              { mark: "number", value: 9, display: "9%", unit: "%", tone: "muted", prominence: "secondary", align: "right", width: "auto" },
            ],
          },
        ],
      },
    },
  ],
};

describe("Item 9 KitContainerPageView & preview page", () => {
  test("renders preview header, declarative section headlines, and all 3 kit sections in light and dark modes", () => {
    const lightHtml = renderToStaticMarkup(
      <KitContainerPageView page={SAMPLE_PAGE} surfaceScheme="light" />,
    );
    const darkHtml = renderToStaticMarkup(
      <KitContainerPageView page={SAMPLE_PAGE} surfaceScheme="dark" />,
    );

    for (const html of [lightHtml, darkHtml]) {
      expect(html).toContain("Policy Rates");
      expect(html).toContain("preview · 3 sections");
      expect(html).toContain("Central Bank Decisions");
      expect(html).toContain("Recession Odds");
      expect(html).toContain("Macro Tail Risks");
      expect(html).toContain("1 in 11");
      expect(html).not.toContain("Standard card fallback");
    }

    const cleanHtml = renderToStaticMarkup(
      <KitContainerPageView page={SAMPLE_PAGE} surfaceScheme="light" showDebugMeta={false} />,
    );
    expect(cleanHtml).toContain("Policy Rates");
    expect(cleanHtml).toContain("Central Bank Decisions");
    expect(cleanHtml).toContain("1 in 11");
    expect(cleanHtml).not.toContain("scoreboard_grid");
    expect(cleanHtml).not.toContain("shared_scale");
    expect(cleanHtml).not.toContain("one_in_n");
  });

  test("TSX components use light semantic classes only (zero dark: classes or hex literals)", () => {
    const compSrc = fs.readFileSync(
      path.join(process.cwd(), "components", "collections", "KitContainerPageView.tsx"),
      "utf-8",
    );
    const pageSrc = fs.readFileSync(
      path.join(process.cwd(), "app", "admin", "containers-kit-preview", "page.tsx"),
      "utf-8",
    );
    for (const src of [compSrc, pageSrc]) {
      expect(src).not.toMatch(/\bdark:/);
      expect(src).not.toMatch(/#[0-9A-Fa-f]{6}/);
    }
    const pageHtml = renderToStaticMarkup(<AdminContainersKitPreviewPage />);
    expect(pageHtml).toContain("Kit Container Pages Preview (#12221 Item 9)");
  });
});
