/** @jest-environment jsdom */
import { TextDecoder, TextEncoder } from "util";
Object.assign(globalThis, { TextEncoder, TextDecoder });

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import CollectionHub from "@/components/collections/CollectionHub";
import type { CollectionHub as Hub } from "@/lib/collections";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/collections/machinery-who-gets-engaged",
  useSearchParams: () => new URLSearchParams(),
}));

const mockFetchCollection = jest.fn();
jest.mock("@/lib/collections", () => {
  const actual = jest.requireActual("@/lib/collections");
  return {
    ...actual,
    fetchCollection: (...args: unknown[]) => mockFetchCollection(...args),
  };
});

describe("CollectionHub document.title sync", () => {
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
    mockFetchCollection.mockReset();
    document.title = "";
  });

  it("updates document.title from fallback 'Collection' once the hub loads client-side", async () => {
    document.title = "Collection | Bain Luck";

    const loadedHub: Hub = {
      slug: "machinery-who-gets-engaged",
      revision: 1,
      state: "published",
      title: "Who Gets Engaged?",
      edition: null,
      sections: [],
      children: [],
      members: [],
      related: {},
      note: null,
      dek: "Chance each couple is engaged by Dec 31, 2026.",
      family: null,
      theme: null,
    };
    mockFetchCollection.mockResolvedValue(loadedHub);

    const container = document.createElement("div");
    document.body.appendChild(container);
    let root: Root | null = null;

    try {
      await act(async () => {
        root = createRoot(container);
        root.render(<CollectionHub slug="machinery-who-gets-engaged" initialHub={null} />);
      });

      expect(document.title).toBe("Who Gets Engaged? | Bain Luck");
    } finally {
      await act(async () => {
        root?.unmount();
      });
      container.remove();
    }
  });
});
