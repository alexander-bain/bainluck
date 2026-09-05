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

/**
 * CERT-1938's block, END TO END — the shape the unit tests cannot reach.
 *
 * The lib guard proves `buildEventShareCopy` words a tournament outcome correctly.
 * It stays green even if the layout never fetches the container, which is exactly
 * how 15293846 shipped a forecast while the page beside it knew the score. This
 * drives the real `generateMetadata` with BOTH routes stubbed.
 *
 * Payloads are the production shapes read on 2026-09-05 from
 * `/api/events/15293846` and `/api/tournaments/by-event/15293846`.
 */
const BERRETTINI_EVENT = {
  id: 15293846,
  home_team: "Matteo Berrettini",
  away_team: "Stan Wawrinka",
  home_score: 3,
  away_score: 0,
  status: "closed",
  sport: "tennis_atp_us_open",
  commence_time: "2026-08-30T18:00:00Z",
  completed_at: "2026-08-30T20:25:53.487618+00:00",
  hero_probability: 0.8411,
  hero_probability_away: 0.1589,
  // The row still carries the blend, which is the whole defect.
  hero_probability_source: "blend",
  current_odds: { home_probability: 0.8411, away_probability: 0.1589 },
  linescore: { sets: [[7, 6], [7, 6], [6, 0]], source: "espn" },
};

const BERRETTINI_TOURNAMENT = {
  event_id: 15293846,
  tournament: { slug: "us-open", title: "US Open 2026", url: "/tournaments/us-open" },
  matchup_key: "mens-singles:matteo-berrettini-vs-stan-wawrinka:2026-08-30",
  result: {
    matchup_key: "mens-singles:matteo-berrettini-vs-stan-wawrinka:2026-08-30",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    players: [
      { entity_key: "stan-wawrinka", display_name: "Stan Wawrinka", is_winner: false },
      { entity_key: "matteo-berrettini", display_name: "Matteo Berrettini", is_winner: true },
    ],
    winner_entity_key: "matteo-berrettini",
    score: "7-6, 7-6, 6-0",
    completion: "final",
    completed_at: "2026-08-30T20:25:53Z",
    source_round: "1st Round",
    source: "espn",
  },
};

/** Routes by URL, so the test can prove WHICH endpoints the layout asked. */
function stubFetchByUrl(routes: Record<string, unknown>, calls?: string[]) {
  global.fetch = jest.fn(async (input: unknown) => {
    const url = String(input);
    calls?.push(url);
    const hit = Object.entries(routes).find(([fragment]) => url.includes(fragment));
    if (!hit) return { ok: false, json: async () => ({}) };
    return { ok: true, json: async () => hit[1] };
  }) as unknown as typeof fetch;
}

describe("generateMetadata on a decided match with no trusted score (CERT-1938)", () => {
  it("publishes the winner and the set line, not the 84% the row still carries", async () => {
    stubFetchByUrl({
      "/api/tournaments/by-event/15293846": BERRETTINI_TOURNAMENT,
      "/api/events/15293846": BERRETTINI_EVENT,
    });
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15293846" }),
    });

    expect(asText(meta.title)).toBe(
      "Stan Wawrinka vs Matteo Berrettini: Matteo Berrettini won 7-6, 7-6, 6-0",
    );
    expect(meta.description).toBe(
      "Final: Matteo Berrettini beat Stan Wawrinka 7-6, 7-6, 6-0.",
    );
    // The exact defect string production served on 2026-09-05.
    expect(asText(meta.title)).not.toMatch(/84%|16%/);
    expect(meta.description).not.toMatch(/win probability/);
  });

  it("carries the result into og: and twitter:, with exactly one site suffix", async () => {
    stubFetchByUrl({
      "/api/tournaments/by-event/15293846": BERRETTINI_TOURNAMENT,
      "/api/events/15293846": BERRETTINI_EVENT,
    });
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15293846" }),
    });

    for (const social of [asText(meta.openGraph?.title), asText(meta.twitter?.title)]) {
      expect(social).toContain("Matteo Berrettini won 7-6, 7-6, 6-0");
      expect(social.match(/\| Bain Luck/g)).toHaveLength(1);
    }
    // The page title itself takes its suffix from the root template.
    expect(asText(meta.title)).not.toMatch(/\| Bain Luck/);
  });

  it("actually ASKS the container — the fetch the lib guard cannot see", async () => {
    const calls: string[] = [];
    stubFetchByUrl(
      {
        "/api/tournaments/by-event/15293846": BERRETTINI_TOURNAMENT,
        "/api/events/15293846": BERRETTINI_EVENT,
      },
      calls,
    );
    await generateMetadata({ params: Promise.resolve({ id: "15293846" }) });
    expect(calls.some((u) => u.includes("/api/tournaments/by-event/15293846"))).toBe(true);
  });
});

describe("the no-authority control — finished, and nothing names a winner", () => {
  it("says Final and publishes no probability when the container has no result", async () => {
    stubFetchByUrl({
      "/api/tournaments/by-event/15293846": { ...BERRETTINI_TOURNAMENT, result: null },
      "/api/events/15293846": BERRETTINI_EVENT,
    });
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15293846" }),
    });

    expect(asText(meta.title)).toBe("Stan Wawrinka vs Matteo Berrettini: Final");
    expect(meta.description).not.toMatch(/\d+%/);
    expect(meta.description).toContain("does not have a confirmed result");
  });

  it("does NOT crown from the untrusted `closed` scores when the container 404s", async () => {
    // The row says 3-0. `closed` scores are frozen mid-game and invert the winner
    // in 2 of 8 sampled rows, so a failed container read must fall to "Final",
    // never to "Berrettini won 3-0".
    stubFetchByUrl({ "/api/events/15293846": BERRETTINI_EVENT });
    const meta = await generateMetadata({
      params: Promise.resolve({ id: "15293846" }),
    });

    expect(asText(meta.title)).toBe("Stan Wawrinka vs Matteo Berrettini: Final");
    expect(asText(meta.title)).not.toContain("3-0");
    expect(meta.description).not.toMatch(/\d+%/);
  });

  it("a non-tournament sport never pays for the container lookup", async () => {
    const calls: string[] = [];
    stubFetchByUrl({ "/api/events/15294037": SETTLED_PAYLOAD }, calls);
    await generateMetadata({ params: Promise.resolve({ id: "15294037" }) });
    expect(calls.some((u) => u.includes("/api/tournaments/by-event"))).toBe(false);
  });
});
