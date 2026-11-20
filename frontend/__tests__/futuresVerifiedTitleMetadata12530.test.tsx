/** #12530: page titles and share images read the same board as the page. */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockImages: React.ReactElement[] = [];
jest.mock("next/og", () => ({
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImages.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import { generateMetadata } from "@/app/futures/[id]/layout";
import FuturesImage from "@/app/futures/[id]/opengraph-image";

// The Nov 11 served board's first three values. The source-mode control is
// deliberately led by Buffalo, as the alias's old browser title was.
function board(id: number, verified: boolean) {
  return {
    id,
    name: "2027 Super Bowl Winner",
    status: "open",
    representation: verified ? "verified_title" : "source",
    mutually_exclusive: true,
    lead_outcome_id: null,
    outcomes: [
      { id: 1, name: "Buffalo Bills", probability: verified ? 0.12956302 : 0.145 },
      { id: 2, name: "San Francisco 49ers", probability: verified ? 0.13484151 : 0.129 },
      { id: 3, name: "Chicago Bears", probability: verified ? 0.10509 : 0.1 },
    ],
  };
}

function servedBoards(id: number, refuse = false) {
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    const verified = url.searchParams.get("representation") === "verified_title" && !refuse;
    return { ok: true, status: 200, json: async () => board(id, verified) } as Response;
  }) as jest.MockedFunction<typeof fetch>;
}

beforeEach(() => { mockImages.length = 0; });

describe.each([86832, 129037, 40533])("verified Super Bowl alias %s", (id) => {
  it("names the verified favourite and number in browser, OG and Twitter metadata", async () => {
    servedBoards(id);
    const metadata = await generateMetadata({ params: Promise.resolve({ id: String(id) }) });
    expect(metadata.title).toBe("San Francisco 49ers 13% - 2027 Super Bowl Winner");
    expect(metadata.openGraph?.title).toBe(`${metadata.title} | Bain Luck`);
    expect(metadata.twitter?.title).toBe(`${metadata.title} | Bain Luck`);
    expect(metadata.description).toMatch(/^San Francisco 49ers 13%, Buffalo Bills 13%, Chicago Bears 11%\./);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/futures/${id}?representation=verified_title`),
      { next: { revalidate: 60 } },
    );
  });

  it("draws the same favourite and number in the actual share image", async () => {
    servedBoards(id);
    await FuturesImage({ params: { id: String(id) } });
    expect(mockImages).toHaveLength(1);
    const html = renderToStaticMarkup(mockImages[0]);
    expect(html).toContain("San Francisco 49ers");
    expect(html).toContain("13%");
    expect(html).not.toContain("15%");
    expect(html).not.toContain("Buffalo Bills");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/futures/${id}?representation=verified_title`),
      { next: { revalidate: 60 } },
    );
  });
});

it("keeps the server's source answer when verified composition refuses", async () => {
  servedBoards(40533, true);
  const metadata = await generateMetadata({ params: Promise.resolve({ id: "40533" }) });
  await FuturesImage({ params: { id: "40533" } });
  expect(metadata.title).toBe("Buffalo Bills 15% - 2027 Super Bowl Winner");
  const html = renderToStaticMarkup(mockImages[0]);
  expect(html).toContain("Buffalo Bills");
  expect(html).toContain("15%");
});
