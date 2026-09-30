jest.mock("@/components/collections/CollectionPageClient", () => ({ __esModule: true, default: () => null }));
jest.mock("@/lib/collections", () => ({ ...jest.requireActual("@/lib/collections"), fetchCollection: jest.fn() }));

import { generateMetadata } from "@/app/collections/[slug]/page";
import { fetchCollection, parseCollection } from "@/lib/collections";
import { nflHub } from "./fixtures";

const read = jest.mocked(fetchCollection);
const params = { slug: "nfl-2026-week-4" };

describe("a shared collection has its own fresh public identity", () => {
  beforeEach(() => read.mockReset());
  test("published edition names itself and its canonical URL", async () => {
    read.mockResolvedValue(parseCollection(nflHub(), params.slug));
    const metadata = await generateMetadata({ params });
    expect(metadata.title).toBe("NFL Week 4");
    expect(metadata.description).toContain("NFL · 2026 · Regular Season · Week 4");
    expect(metadata.alternates?.canonical).toBe("/collections/nfl-2026-week-4");
    expect(metadata.openGraph).toMatchObject({ url: "/collections/nfl-2026-week-4", title: "NFL Week 4 | Bain Luck" });
    expect(metadata.openGraph).toMatchObject({ images: [{ url: "/collections/nfl-2026-week-4/opengraph-image" }] });
    expect(metadata.twitter).toMatchObject({ images: [{ url: "/collections/nfl-2026-week-4/opengraph-image" }] });
    expect(metadata.robots).toBeUndefined();
    expect(read.mock.calls[0][1]).toBeInstanceOf(AbortSignal);
  });
  test("withdrawal does not leak the old published title", async () => {
    read.mockResolvedValue(parseCollection({ ...nflHub(), state: "withdrawn" }, params.slug));
    const metadata = await generateMetadata({ params });
    expect(metadata.title).toBe("Collection");
    expect(metadata.description).toContain("no longer available");
    expect(metadata.robots).toEqual({ index: false, follow: true });
  });
  test("transient failure stays retryable without asserting absence", async () => {
    read.mockRejectedValue(new Error("503"));
    const metadata = await generateMetadata({ params });
    expect(metadata.description).toContain("temporarily unavailable");
    expect(metadata.robots).toBeUndefined();
  });
  test("invalid slug never reaches the public fetch or emits an unsafe canonical", async () => {
    const metadata = await generateMetadata({ params: { slug: "../other" } });
    expect(read).not.toHaveBeenCalled();
    expect(metadata.alternates).toBeUndefined();
    expect(metadata.robots).toEqual({ index: false, follow: true });
  });
});
