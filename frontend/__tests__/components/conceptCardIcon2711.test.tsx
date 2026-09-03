// UX-1035 / #2711 — THE CONCEPT CARD RENDERS THE RIGHT ICON.
//
// What a reader saw, measured on production 2026-09-02 at phone width: the
// Vuelta a España card read "🥊 CYCLING" and the Dutch Grand Prix card read
// "🥊 F1". `components/FeedCard.tsx` hardcoded 🥊 in its concept arm and printed
// `data.domain?.toUpperCase()` immediately beside it, so the icon and the label
// on the same line disagreed with each other. The component was written for UFC
// and boxing cards and was never generalised when the cycling, F1 and golf
// concept adapters shipped.
//
// THIS FILE RENDERS, and that is the point. `conceptDomainIcon2711.test.ts`
// exercises the helper, and it would stay green forever if the card never
// called it — which is precisely the state that shipped. A helper is not a fix
// until the render reaches it.
//
// The cards below are the payload production served, not an invented shape:
// three of the fourteen concept items from
// `GET /api/feed?mode=sports&limit=200`, banked whole at
// `__tests__/fixtures/conceptCards2711.json`.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "fs";
import path from "path";
import type { FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";

const FIXTURE = path.join(__dirname, "..", "fixtures", "conceptCards2711.json");
const banked: { items: FeedItem[] } = JSON.parse(
  fs.readFileSync(FIXTURE, "utf8"),
);

const byName = (name: string): FeedItem => {
  const found = banked.items.find(
    (i) => (i.data as { name?: string }).name === name,
  );
  if (!found) throw new Error(`fixture is missing the concept card "${name}"`);
  return found;
};

const html = (item: FeedItem): string =>
  renderToStaticMarkup(<FeedCard item={item} />);

const GLOVE = "🥊";

describe("#2711 — the rendered concept card", () => {
  it("🔴 no longer draws a boxing glove over a bike race", () => {
    const out = html(byName("Vuelta a España 2026"));
    expect(out).toContain("CYCLING");
    expect(out).not.toContain(GLOVE);
    expect(out).toContain("🚴");
  });

  it("🔴 no longer draws a boxing glove over a Grand Prix", () => {
    const out = html(byName("Dutch Grand Prix Winner"));
    expect(out).toContain("F1");
    expect(out).not.toContain(GLOVE);
    expect(out).toContain("🏎");
  });

  it("🟢 the control: a UFC card still draws the glove", () => {
    // The card the icon was RIGHT for. A fix that took it away from combat
    // cards would be a regression wearing a repair's clothes — and it is the
    // arm that proves `not.toContain(GLOVE)` above is discriminating rather
    // than a card that renders no icon at all.
    const ufc = banked.items.find(
      (i) => (i.data as { domain?: string }).domain === "ufc",
    );
    expect(ufc).toBeDefined();
    expect(html(ufc!)).toContain(GLOVE);
  });

  it("every banked concept card renders an icon that matches its own label", () => {
    // The sweep, over the real payload rather than three chosen rows. The icon
    // and the domain text sit on the same line; this asserts they agree for all
    // fourteen.
    const expected: Record<string, string> = {
      cycling: "🚴",
      f1: "🏎",
      ufc: GLOVE,
    };
    for (const item of banked.items) {
      const { domain, name } = item.data as { domain: string; name: string };
      const out = html(item);
      expect(expected[domain]).toBeDefined();
      expect(`${name} -> ${out.includes(expected[domain])}`).toBe(
        `${name} -> true`,
      );
    }
  });
});
