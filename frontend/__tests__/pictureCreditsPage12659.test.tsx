import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import verifiedDiscoverArt from "@/lib/discover/verifiedDiscoverArt.json";

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/picture-credits",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => undefined }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PictureCreditsPage = require("@/app/picture-credits/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const Footer = require("@/components/Footer").default;

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

describe("Picture credits page (#12659 / Ruling 195-A)", () => {
  it("renders every credited entry from the verified art register with picture, author, licence, and source link", () => {
    const expectedCredited = verifiedDiscoverArt.entries.filter(
      (entry) => entry.author && entry.license && entry.source_page,
    );
    expect(expectedCredited.length).toBeGreaterThanOrEqual(27);

    const html = renderToStaticMarkup(React.createElement(PictureCreditsPage));
    expect(html).toContain("<h1");
    expect(html).toContain(">Picture credits</h1>");

    const itemCount = (html.match(/data-testid="picture-credit-item"/g) || []).length;
    expect(itemCount).toBe(expectedCredited.length);

    for (const entry of expectedCredited) {
      expect(html).toContain(`src="${escapeHtml(entry.url)}"`);
      expect(html).toContain(escapeHtml(entry.author ?? ""));
      expect(html).toContain(escapeHtml(entry.license ?? ""));
      expect(html).toContain(`href="${escapeHtml(entry.source_page ?? "")}"`);
    }
  });

  it("links to /picture-credits from both the website Footer and About page", () => {
    const footerHtml = renderToStaticMarkup(React.createElement(Footer));
    expect(footerHtml).toContain('href="/picture-credits"');
    expect(footerHtml).toContain(">Picture credits</a>");

    const aboutSource = fs.readFileSync(
      path.join(__dirname, "..", "app", "about", "page.tsx"),
      "utf-8",
    );
    expect(aboutSource).toContain('href="/picture-credits"');
    expect(aboutSource).toContain("Picture credits");
  });
});
