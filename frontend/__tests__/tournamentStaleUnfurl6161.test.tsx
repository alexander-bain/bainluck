/**
 * #6161 — A US OPEN UNFURL PICTURE STOPS PUBLISHING A WEEK-OLD FORECAST WHILE
 * THE WORDS BESIDE IT CORRECTLY SAY NOTHING.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION ═══
 *
 * 2026-09-14 13:29Z, one minute after an unrelated deploy. A pasted
 * `/tournaments/us-open` link unfurled with a picture naming two leaders and
 * two probabilities for a tournament both had already won:
 *
 *   card    "Alexander Zverev 59% (Men's Singles) ·
 *            Elena Rybakina 99% (Women's Singles) · 2 draws tracked"      ❌
 *   words   "US Open 2026 — Flushing Meadows…"  (correctly numberless)    ✅
 *
 * Read in the SAME MINUTE, `GET /api/tournaments/us-open?sections=first`
 * (`generated_at` 2026-09-14T13:27:25Z) served both boards `decided` with zero
 * priced rows. The card was not mis-reading that payload. It was reading a
 * different, older one:
 *
 *   first three fetches   36,415 bytes   HIT    md5 5811b80c…   ❌ the forecast
 *   fourth, ~3 min later  18,540 bytes   MISS   md5 36f73b50…   ✅ quiet card
 *
 * ═══ 🔴 WHY THIS IS NOT FIXED WITH `decided` ═══
 *
 * That is the issue's own preferred reading, and `inertness` below pins why it
 * would change nothing. `apply_final_result` (`tournament_board.py:1033`)
 * settles every row through `_settle_row` — `probability: None` — and only then
 * writes `board.decided`, so a decided board is an unpriced board and
 * `boardLeader`'s null-price exit already withholds it. Measured on production:
 * both US Open boards `decided`, 0 of 36 and 0 of 44 rows priced.
 *
 * And the STALE body predates the settle, so it carries no `decided` either. A
 * field absent on both sides of the defect cannot decide it.
 *
 * ═══ 🔴 WHY THIS IS NOT A CACHE FIX ═══
 *
 * Verified before building: `layout.tsx` and `opengraph-image.tsx` fetch an
 * IDENTICAL url with an IDENTICAL window. There is no misalignment to correct,
 * transport is latency's under notice 41, and `revalidate` is untouched by this
 * ship. `payloadIsStale` is the judgement that holds whatever the cache does —
 * which matters most on this surface, because an unfurl's bytes are cached by
 * Slack and X on the READER's side: a card fetched once while wrong stays wrong
 * in that channel long after production has healed itself.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * No result is claimed, and the identity is kept: a stale body's `title` and
 * `subtitle` are still true, so the card goes QUIET, not blank. And the rule
 * fails open three ways — absent, unparseable and future stamps all print —
 * because this exists to catch a body we can PROVE is old.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  buildTournamentShareCopy,
  tournamentShareFacts,
  TOURNAMENT_SHARE_REVALIDATE_SECONDS,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/tournaments/[slug]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/** The instant the stale card was measured on production. */
const OBSERVED_AT = Date.parse("2026-09-14T13:29:00.000Z");

/**
 * The body the card drew from, reconstructed from the card itself.
 *
 * The two probabilities are the ones a reader saw — 59% and 99% — and the names
 * and `title`/`subtitle` are production's own. The exact `generated_at` of that
 * body is not recoverable; what IS known is that it predates the men's final
 * settle (`completed_at` 2026-09-13 21:53:36Z), because both boards are priced
 * and neither is `decided`. Any such stamp is at least fifteen hours old at the
 * observed render, so the stamp below is the LATEST the body can have been
 * built — the hardest case for the bound.
 */
const STALE_BODY: TournamentShareSource = {
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  generated_at: "2026-09-13T21:53:00.000Z",
  boards: [
    {
      label: "Men's Singles",
      rows: [
        { display_name: "Alexander Zverev", probability: 0.59 },
        { display_name: "Ben Shelton", probability: 0.22 },
        { display_name: "Lorenzo Musetti", probability: 0.11 },
      ],
    },
    {
      label: "Women's Singles",
      rows: [
        { display_name: "Elena Rybakina", probability: 0.99 },
        { display_name: "Alexandra Eala", probability: 0.011 },
      ],
    },
  ],
};

/** The same body, built a minute ago. Nothing about it is stale but the clock. */
const FRESH_BODY: TournamentShareSource = {
  ...STALE_BODY,
  generated_at: new Date(OBSERVED_AT - 60_000).toISOString(),
};

/** Production's live shape: settled by `apply_final_result`, every price null. */
const DECIDED_BODY: TournamentShareSource = {
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  generated_at: new Date(OBSERVED_AT - 60_000).toISOString(),
  boards: [
    {
      label: "Men's Singles",
      rows: [
        { display_name: "Alexander Zverev", probability: null },
        { display_name: "Ben Shelton", probability: null },
      ],
    },
  ],
};

/* ─────────────────────────────── the harness ─────────────────────────────── */

/**
 * The card as the reader meets it, top to bottom.
 *
 * Rendered rather than prop-inspected, for #6149's reason: a prop assertion
 * would pass on a card that received `rows={[]}` and drew a number from
 * somewhere else. The route reads the clock through `Date.now`, so the spy is
 * what puts the render at the measured instant — an absolute stamp, never an
 * offset from the suite's own run time.
 */
async function drawCard(payload: TournamentShareSource): Promise<string> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  }) as unknown as typeof fetch;

  await OgImage({ params: Promise.resolve({ slug: "us-open" }) });

  return renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every string the card and the copy put in front of a reader, as one blob. */
async function everythingSaid(payload: TournamentShareSource): Promise<string> {
  const { title, description } = buildTournamentShareCopy(payload, OBSERVED_AT);
  return `${title} ${description} ${await drawCard(payload)}`;
}

beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(OBSERVED_AT);
});

afterEach(() => {
  jest.restoreAllMocks();
});

/* ──────────────────────────────── the ship ──────────────────────────────── */

describe("#6161 a stale body does not unfurl as a current forecast", () => {
  it("the defect's own numbers are gone from BOTH halves", async () => {
    const said = await everythingSaid(STALE_BODY);

    expect(said).not.toMatch(/59\s*%/);
    expect(said).not.toMatch(/99\s*%/);
    expect(said).not.toContain("Alexander Zverev");
    expect(said).not.toContain("Elena Rybakina");
    expect(said).not.toMatch(/leads/i);
    expect(said).not.toContain("draws tracked");
  });

  it("goes QUIET, not blank — the hub is still named", async () => {
    const { title, description } = buildTournamentShareCopy(
      STALE_BODY,
      OBSERVED_AT,
    );

    expect(title).toBe("US Open 2026");
    expect(description).toContain("Flushing Meadows");
    expect(await drawCard(STALE_BODY)).toContain("US Open 2026");
  });

  it("the two halves agree, which is the symptom that was filed", async () => {
    const { title } = buildTournamentShareCopy(STALE_BODY, OBSERVED_AT);
    const card = await drawCard(STALE_BODY);

    // The words were right and the picture was wrong. Neither may carry a
    // number now, and they may not diverge again.
    expect(title).not.toMatch(/\d+\s*%/);
    expect(card).not.toMatch(/\d+\s*%/);
  });
});

describe("#6161 over-reach controls — the rule fires on AGE, not on content", () => {
  it("the identical body, built a minute ago, still prints its leaders", async () => {
    const { title, description } = buildTournamentShareCopy(
      FRESH_BODY,
      OBSERVED_AT,
    );

    expect(title).toBe("US Open 2026: Alexander Zverev 59%, Elena Rybakina 99%");
    expect(description).toContain("Alexander Zverev leads the Men's Singles at 59%.");
    expect(await drawCard(FRESH_BODY)).toContain("59%");
  });

  it("a body with NO stamp prints — every caller before this shipped one", () => {
    const unstamped: TournamentShareSource = {
      ...STALE_BODY,
      generated_at: undefined,
    };

    expect(tournamentShareFacts(unstamped, OBSERVED_AT).leaders).toHaveLength(2);
  });

  it("an unparseable stamp prints rather than silencing the card", () => {
    const garbled: TournamentShareSource = {
      ...STALE_BODY,
      generated_at: "not a date",
    };

    expect(tournamentShareFacts(garbled, OBSERVED_AT).leaders).toHaveLength(2);
  });

  it("a stamp in the FUTURE is clock skew, not staleness", () => {
    const skewed: TournamentShareSource = {
      ...STALE_BODY,
      generated_at: new Date(OBSERVED_AT + 86_400_000).toISOString(),
    };

    expect(tournamentShareFacts(skewed, OBSERVED_AT).leaders).toHaveLength(2);
  });
});

describe("#6161 the bound is derived from the fetch window, not chosen", () => {
  /** The bound the module computes, restated from its two inputs. */
  const boundMs = TOURNAMENT_SHARE_REVALIDATE_SECONDS * 12 * 1000;

  const atAge = (ms: number): TournamentShareSource => ({
    ...STALE_BODY,
    generated_at: new Date(OBSERVED_AT - ms).toISOString(),
  });

  it("a body exactly at the bound still prints", () => {
    expect(tournamentShareFacts(atAge(boundMs), OBSERVED_AT).leaders).toHaveLength(2);
  });

  it("a body one second past it does not", () => {
    expect(
      tournamentShareFacts(atAge(boundMs + 1000), OBSERVED_AT).leaders,
    ).toEqual([]);
  });

  it("the window is the one both halves actually fetch with", () => {
    // If the routes' cache window is ever retuned, the bound moves with it
    // rather than drifting — the two `300`s this ship replaced could not.
    expect(TOURNAMENT_SHARE_REVALIDATE_SECONDS).toBe(300);
    expect(boundMs).toBe(3_600_000);
  });
});

describe("#6161 inertness — why `decided` was not the fix", () => {
  it("a settled board is already withheld, with no `decided` branch at all", () => {
    // `apply_final_result` nulls every probability BEFORE it writes `decided`,
    // so the two states cannot co-occur and `boardLeader`'s null-price exit
    // covers the whole class. If a decided board ever arrives priced, this
    // fails and this module needs the branch the issue proposed.
    expect(tournamentShareFacts(DECIDED_BODY, OBSERVED_AT).leaders).toEqual([]);
    expect(buildTournamentShareCopy(DECIDED_BODY, OBSERVED_AT).title).toBe(
      "US Open 2026",
    );
  });
});
