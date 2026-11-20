/** @jest-environment jsdom */
import { TextDecoder, TextEncoder } from "util";
Object.assign(globalThis, { TextEncoder, TextDecoder });

import React, { act } from "react";
import { hydrateRoot, type Root } from "react-dom/client";
import { AsOfStamp } from "@/components/AsOfStamp";
import { formatAsOfStamp } from "@/lib/asOfStamp";
import CollectionHub from "@/components/collections/CollectionHub";
import type { CollectionHub as Hub } from "@/lib/collections";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { renderToString } = require("react-dom/server") as typeof import("react-dom/server");

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

// Mock Next.js router/navigation hooks used by CollectionHub
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/collections/machinery-fed-and-macro",
  useSearchParams: () => new URLSearchParams(),
}));

describe("#13203: AsOfStamp never bakes server UTC clock into SSR HTML", () => {
  const originalConsoleError = console.error;

  beforeAll(() => {
    Object.defineProperty(global, "IntersectionObserver", {
      writable: true,
      configurable: true,
      value: class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    });
  });

  afterEach(() => {
    console.error = originalConsoleError;
    jest.restoreAllMocks();
  });

  it("respects the caller's time zone for both clock time and same-day boundary", () => {
    // 2026-11-20T15:04:00Z is 3:04 PM UTC and 7:04 AM Pacific
    const nowSameDay = new Date("2026-11-20T15:04:30Z");
    expect(formatAsOfStamp("2026-11-20T15:04:00Z", nowSameDay, "UTC")).toBe(
      "As of 3:04 PM",
    );
    expect(
      formatAsOfStamp("2026-11-20T15:04:00Z", nowSameDay, "America/Los_Angeles"),
    ).toBe("As of 7:04 AM");

    // Late Pacific afternoon crossing UTC midnight:
    // 2026-11-20T23:00:00Z (3:00 PM PT Nov 20) vs 2026-11-21T01:30:00Z (5:30 PM PT Nov 20)
    // In UTC these are different days (Nov 20 vs Nov 21), in Pacific the same day (Nov 20).
    const pacificEveningNow = new Date("2026-11-21T01:30:00Z");
    expect(
      formatAsOfStamp(
        "2026-11-20T23:00:00Z",
        pacificEveningNow,
        "America/Los_Angeles",
      ),
    ).toBe("As of 3:00 PM");
    expect(formatAsOfStamp("2026-11-20T23:00:00Z", pacificEveningNow, "UTC")).toBe(
      "As of Nov 20",
    );
  });

  it("renders nothing on a UTC server and populates the browser's Pacific time on hydration", () => {
    const errors: string[] = [];
    console.error = (...args: unknown[]) => {
      errors.push(args.map(String).join(" "));
    };

    const iso = "2026-11-20T15:04:00Z";
    const now = new Date("2026-11-20T15:04:30Z");

    // 1. Server pass in UTC: must NOT emit "3:04 PM" or any "As of" text
    const serverHtml = renderToString(
      <div>
        <span>Lead 57%</span>
        <AsOfStamp iso={iso} prefix=" · " now={now} timeZone="UTC" />
      </div>,
    );
    expect(serverHtml).not.toContain("3:04 PM");
    expect(serverHtml).not.toContain("As of");

    // 2. Browser hydration in Pacific time: browser's "7:04 AM" must win with zero hydration warnings
    const container = document.createElement("div");
    container.innerHTML = serverHtml;
    document.body.appendChild(container);

    let root: Root | null = null;
    act(() => {
      root = hydrateRoot(
        container,
        <div>
          <span>Lead 57%</span>
          <AsOfStamp
            iso={iso}
            prefix=" · "
            now={now}
            timeZone="America/Los_Angeles"
          />
        </div>,
      );
    });

    expect(container.textContent).toContain("As of 7:04 AM");
    expect(container.textContent).not.toContain("3:04 PM");
    expect(errors.filter((e) => /hydrat/i.test(e))).toHaveLength(0);

    act(() => {
      root?.unmount();
    });
    container.remove();
  });

  it("CollectionHub 'More sets worth a look' omits server UTC stamp on SSR and renders browser stamp after hydration", () => {
    const errors: string[] = [];
    console.error = (...args: unknown[]) => {
      errors.push(args.map(String).join(" "));
    };

    // Pin system clock to 7:04:30 AM PT (15:04:30Z) so 15:04:00Z is same-day
    jest.useFakeTimers({ now: new Date("2026-11-20T15:04:30Z") });
    try {
      const iso = "2026-11-20T15:04:00Z";
      const hub = {
        state: "published",
        slug: "machinery-fed-and-macro",
        revision: "rev-1",
        title: "Fed & Macro",
        name: "Fed & Macro",
        kind: "machinery",
        category: "economics",
        caption: null,
        subtitle: null,
        dek: "Key Fed rate expectations.",
        members: [],
        children: [],
        sections: [
          {
            key: "fed-decisions",
            title: "Fed Decisions",
            layout: "list",
            members: [],
          },
        ],
        moreSets: [
          {
            slug: "machinery-oscars-best-picture",
            name: "Oscars 2027",
            href: "/collections/machinery-oscars-best-picture",
            dek: "Best Picture and acting races",
            leadLabel: "Hamnet",
            leadProbability: 0.42,
            leadRenderedPercent: 42,
            memberCount: 5,
            asOf: iso,
          },
        ],
      } as unknown as Hub;

      // Server render under Jest's pinned UTC timezone (TZ=UTC):
      // MUST emit no server UTC timestamp at all.
      const serverHtml = renderToString(
        <CollectionHub slug="machinery-fed-and-macro" initialHub={hub} />,
      );
      expect(serverHtml).toContain("More sets worth a look");
      expect(serverHtml).toContain("Oscars 2027");
      expect(serverHtml).not.toContain("As of");
      expect(serverHtml).not.toContain("3:04 PM");

      // Browser hydration simulating a reader in Pacific time (America/Los_Angeles):
      const RealDTF = Intl.DateTimeFormat;
      jest
        .spyOn(Intl, "DateTimeFormat")
        .mockImplementation((locales, options) => {
          return new RealDTF(locales, {
            ...(options || {}),
            timeZone: options?.timeZone ?? "America/Los_Angeles",
          });
        });

      const container = document.createElement("div");
      container.innerHTML = serverHtml;
      document.body.appendChild(container);

      let root: Root | null = null;
      act(() => {
        root = hydrateRoot(
          container,
          <CollectionHub slug="machinery-fed-and-macro" initialHub={hub} />,
        );
      });

      const moreSetRow = container.querySelector(
        '[data-collection-more-set="machinery-oscars-best-picture"]',
      );
      expect(moreSetRow).not.toBeNull();
      expect(moreSetRow?.textContent).toContain("As of 7:04 AM");
      expect(moreSetRow?.textContent).not.toContain("3:04 PM");
      expect(errors.filter((e) => /hydrat/i.test(e))).toHaveLength(0);

      act(() => {
        root?.unmount();
      });
      container.remove();
    } finally {
      jest.useRealTimers();
    }
  });
});
