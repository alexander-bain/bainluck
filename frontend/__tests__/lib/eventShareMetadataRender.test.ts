/**
 * Q441 (#1495) — the RENDER half.
 *
 * `eventShareMeta.test.ts` proves the copy builder is right. This file proves the
 * event page actually calls it: it drives the real `generateMetadata` export from
 * `app/events/[id]/layout.tsx` with a stubbed fetch and asserts on the Metadata
 * object Next.js would render into `<head>`.
 *
 * The two are not redundant. A pure-lib guard stays green when the render drops
 * the module — which is precisely how the wrong number survived on the page while
 * `resolveProbability` was already honest about finished games.
 */

import { generateMetadata } from "@/app/events/[id]/layout";

const SETTLED_PAYLOAD = {
  id: 15294037,
  home_team: "Villanova Wildcats",
  away_team: "William and Mary Tribe",
  home_score: 32,
  away_score: 35,
  status: "completed",
  commence_time: "2026-08-28T22:00:00Z",
  hero_probability: 0.0,
  hero_probability_away: 1.0,
  hero_probability_source: "settled",
  hero_settled_result: "away",
  current_odds: { home_probability: 0.8199, away_probability: 0.1801 },
};

const SCHEDULED_PAYLOAD = {
  id: 1,
  home_team: "Celtics",
  away_team: "76ers",
  home_score: null,
  away_score: null,
  status: "scheduled",
  commence_time: "2026-09-02T23:00:00Z",
  hero_probability: 0.65,
  hero_probability_source: "blend",
  current_odds: { home_probability: 0.65, away_probability: 0.35 },
};

function stubFetch(payload: unknown, ok = true) {
  global.fetch = jest.fn().mockResolvedValue({
    ok,
    json: async () => payload,
  }) as unknown as typeof fetch;
}

const asText = (v: unknown): string =>
  typeof v === "string" ? v : typeof v === "object" && v !== null && "absolute" in v
    ? String((v as { absolute?: string }).absolute ?? "")
    : String(v ?? "");

afterEach(() => {
  jest.restoreAllMocks();
});

describe("generateMetadata on a settled event", () => {
  it("publishes the winner, not the losing favorite", async () => {
    stubFetch(SETTLED_PAYLOAD);
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15294037" }),
    });

    const title = asText(meta.title);
    const description = asText(meta.description);

    // What production served on 2026-08-29, and must never serve again:
    expect(description).not.toBe(
      "Final. Bain Luck gives Villanova Wildcats a 82% win probability and William and Mary Tribe a 18% win probability.",
    );
    expect(description).not.toMatch(/win probability/);
    expect(description).toContain("William and Mary Tribe beat Villanova Wildcats");
    expect(title).toContain("William and Mary Tribe won");
    expect(title).not.toMatch(/82%/);
  });

  it("carries the result into og: and twitter: as well", async () => {
    stubFetch(SETTLED_PAYLOAD);
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15294037" }),
    });

    const ogTitle = asText(meta.openGraph?.title);
    const twitterTitle = asText(meta.twitter?.title);

    for (const t of [ogTitle, twitterTitle]) {
      expect(t).toContain("William and Mary Tribe won");
      expect(t).not.toMatch(/%/);
      // og:/twitter: bypass the root template, so they carry exactly one suffix
      expect(t.match(/\| Bain Luck/g)).toHaveLength(1);
    }
    expect(asText(meta.openGraph?.description)).not.toMatch(/win probability/);
    expect(asText(meta.twitter?.description)).not.toMatch(/win probability/);
  });

  it("emits no doubled site suffix in the page title", async () => {
    stubFetch(SETTLED_PAYLOAD);
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15294037" }),
    });
    // The root layout template is `%s | Bain Luck`; the page title must add none.
    expect(asText(meta.title)).not.toMatch(/\| Bain Luck/);
  });
});

describe("generateMetadata leaves unsettled events alone", () => {
  it("still publishes the probability copy for a scheduled game", async () => {
    stubFetch(SCHEDULED_PAYLOAD);
    const meta = await generateMetadata({ params: Promise.resolve({ id: "1" }) });

    expect(asText(meta.description)).toContain("win probability");
    expect(asText(meta.title)).toContain("65%");
    expect(asText(meta.title)).not.toMatch(/\| Bain Luck/);
  });

  it("falls back safely when the event cannot be fetched", async () => {
    stubFetch(null, false);
    const meta = await generateMetadata({ params: Promise.resolve({ id: "9" }) });
    expect(asText(meta.title)).toBe("Event Odds - Bain Luck");
  });
});
