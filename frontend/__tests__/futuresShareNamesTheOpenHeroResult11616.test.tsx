/**
 * #11616 O-L3-1 — the shared link names the result the page hero prints.
 *
 * lane1b EARLY-REPAIR-REVIEW-e3de8f84 §6 (O-L3-1), dispositioned under Root's
 * consistency scope: on the exact L3(a) board (open, exclusive; Shai 0.97, Victor
 * a supported `api_settlement` Won) the page heroes "Victor · Won" and the iOS
 * share reads "Victor: Won — …", but the unfurl shared
 *
 *   title        "Shai Gilgeous-Alexander 97% - Hero board"
 *   description  "Shai Gilgeous-Alexander 97%, Victor Wembanyama 95%. …"
 *   picture      "97%" over "Shai Gilgeous-Alexander"
 *
 * — the price leader's forecast as the board's answer, and Victor's result as a
 * 95% chance. The table's highlighted row and the chart seed are labelled
 * prices and are not changed here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockImageResponseCalls: React.ReactElement[] = [];
jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import FuturesOgImage from "@/app/futures/[id]/opengraph-image";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";

type Leg = [name: string, p: number | null, won: boolean, src: string | null];
function board(legs: Leg[], extra: Record<string, unknown> = {}) {
  return {
    id: 11616, name: "Hero board", status: "open", mutually_exclusive: true, source: "kalshi",
    created_at: "2026-09-20T00:00:00+00:00",
    outcomes: legs.map(([name, p, won, src], i) => ({
      id: 500 + i, name, probability: p, rank: i + 1, opening_probability: null,
      probability_change_24h: null, american_odds: null, opening_american_odds: null,
      is_winner: won, resolution_source: src, last_updated: "2026-10-27T12:00:00+00:00",
    })),
    ...extra,
  };
}

function respondWith(body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => body,
  }) as unknown as typeof fetch;
}

async function share(body: unknown) {
  respondWith(body);
  const meta = await futuresMetadata({ params: Promise.resolve({ id: "11616" }) });
  mockImageResponseCalls.length = 0;
  respondWith(body);
  await (FuturesOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: { id: "11616" },
  });
  if (mockImageResponseCalls.length !== 1) throw new Error("expected one picture");
  const picture = renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return { title: String(meta.title), description: String(meta.description), picture };
}

const SHAI: Leg = ["Shai Gilgeous-Alexander", 0.97, false, null];

describe("O-L3-1: an open board's shared link names the hero's result", () => {
  it.each([0.95, null])("Victor Won (price %p): title, description and picture say Victor won", async (p) => {
    const s = await share(board([SHAI, ["Victor Wembanyama", p, true, "api_settlement"]]));
    expect(s.title).toBe("Victor Wembanyama won - Hero board");
    expect(s.description).toBe("Victor Wembanyama won (Hero board). See the full probability board on Bain Luck.");
    expect(s.picture).toContain("Victor Wembanyama WON");
    for (const text of [s.title, s.description, s.picture]) {
      expect(text).not.toMatch(/97%|95%|Shai/);
    }
  });

  it("CONTROL: an open exclusive board without a supported winner still shares its leader", async () => {
    const s = await share(board([SHAI, ["Victor Wembanyama", 0.95, false, null]]));
    expect(s.title).toBe("Shai Gilgeous-Alexander 97% - Hero board");
    expect(s.picture).toMatch(/97%\s+Shai Gilgeous-Alexander/);
  });

  it("CONTROL: a raw winner flag with a null source is a price, not a shared result", async () => {
    const s = await share(board([SHAI, ["Victor Wembanyama", 0.95, true, null]]));
    expect(s.title).toBe("Shai Gilgeous-Alexander 97% - Hero board");
    expect(s.picture).not.toContain("WON");
  });

  it("CONTROL: an independent open board with a live row above 0 shares the live row", async () => {
    const s = await share(
      board([["↑ 4.25%", 0.4, false, null], ["↓ 3.5%", 0.95, true, "api_settlement"]], {
        mutually_exclusive: false,
      }),
    );
    expect(s.picture).not.toContain("WON");
    expect(s.title).not.toMatch(/ won - /);
  });

  it("an independent open board with every live row at 0 shares its supported winner, as its hero", async () => {
    const s = await share(
      board([["↑ 4.25%", 0.0, false, null], ["↓ 3.5%", null, true, "api_settlement"]], {
        mutually_exclusive: false,
      }),
    );
    expect(s.title).toBe("↓ 3.5% won - Hero board");
    expect(s.picture).toContain("↓ 3.5% WON");
  });
});
