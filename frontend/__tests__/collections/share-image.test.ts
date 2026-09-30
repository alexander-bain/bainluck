jest.mock("next/og", () => ({ ImageResponse: jest.fn((element, size) => ({ element, size })) }));
jest.mock("@/lib/collections", () => ({ ...jest.requireActual("@/lib/collections"), fetchCollection: jest.fn() }));

import { ImageResponse } from "next/og";
import Image from "@/app/collections/[slug]/opengraph-image";
import { fetchCollection, parseCollection } from "@/lib/collections";
import { accentFor } from "@/components/og/UnfurlCard";
import { UNFURL_CACHE_MOVING } from "@/lib/unfurlImageCache";
import { nflHub, mlbHub } from "./fixtures";

const read = jest.mocked(fetchCollection);
const response = jest.mocked(ImageResponse);
async function imageProps(slug: string) {
  await Image({ params: Promise.resolve({ slug }) });
  return (response.mock.calls[response.mock.calls.length - 1][0] as { props: Record<string, unknown> }).props;
}

describe("collection share image names its public edition without inventing a probability", () => {
  beforeEach(() => { read.mockReset(); response.mockClear(); });
  test("NFL and MLB use their supplied collection name, edition and sport", async () => {
    for (const [fixture, category] of [[nflHub(), "football"], [mlbHub(), "baseball"]] as const) {
      const hub = parseCollection(fixture, fixture.slug);
      read.mockResolvedValue(hub);
      expect(await imageProps(fixture.slug)).toMatchObject({ title: hub.title, subtitle: hub.edition, rows: [], accent: accentFor(category), verdict: hub.note ?? "Explore games, results and related questions." });
    }
    expect(response.mock.calls[0][1]).toEqual({ width: 1200, height: 630, headers: { "cache-control": UNFURL_CACHE_MOVING } });
  });
  test("withdrawal drops the old name, edition and member facts", async () => {
    const raw = nflHub();
    read.mockResolvedValue(parseCollection({ ...raw, state: "withdrawn" }, raw.slug));
    expect(await imageProps(raw.slug)).toMatchObject({ title: "Collection", subtitle: null, rows: [], verdict: "This collection is no longer available." });
  });
  test("transient failure stays unavailable without asserting absence or a fake result", async () => {
    read.mockRejectedValue(new Error("503"));
    expect(await imageProps("nfl-2026-week-4")).toMatchObject({ title: "Collection", rows: [], verdict: "This collection is temporarily unavailable." });
  });
});
