/** @jest-environment jsdom */
import React from "react";
import { TextEncoder, TextDecoder } from "util";
if (typeof globalThis.TextEncoder === "undefined") {
  Object.assign(globalThis, { TextEncoder, TextDecoder });
}
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

jest.mock("@/lib/api", () => ({
  API_URL: "http://fixture.invalid",
  fetchPairedMetricsByCeremony: jest.fn(async () => ({ sets: [] })),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));
jest.mock("@/components/collections/CollectionMemberCard", () => ({
  CollectionMemberCard: ({ member }: { member: { href: string; key: string } }) => (
    <a href={member.href} data-testid={`member-${member.key}`}>{member.key}</a>
  ),
}));

import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection } from "@/lib/collections";
import { nflHub } from "./fixtures";

describe("#13103 — Shared set SSR landing and stranger-first header", () => {
  let root: Root;
  let element: HTMLDivElement;

  beforeEach(() => {
    (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    forgetAcceptedCollections();
    sessionStorage.clear();
    element = document.createElement("div");
    document.body.append(element);
    root = createRoot(element);
  });

  afterEach(() => {
    act(() => root.unmount());
    element.remove();
    forgetAcceptedCollections();
  });

  const makePublishedHub = (slug = "nfl-2026-week-4") => {
    const base = nflHub();
    const body = {
      ...base,
      slug,
      container: { ...base.container, slug, name: "NFL Week 4 — Headline Slate" },
    };
    const hub = {
      ...parseCollection(body, slug),
      dek: "Odds across every Week 4 game as of today.",
    };
    return { body, hub };
  };

  it("renders title, one-line reason, and first rows in static SSR HTML with zero loading text", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { renderToStaticMarkup } = require("react-dom/server") as typeof import("react-dom/server");
    const slug = "nfl-2026-week-4";
    const { hub } = makePublishedHub(slug);

    const html = renderToStaticMarkup(<CollectionHub slug={slug} initialHub={hub} />);
    expect(html).not.toContain("Loading collection");
    expect(html).not.toContain("Back to Discover");
    expect(html).toContain("NFL Week 4 — Headline Slate");
    expect(html).toContain("Odds across every Week 4 game as of today.");
    expect(html).toContain("Explore Discover");
    expect(html).toContain("Get the iPhone App");

    // Top header has no "COLLECTION" eyebrow and no top "Refresh" button.
    const headerMatch = html.match(/<header[^>]*data-collection-header[^>]*>([\s\S]*?)<\/header>/);
    expect(headerMatch).not.toBeNull();
    expect(headerMatch![1]).not.toContain(">Collection<");
    expect(headerMatch![1]).not.toContain("Refresh");
    expect(headerMatch![1]).not.toContain("Back to Discover");
    // One-line reason sits directly after the h1 title.
    expect(headerMatch![1].indexOf("collection-title")).toBeLessThan(headerMatch![1].indexOf("data-collection-dek"));
  });

  it("skips redundant initial client fetch when mounted with a published SSR hub", async () => {
    const slug = "nfl-2026-week-4";
    const { body, hub } = makePublishedHub(slug);
    const fetchMock = jest.fn(async (_url?: unknown) => ({ ok: true, status: 200, json: async () => body }));
    global.fetch = fetchMock as unknown as typeof fetch;

    await act(async () => {
      root.render(<CollectionHub slug={slug} initialHub={hub} />);
    });

    expect(element.textContent).not.toContain("Loading collection");
    expect(element.querySelectorAll("[data-collection-member]")).toHaveLength(5);
    const containerCalls = fetchMock.mock.calls.filter((args) => String(args[0] ?? "").endsWith(`/api/containers/${slug}`));
    expect(containerCalls).toHaveLength(0);
  });

  it("hides the iPhone App Store CTA on Android user agents while keeping Explore Discover", async () => {
    const origUA = navigator.userAgent;
    Object.defineProperty(navigator, "userAgent", {
      value: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36",
      configurable: true,
    });
    try {
      const slug = "nfl-2026-week-4";
      const { hub } = makePublishedHub(slug);
      await act(async () => {
        root.render(<CollectionHub slug={slug} initialHub={hub} />);
      });
      expect(element.querySelector("[data-collection-app-cta]")).toBeNull();
      expect(element.querySelector("[data-collection-discover-cta]")?.textContent).toContain("Explore Discover");
    } finally {
      Object.defineProperty(navigator, "userAgent", { value: origUA, configurable: true });
    }
  });
});
