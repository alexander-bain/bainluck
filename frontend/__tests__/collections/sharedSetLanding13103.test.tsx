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
    expect(html).not.toContain("Refresh");
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

  it("parses and renders up to two server-picked more_sets with real numbers and dates, filtering invalid entries", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { renderToStaticMarkup } = require("react-dom/server") as typeof import("react-dom/server");
    const slug = "nfl-2026-week-4";
    const { body } = makePublishedHub(slug);
    const bodyWithMoreSets = {
      ...body,
      more_sets: [
        // Self link must be dropped
        {
          slug,
          name: "Self link should drop",
          member_count: 5,
          lead_label: "Bills",
          lead_probability: 0.65,
          as_of: "2026-11-19T18:00:00+00:00",
        },
        // Valid card 1
        {
          slug: "roundup-this-weeks-economic-data",
          name: "This week's economic data",
          dek: "Key inflation and jobs prints this week.",
          category: "economics",
          member_count: 4,
          lead_label: "Fed cuts rates in December",
          lead_probability: 0.72,
          as_of: "2026-11-19T15:30:00+00:00",
          destination: {
            kind: "container",
            slug: "roundup-this-weeks-economic-data",
            web: "/collections/roundup-this-weeks-economic-data",
            api: "/api/containers/roundup-this-weeks-economic-data",
          },
        },
        // Invalid zero-member card must be dropped
        {
          slug: "empty-set",
          name: "Empty Set",
          member_count: 0,
        },
        // Valid card 2
        {
          slug: "roundup-oscars-best-picture",
          name: "Oscars Best Picture",
          dek: "Frontrunners across nomination and win odds.",
          category: "entertainment",
          member_count: 6,
          lead_label: "Anora",
          lead_probability: 0.41,
          as_of: "2026-11-18T12:00:00+00:00",
        },
        // Undated card must be dropped (fail-closed)
        {
          slug: "undated-set",
          name: "Undated Set",
          member_count: 3,
          lead_label: "Someone",
          lead_probability: 0.55,
        },
        // 3rd valid card must be capped at 2
        {
          slug: "roundup-third-set",
          name: "Third Set",
          member_count: 3,
          lead_label: "Leader",
          lead_probability: 0.62,
          as_of: "2026-11-19T19:00:00+00:00",
        },
      ],
    };

    const parsed = parseCollection(bodyWithMoreSets, slug);
    expect(parsed.moreSets).toHaveLength(2);
    expect(parsed.moreSets?.map((s) => s.slug)).toEqual([
      "roundup-this-weeks-economic-data",
      "roundup-oscars-best-picture",
    ]);

    const html = renderToStaticMarkup(<CollectionHub slug={slug} initialHub={parsed} />);
    expect(html).toContain("More sets worth a look");
    expect(html).toContain("This week&#x27;s economic data");
    expect(html).toContain("Fed cuts rates in December");
    expect(html).toContain("72%");
    expect(html).toContain("As of");
    expect(html).toContain("4 markets");
    expect(html).toContain("Oscars Best Picture");
    expect(html).toContain("Anora");
    expect(html).toContain("41%");
    expect(html).toContain("6 markets");
    expect(html).not.toContain("Self link should drop");
    expect(html).not.toContain("Third Set");
    expect(html.indexOf("data-collection-more-sets")).toBeLessThan(
      html.indexOf("data-collection-landing-footer"),
    );
  });

  it("prints lead_rendered_percent when provided and keeps As of on one line", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { renderToStaticMarkup } = require("react-dom/server") as typeof import("react-dom/server");
    const slug = "nfl-2026-week-4";
    const { body } = makePublishedHub(slug);
    const bodyWithRendered = {
      ...body,
      more_sets: [
        {
          slug: "roundup-fed-rate",
          name: "Year-end Fed rate",
          href: "/collections/roundup-fed-rate",
          category: "economics",
          member_count: 3,
          lead_label: "3.50-3.75%",
          lead_probability: 0.874,
          lead_rendered_percent: 88,
          as_of: "2026-11-19T19:45:00+00:00",
        },
      ],
    };
    const parsed = parseCollection(bodyWithRendered, slug);
    expect(parsed.moreSets?.[0]?.leadRenderedPercent).toBe(88);
    const html = renderToStaticMarkup(<CollectionHub slug={slug} initialHub={parsed} />);
    expect(html).toContain("88%");
    expect(html).not.toContain("87%");
    expect(html).toMatch(/class="[^"]*whitespace-nowrap[^"]*"[^>]*>· As of/);
  });
});
