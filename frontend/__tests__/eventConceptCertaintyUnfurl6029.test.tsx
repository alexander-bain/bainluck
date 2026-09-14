/**
 * #6029 — A GOLF TOURNAMENT THAT HAS ALREADY BEEN WON STOPS UNFURLING AS
 * "SHANE LOWRY LEADS AT 100%".
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 11:17Z ═══
 *
 * `https://bainluck.com/event/golf/amgen-irish-open`, read with a crawler UA at
 * one instant — the two halves of ONE card, from one payload and one shared
 * helper, disagreeing in the same minute:
 *
 *   og:image        "Amgen Irish Open · Trump International Golf Links &
 *                    Hotel Ireland · Shane Lowry won"                       ✅
 *   og:title        "Amgen Irish Open: Shane Lowry 100%"                    ❌
 *   og:description  "Trump International Golf Links & Hotel Ireland.
 *                    Shane Lowry leads at 100%."                            ❌
 *
 * Not a CDN artefact: `x-vercel-cache: MISS`, `age: 0`, `no-store`, and it
 * survived a re-read 400s later — past the `revalidate: 300` both routes carry.
 *
 * ═══ 🔴 THE ISSUE'S STATED MECHANISM IS REFUTED — THE ADAPTER IS CORRECT ═══
 *
 * #6029 was filed as a golf-adapter bug: `event.status` stuck at `"live"` so
 * `flaggedWinner`'s conjunction never fired. By the time it was worked the
 * adapter had flipped — production serves `status: "settled"` with Shane Lowry
 * `won: true, probability: 1.0`, which is why the PICTURE was right. The words
 * were simply reading an older body. Fixing the adapter would have changed
 * nothing, and the eight-adapter census the issue implied was not needed.
 *
 * ═══ THE STALE READ IS THE OCCASION; THE DEFECT IS THAT 100% HAS NO BRANCH ═══
 *
 * `buildEventConceptShareCopy` had no answer for a price of 1.0 other than to
 * narrate it as a lead, so ANY lag between a contest deciding and `event.status`
 * flipping prints that sentence — a stale cache entry is only one way to buy the
 * lag. The structural way is larger: `_golf_status` date-settles a tournament
 * only at `end_date < today - 1 day`, and the Irish Open's `end_date` is
 * 2026-09-13, so on 2026-09-14 it is NOT date-settled. Production reads
 * "settled" today for one reason only — DataGolf's `schedule_status` flipped
 * first. Whenever that flip lags, the date path holds a finished tournament
 * non-settled for the better part of two days with its winner sitting at 100%.
 *
 * Nor is the fuel scarce. One db-query against production the same morning:
 * open futures markets carry 2,259 outcomes at exactly 1.000 and 1,711 more in
 * [0.995, 1.0) — every one of which prints "100%". The band below,
 * [0.990, 0.995), holds 2,064 more that print "99%" and are deliberately left
 * alone.
 *
 * ═══ THE FIX IS AN ADOPTION — THE SEVENTH IN A ROW ═══
 *
 * Nothing new is decided and no new branch is drawn. `eventConceptShareFacts`
 * is the facts BOTH halves already read, so clearing `priced` there lands the
 * judgement once: the copy falls to its existing "nothing priced" rung and the
 * card falls to its existing quiet rendering. `withholds the board, not the
 * competitor` below is the assertion a narrower repair fails.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * No result is claimed. The module header's refusal stands — a winner is read
 * from the authoritative `won` flag and NEVER inferred from a price, because
 * `event:ufc:26sep12` sat `live` at 0.99. This branch claims strictly LESS, not
 * more: the reader gets the event's name and no number, and the card upgrades
 * itself to "X won" the moment settlement lands. `the settled payload is
 * untouched` pins that second half.
 *
 * The cache windows are untouched too. Aligning them was considered and
 * rejected: both routes already carry an identical `revalidate: 300` on an
 * identical URL, so there is no misalignment to fix, and a copy rule that only
 * holds while two caches agree is not a rule.
 *
 * Sibling surfaces are NOT converted. `boardLeader` in `tournamentShareMeta`
 * has the same shape of hole, but no specimen was measured there and an
 * unproven widening is how a withholding rule starts eating live markets. It is
 * one call away when someone measures one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  buildEventConceptShareCopy,
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";
import { formatShareProbability } from "@/lib/share";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/event/[domain]/[slug]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The production payload, field for field, trimmed to what these two surfaces
 * read — captured from `GET /api/event/event:golf:amgen-irish-open` on
 * 2026-09-14, not invented. The finding is that a PLAUSIBLE card is drawn from
 * an HONEST payload, and a fixture built to the fix's shape cannot catch that.
 *
 * The 199 golfers behind Lowry really are all at `0.0`:
 * `formatShareProbability` drops them, which is why `priced` has length 1 and
 * the FIELD branch — not the duel — produced the measured sentence. Three are
 * carried here so that fact is visible rather than asserted.
 */
const IRISH_OPEN_SETTLED: EventConceptShareSource = {
  event: {
    name: "Amgen Irish Open",
    slug: "amgen-irish-open",
    status: "settled",
    venue: "Trump International Golf Links & Hotel Ireland",
    location: null,
  },
  primary: {
    label: "Winner",
    competitors: [
      { name: "Shane Lowry", probability: 1.0, won: true },
      { name: "Ryan Gerard", probability: 0.0, won: false },
      { name: "Marco Penge", probability: 0.0, won: false },
      { name: "Keita Nakajima", probability: 0.0, won: false },
    ],
  },
};

/**
 * The same tournament before the status flip — the body the WORDS were reading
 * at 11:17Z.
 *
 * `event.status` is the ONLY field changed from the payload above, which is
 * what makes this a reproduction rather than a construction: with the guard
 * removed it emits the measured strings byte for byte (verified 2026-09-14,
 * `"Amgen Irish Open: Shane Lowry 100%"` / `"…Shane Lowry leads at 100%."`).
 *
 * `won` is left TRUE deliberately, even though the pre-flip body may not have
 * carried it: `flaggedWinner` gates on `settled` first and returns null either
 * way, so leaving it set proves the fix does not quietly lean on the flag.
 */
const IRISH_OPEN_PRE_FLIP: EventConceptShareSource = {
  ...IRISH_OPEN_SETTLED,
  event: { ...IRISH_OPEN_SETTLED.event, status: "live" },
};

/**
 * `_golf_status`'s OTHER non-settled return.
 *
 * With `schedule_status` absent and an `end_date` inside the one-day grace, the
 * function falls through every branch and returns `"upcoming"` — so a finished
 * tournament is reachable in two distinct non-settled states, not one. Both
 * must withhold, and a fix keyed on the word "live" would pass the case above
 * and fail this one.
 */
const IRISH_OPEN_UPCOMING: EventConceptShareSource = {
  ...IRISH_OPEN_SETTLED,
  event: { ...IRISH_OPEN_SETTLED.event, status: "upcoming" },
};

/**
 * THE OVER-REACH CONTROL: a genuinely live field, priced nowhere near certainty.
 *
 * Real values from `GET /api/golf` on 2026-09-14. If the ship is drawn one step
 * too wide this card goes quiet and a working surface is deleted, so this is the
 * fixture that proves the withholding is narrow.
 */
const BILTMORE_LIVE: EventConceptShareSource = {
  event: {
    name: "Biltmore Championship Asheville",
    slug: "biltmore-championship-asheville",
    status: "upcoming",
    venue: null,
    location: null,
  },
  primary: {
    label: "Winner",
    competitors: [
      { name: "Scottie Scheffler", probability: 0.182, won: false },
      { name: "Rory McIlroy", probability: 0.087, won: false },
      { name: "Xander Schauffele", probability: 0.084, won: false },
    ],
  },
};

/* ─────────────────────────────── the harness ─────────────────────────────── */

/**
 * The card as the reader meets it, top to bottom.
 *
 * `UnfurlCard` is a plain function component, so the element the route hands
 * `ImageResponse` is rendered rather than prop-inspected — a prop assertion
 * would pass on a card that received `rows={[]}` and drew a number from
 * somewhere else.
 */
async function drawCard(payload: EventConceptShareSource): Promise<string> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  }) as unknown as typeof fetch;

  await OgImage({
    params: Promise.resolve({ domain: "golf", slug: "amgen-irish-open" }),
  });

  return renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every string the card and the copy put in front of a reader, as one blob. */
async function everythingSaid(payload: EventConceptShareSource): Promise<string> {
  const { title, description } = buildEventConceptShareCopy(payload);
  return `${title} ${description} ${await drawCard(payload)}`;
}

/* ──────────────────────────────── the ship ──────────────────────────────── */

describe("#6029 a decided contest does not unfurl as a forecast", () => {
  it("the measured sentence is gone from BOTH halves", async () => {
    const { title, description } = buildEventConceptShareCopy(IRISH_OPEN_PRE_FLIP);

    // The two strings production served at 11:17Z, verbatim.
    expect(title).not.toBe("Amgen Irish Open: Shane Lowry 100%");
    expect(description).not.toBe(
      "Trump International Golf Links & Hotel Ireland. Shane Lowry leads at 100%.",
    );

    const said = await everythingSaid(IRISH_OPEN_PRE_FLIP);
    expect(said).not.toMatch(/100\s*%/);
    expect(said).not.toMatch(/leads/i);
  });

  it("still names the tournament, so the card is quiet and not broken", async () => {
    const { title } = buildEventConceptShareCopy(IRISH_OPEN_PRE_FLIP);
    expect(title).toBe("Amgen Irish Open");

    const card = await drawCard(IRISH_OPEN_PRE_FLIP);
    expect(card).toContain("Amgen Irish Open");
    expect(card).toContain("Trump International Golf Links & Hotel Ireland");
    expect(card).toContain("Golf");
  });

  it("withholds the board, not the competitor", async () => {
    // A repair that dropped only the certain golfer would promote the next one
    // and crown a longshot as the new leader. Two golfers priced BEHIND a
    // certain one — neither may be named, and no number may survive.
    const decidedField: EventConceptShareSource = {
      ...IRISH_OPEN_SETTLED,
      event: { ...IRISH_OPEN_SETTLED.event, status: "live" },
      primary: {
        label: "Winner",
        competitors: [
          { name: "Shane Lowry", probability: 1.0, won: false },
          { name: "Rory McIlroy", probability: 0.03, won: false },
          { name: "Tyrrell Hatton", probability: 0.01, won: false },
        ],
      },
    };

    expect(eventConceptShareFacts(decidedField).priced).toEqual([]);

    const said = await everythingSaid(decidedField);
    expect(said).not.toContain("Rory McIlroy");
    expect(said).not.toContain("Tyrrell Hatton");
    expect(said).not.toMatch(/\d+\s*%/);
  });

  it("withholds in every non-settled state, not just 'live'", async () => {
    const said = await everythingSaid(IRISH_OPEN_UPCOMING);
    expect(said).not.toMatch(/100\s*%/);
    expect(said).not.toMatch(/leads/i);
    expect(eventConceptShareFacts(IRISH_OPEN_UPCOMING).priced).toEqual([]);
  });

  it("withholds a certain DUEL too, where the sentence never said 'leads'", async () => {
    // The duel branch prints "A 100%, B 1%" — no "leads", but a pair summing to
    // 101% and asserting certainty. A fix aimed at the word rather than at the
    // number would leave this standing.
    const duel: EventConceptShareSource = {
      event: { name: "Fight Night: Klose vs Gantt", status: "live", venue: null },
      primary: {
        label: "Main event",
        competitors: [
          { name: "Klose", probability: 0.997, won: false },
          { name: "Gantt", probability: 0.01, won: false },
        ],
      },
    };

    const said = await everythingSaid(duel);
    expect(said).not.toMatch(/\d+\s*%/);
    expect(said).toContain("Fight Night: Klose vs Gantt");
  });
});

describe("#6029 the ship does not over-reach", () => {
  it("a genuinely live field still names its leader", async () => {
    const { title, description } = buildEventConceptShareCopy(BILTMORE_LIVE);
    expect(title).toBe("Biltmore Championship Asheville: Scottie Scheffler 18%");
    expect(description).toContain("Scottie Scheffler leads at 18%");
    expect(await drawCard(BILTMORE_LIVE)).toContain("Scottie Scheffler");
  });

  it("the settled payload is untouched — the card upgrades itself to the result", async () => {
    const { title, description } = buildEventConceptShareCopy(IRISH_OPEN_SETTLED);
    expect(title).toBe("Amgen Irish Open: Shane Lowry won");
    expect(description).toBe("Final: Shane Lowry won.");
    expect(await drawCard(IRISH_OPEN_SETTLED)).toContain("Shane Lowry won");
  });

  it("a leader one rounding step below certainty is left alone", async () => {
    // 0.994 prints "99%". The withholding band is one step wide on purpose, so
    // a lopsided-but-live market keeps its number.
    //
    // The runners-up sit at 0.0 exactly, as they really do on this specimen, so
    // `formatShareProbability` drops them and this takes the FIELD branch — the
    // same branch that produced the measured defect. An earlier draft priced one
    // of them at 0.003, which does NOT get dropped (it prints "0%") and quietly
    // moved the case to the duel branch, testing the wrong sentence.
    const lopsided: EventConceptShareSource = {
      ...IRISH_OPEN_SETTLED,
      event: { ...IRISH_OPEN_SETTLED.event, status: "live" },
      primary: {
        label: "Winner",
        competitors: [
          { name: "Shane Lowry", probability: 0.994, won: false },
          { name: "Rory McIlroy", probability: 0.0, won: false },
        ],
      },
    };

    expect(buildEventConceptShareCopy(lopsided).description).toContain(
      "Shane Lowry leads at 99%",
    );
    expect(await drawCard(lopsided)).toContain("99%");
  });
});

describe("#6029 the threshold is the formatter's own boundary", () => {
  /**
   * The one assertion that keeps `PRINTS_AS_CERTAIN` honest.
   *
   * The constant is 0.995 because that is where `formatShareProbability`'s
   * `Math.round` turns over — not because 0.995 is a nice number. Asserting the
   * formatter directly means this suite fails if the rounding ever changes,
   * rather than the module silently withholding the wrong band.
   */
  it("0.995 prints 100% and 0.994 prints 99%", () => {
    expect(formatShareProbability(0.995)).toBe("100%");
    expect(formatShareProbability(0.994)).toBe("99%");
  });

  it("the withheld set is exactly the set that would print 100% or more", () => {
    const withheld = (fraction: number) =>
      eventConceptShareFacts({
        event: { name: "T", status: "live" },
        primary: { competitors: [{ name: "A", probability: fraction }] },
      }).priced.length === 0;

    // Below the boundary: kept, and each prints a number under 100%.
    for (const fraction of [0.5, 0.9, 0.99, 0.994]) {
      expect([fraction, withheld(fraction)]).toEqual([fraction, false]);
    }
    // At and above it: withheld. 1.02 is in the list because a price over 1.0
    // prints "102%", which is no more a forecast than "100%" is.
    for (const fraction of [0.995, 0.999, 1.0, 1.02]) {
      expect([fraction, withheld(fraction)]).toEqual([fraction, true]);
    }
  });
});
