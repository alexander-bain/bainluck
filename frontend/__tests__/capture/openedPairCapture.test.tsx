/**
 * UX-P166 — a game card's "Opened" line stops adding up to 101.
 *
 * ═══ WHAT A READER SEES TODAY ═══
 *
 * Read on the deployed build, 2026-08-29, over EVERY event in the database that
 * carries an opening line — a census, not a sample:
 *
 *     Athletic Bilbao @ Barcelona     ->  Opened 85/16
 *     FC Machida Zelvia @ Mito        ->  Opened 32/69      (LIVE when measured)
 *     Lyngby @ AC Horsens             ->  Opened 38/63
 *
 *     events with an opening line          24,117
 *     of those, complement pairs           24,117   (all of them)
 *     printing a pair that sums to 101        207   (115 completed, 91 closed, 1 live)
 *     printing a pair that sums to 99           0
 *
 * The one-directional skew is the signature: only an exact `.5` fractional part
 * misfires, and it rounds BOTH sides up. Never 99, always 101 — one systematic
 * cause rather than noise. Same shape as the `current_odds` strip UX-P114 fixed.
 *
 * ═══ THE EXEMPLAR IS A CARD THAT DISAGREED WITH ITSELF ═══
 *
 * Barcelona's `opening_odds` and `current_odds` hold the SAME two floats, 0.845
 * and 0.155. `current_odds` carries the server's rendered percents, so the strip
 * printed 85/15. `opening_odds` carries none, so the footer printed `Opened
 * 85/16`. One card, one pair of numbers, two answers a point apart — and the fix
 * was already sitting one field over on the same payload.
 *
 * ═══ WHY THE FAVOURITE'S NUMBER NEVER MOVES ═══
 *
 * `renderedDuelPercents` hands the FAVOURITE to index 0, so the number a reader
 * anchors on survives untouched and the derived point lands on the side nobody is
 * quoting. On all three specimens the favourite keeps its own correct value
 * (85, 69, 63) and only the underdog moves. Always-away-first would instead have
 * moved Mito's favourite off its own correct 69.
 *
 * ═══ SCOPE: THE THREE CARD SURFACES, BECAUSE MASTER ALREADY FIXED THE OTHER THREE ═══
 *
 * A grep for `Opened` across `frontend/` and `ios/` found SIX surfaces printing an
 * independently-rounded pair. Checking this branch against `origin/master` before
 * issuing the READY token found that **#2085 has already fixed three of them** —
 * `app/events/[id]/page.tsx` and both sites in `EventDetailView.swift` — with the
 * same helper and, on the web side, a better placement (the decision moved into
 * `resolveProbability`, which is the one place that knows which source each pair
 * came from). Master carries its own tests for those: `test_event_detail_duel_
 * percents_2085.py`, `eventHeroDuelInvariant.test.tsx`, `eventDetailHeroDuel.test.ts`.
 *
 * So this queue owns the three master did NOT fix, which are the three CARD
 * surfaces and the higher-traffic half: `FeedCard.tsx`, `EventCard.tsx` and
 * `EventCardView.swift`. #2085 fixed the two detail pages and missed every card.
 *
 * ⚠️ **Do not "restore" the detail-page arm here.** It was written, it passed, and
 * it was deleted on purpose once master's copy was found — duplicating it would
 * re-create a merge conflict and a second owner for one line.
 *
 * Master's `servedDuelPercents` (#2279) is deliberately NOT used: its own red block
 * says a caller whose probabilities came from `opening_odds` must pass null served
 * values and fall back to `renderedDuelPercents`, which is exactly what these three
 * sites do.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * The SHIPPED `FeedCard` and `EventCard`, with the app's own compiled stylesheet.
 * The payloads are not hand-written: `backend/tests/fixtures/uxp166_opened_pairs.json`
 * holds what `GET /api/events/{id}` actually served for each specimen, and the
 * `naive_*` fields record what those surfaces printed from them before this queue.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=openedPairCapture
 *
 * With no env var set it is an ordinary test that renders every panel and asserts
 * the rig works, same as the sibling capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

// Both cards read the analytics context, which has no provider under
// `renderToStaticMarkup`. Stubbed rather than wrapped: this file is about the two
// numbers the footer prints, and a real provider would add a second thing that can
// break these tests for reasons unrelated to their subject.
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({
    trackEventCardClick: () => {},
    track: () => {},
  }),
}));

import FeedCard from "@/components/FeedCard";
import EventCard from "@/components/EventCard";
import { PREMATCH_SAID } from "@/lib/prematchReading";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp166_opened_pairs.json",
);

type Odds = {
  home_probability: number;
  away_probability: number;
  home_rendered_percent?: number;
  away_rendered_percent?: number;
  favorite?: string;
};
type Spec = {
  id: number;
  status: string;
  sport: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  home_score: number | null;
  away_score: number | null;
  opening_odds: Odds;
  current_odds: Odds;
  naive_opened_home_away: [number, number];
  naive_opened_sum: number;
  expected_opened_home_away: [number, number];
};

const fixture: { _census: Record<string, unknown>; events: Spec[] } = JSON.parse(
  fs.readFileSync(FIXTURE, "utf8"),
);

const spec = (id: number): Spec => {
  const found = fixture.events.find((e) => e.id === id);
  if (!found) throw new Error(`fixture is missing event ${id}`);
  return found;
};

const BARCELONA = spec(14970075);
const MITO = spec(15291020);
const LYNGBY = spec(15199704);
const YANKEES = spec(14877917);
const THIN = spec(900000001);

const ALL_101 = [BARCELONA, MITO, LYNGBY];

/** The app's own compiled stylesheet, so the panels look like the product. */
function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

function asFeedData(s: Spec): FeedEventData {
  return {
    id: s.id,
    external_id: `evt-${s.id}`,
    sport: s.sport,
    sport_name: s.sport,
    home_team: s.home_team,
    away_team: s.away_team,
    commence_time: s.commence_time,
    status: s.status,
    home_score: s.home_score,
    away_score: s.away_score,
    opening_odds: s.opening_odds,
    current_odds: s.current_odds,
  } as unknown as FeedEventData;
}

function asEvent(s: Spec): Event {
  return {
    id: s.id,
    external_id: `evt-${s.id}`,
    sport: s.sport,
    home_team: s.home_team,
    away_team: s.away_team,
    commence_time: s.commence_time,
    status: s.status,
    home_score: s.home_score,
    away_score: s.away_score,
    opening_odds: s.opening_odds,
    current_odds: s.current_odds,
  } as unknown as Event;
}

function renderFeedCard(s: Spec): string {
  const item = {
    type: "event",
    score: 50,
    reason: "",
    headline: "",
    data: asFeedData(s),
  } as unknown as FeedItem;
  return renderToStaticMarkup(<FeedCard item={item} />);
}

function renderEventCard(s: Spec): string {
  return renderToStaticMarkup(<EventCard event={asEvent(s)} />);
}

/**
 * `renderToStaticMarkup` HTML-escapes, and the extractor must undo that before
 * reading copy back (UX-P046's `&lt;1%` sentinel trap, inherited).
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The two integers the card actually PRINTS for the OPENING LINE, [home, away].
 *
 * Anchored on the rendered TEXT rather than on a source expression: #2060's
 * forced lesson is that a mutation replacing a conditional with `{false && (`
 * leaves every source token intact and passes a grep-shaped suite. Throws rather
 * than returning null, so a card that stops printing the pair is a red test and
 * not a silently-skipped one.
 *
 * ═══ ux/1036 — WHY THIS READS TWO LOCI ═══
 *
 * UX-P166's subject is a RULE — the two sides of the opening line are rounded as
 * one pair, so they cannot sum to 101 — and its locus used to be the single
 * `Opened H/A` footer, on live and settled cards alike.
 *
 * A settled card no longer has that footer. Alex, on /sports "Just Happened" at
 * phone width: *"How come none of these show pre-event probability?"* — the
 * footnote was the ONLY pre-match figure on a FINAL card and it never said which
 * team was the 40. The two numbers now sit beside the two names instead.
 *
 * So the rule is unchanged and it is enforced in a second place, which is why
 * this reads both rather than dropping the settled specimens. Four of the five
 * are settled; scoping the guard to the live pair would have retired most of
 * UX-P166's census while calling it a pass. Same expected integers either way —
 * `renderedDuelPercents` decides both loci.
 */
function printedOpened(html: string): [number, number] {
  const text = visibleText(html);

  // ═══ ux/1041 (#2689) — READ THE FOOTER'S SIDES BY NAME WHERE IT GIVES THEM ═══
  //
  // `FeedCard`'s footer used to be `Opened {home}/{away}` on a card that lists
  // the AWAY team above the HOME team, which inverted the favourite on 10 of 10
  // rows — by construction, since the pair is an exact complement. It is
  // away-first now, and it states the order in its own accessible name instead
  // of leaving it to position, so this reads THAT and derives which side is
  // which from the card's own link label ("{away} at {home}").
  //
  // NOT a constant in this file. A hardcoded [home, away] here is exactly the
  // mistake #2786 made one component away — it read the order off a sibling and
  // could not notice when the card moved underneath it. `EventCard` keeps the
  // positional branch below, because it lists HOME first and its footer is
  // correct; that asymmetry is the whole point and is why this cannot be one
  // global flip.
  //
  // The UX-P166 rule this file exists for is untouched: same two integers, same
  // pair, same rounding. Only the order they are read in changed.
  const said = html.match(/data-testid="feed-card-opened"[^>]*aria-label="([^"]+)"/);
  if (said) {
    const sides = Array.from(
      said[1].matchAll(/(.+?) opened at (\d+)%/g),
    ).map((m) => [m[1].replace(/^,\s*/, ""), Number(m[2])] as [string, number]);
    // Anti-vacuity: two sides, always, or the sentence stopped naming them and
    // this must go red rather than fall through to a positional guess.
    expect(sides).toHaveLength(2);
    const link = html.match(/aria-label="([^"]+?) at ([^"]+?)(?: - [^"]*)?"/);
    expect(link).not.toBeNull();
    const [awayName] = [link![1]];
    const away = sides.find(([team]) => team === awayName);
    const home = sides.find(([team]) => team !== awayName);
    expect(away).toBeDefined();
    expect(home).toBeDefined();
    return [home![1], away![1]];
  }

  const footer = text.match(/Opened\s+(\d+)\s*\/\s*(\d+)/);
  if (footer) return [Number(footer[1]), Number(footer[2])];

  // The settled card's per-team cells. Matched through the screen-reader
  // sentence, which names the team each number is about — the whole reason the
  // footer was replaced, and the only way to read [home, away] back out of a
  // layout whose visible order is away-first.
  // ONE phrasing since D65 (Alex: "shouldn't reference sportsbooks"), and the
  // pattern is BUILT FROM `PREMATCH_SAID` rather than retyped. This extractor
  // used to spell out both halves of the old rung-dependent fork, and every
  // specimen here is an `opening_odds` (books) card — so when the phrase moved,
  // a hand-copied literal read zero cells and threw on the whole census. Derived
  // from the constant, the census cannot be broken by rewording again.
  const perTeam = Array.from(
    text.matchAll(
      new RegExp(`${PREMATCH_SAID.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} .+? (\\d+)%`, "g"),
    ),
  ).map((m) => Number(m[1]));
  if (perTeam.length === 2) return [perTeam[1], perTeam[0]];

  throw new Error(
    `no opening pair in the rendered markup — neither an "Opened H/A" footer nor ` +
      `two per-team pre-match cells.\n${text.slice(0, 600)}`,
  );
}

describe("UX-P166 — the fixture reproduces what production served", () => {
  it("every specimen carries the payload the endpoint actually returned", () => {
    expect(BARCELONA.opening_odds).toEqual({
      home_probability: 0.845,
      away_probability: 0.155,
      favorite: "home",
    });
    expect(MITO.status).toBe("live");
    expect(LYNGBY.opening_odds.home_probability).toBe(0.375);
  });

  it("the exemplar's two odds blocks hold the SAME floats and disagreed anyway", () => {
    // This is the whole argument for the fix in one assertion: the numbers were
    // never in question, only which field they arrived in.
    expect(BARCELONA.current_odds.home_probability).toBe(
      BARCELONA.opening_odds.home_probability,
    );
    expect(BARCELONA.current_odds.away_probability).toBe(
      BARCELONA.opening_odds.away_probability,
    );
    expect([
      BARCELONA.current_odds.home_rendered_percent,
      BARCELONA.current_odds.away_rendered_percent,
    ]).toEqual([85, 15]);
    expect(BARCELONA.naive_opened_home_away).toEqual([85, 16]);
  });

  it("the recorded BEFORE numbers are what independent rounding really produces", () => {
    // The fixture's `naive_*` fields are a claim about the old code. Re-derive
    // them from the floats rather than trusting the JSON, or a mistyped fixture
    // would make the AFTER assertions look like a fix they are not.
    for (const s of [...ALL_101, YANKEES, THIN]) {
      const naive: [number, number] = [
        Math.round(s.opening_odds.home_probability * 100),
        Math.round(s.opening_odds.away_probability * 100),
      ];
      expect([s.id, naive]).toEqual([s.id, s.naive_opened_home_away]);
      expect([s.id, naive[0] + naive[1]]).toEqual([s.id, s.naive_opened_sum]);
    }
  });

  it("the three 101 specimens are the defect and the other two are not", () => {
    expect(ALL_101.map((s) => s.naive_opened_sum)).toEqual([101, 101, 101]);
    expect(YANKEES.naive_opened_sum).toBe(100);
    expect(THIN.naive_opened_sum).toBe(97);
  });
});

describe("UX-P166 — the shipped feed card's footer", () => {
  it.each(ALL_101.map((s) => [`${s.away_team} @ ${s.home_team}`, s] as const))(
    "AFTER: %s prints a pair that adds up",
    (_name, s) => {
      const printed = printedOpened(renderFeedCard(s));
      expect(printed).toEqual(s.expected_opened_home_away);
      expect(printed[0] + printed[1]).toBe(100);
    },
  );

  it.each(ALL_101.map((s) => [`${s.away_team} @ ${s.home_team}`, s] as const))(
    "BEFORE/AFTER: %s no longer prints the 101 it used to",
    (_name, s) => {
      const printed = printedOpened(renderFeedCard(s));
      expect(printed).not.toEqual(s.naive_opened_home_away);
    },
  );

  it("AFTER: the FAVOURITE's own number is never the one that moves", () => {
    // The contract's reason for handing the favourite to index 0. Barcelona keeps
    // 85, Mito keeps 69, Lyngby keeps 63 — the derived point lands on the side
    // nobody is quoting.
    for (const s of ALL_101) {
      const homeIsFavourite =
        s.opening_odds.home_probability >= s.opening_odds.away_probability;
      const idx = homeIsFavourite ? 0 : 1;
      const printed = printedOpened(renderFeedCard(s));
      expect([s.id, printed[idx]]).toEqual([s.id, s.naive_opened_home_away[idx]]);
    }
  });

  it("LEAVE ALONE: an ordinary pair off the boundary prints exactly what it did", () => {
    // gotcha #43 — both directions. 23,910 of the 24,117 measured events are this
    // case and none of them may move.
    const printed = printedOpened(renderFeedCard(YANKEES));
    expect(printed).toEqual([61, 39]);
    expect(printed).toEqual(YANKEES.naive_opened_home_away);
  });

  it("LEAVE ALONE: an out-of-band pair is NOT forced to 100", () => {
    // Normalizing 0.97 would invent three points of probability rather than round
    // one. The footer keeps printing 97, because that is the honest total.
    const printed = printedOpened(renderFeedCard(THIN));
    expect(printed).toEqual([57, 40]);
    expect(printed[0] + printed[1]).toBe(97);
  });

  it("LEAVE ALONE: the boundary pairs are not moved either", () => {
    // Every extreme opening pair in the printing population, measured 2026-08-29
    // (4 distinct pairs over 19 events). The concern was that normalizing could
    // push an underdog to a false 0 or a favourite to a false 100. It does not:
    // all four render exactly what independent rounding rendered.
    //
    // ⚠️ THE LAST ROW IS A PRE-EXISTING DEFECT THIS QUEUE DOES NOT FIX, and it is
    // pinned here so it is not mistaken for one this queue caused. `0.998 / 0.002`
    // printed `Opened 100/0` before and prints `Opened 100/0` now: this footer
    // draws BARE INTEGERS with no `<1%` / `>99%` sentinel, so UX-P046's boundary
    // rule never reached it. One event today. The detail page's version of the
    // same line goes through `formatProbability` and prints `>99% – <1%`
    // correctly, so the two surfaces disagree — see the report's parked item.
    const EXTREMES: Array<[number, number, [number, number]]> = [
      [0.0192, 0.9808, [2, 98]],
      [0.9808, 0.0192, [98, 2]],
      [0.9831, 0.0169, [98, 2]],
      [0.998, 0.002, [100, 0]],
    ];
    for (const [home, away, expected] of EXTREMES) {
      const naive: [number, number] = [
        Math.round(home * 100),
        Math.round(away * 100),
      ];
      const s = {
        ...BARCELONA,
        opening_odds: { home_probability: home, away_probability: away },
      } as unknown as Spec;
      const printed = printedOpened(renderFeedCard(s));
      expect([home, printed]).toEqual([home, expected]);
      expect([home, printed]).toEqual([home, naive]); // unchanged by the fix
    }
  });

  it("a scheduled game has no opening footer to get wrong", () => {
    // The footer is gated on live/finished. Pinned so the fix cannot accidentally
    // start drawing pre-game context on a card that never had it.
    const scheduled = { ...BARCELONA, status: "scheduled" };
    expect(visibleText(renderFeedCard(scheduled))).not.toContain("Opened");
  });
});

describe("UX-P166 — the shipped sports/search event card's footer", () => {
  // `EventCard`'s footer is gated on `isLive` only, so the live specimen is the
  // one that reaches it. The finished specimens are covered on the feed card above.
  it("AFTER: the live game prints a pair that adds up", () => {
    const printed = printedOpened(renderEventCard(MITO));
    expect(printed).toEqual([31, 69]);
    expect(printed[0] + printed[1]).toBe(100);
    expect(printed).not.toEqual(MITO.naive_opened_home_away);
  });

  it("AFTER: the favourite keeps its own 69 and the underdog absorbs the point", () => {
    expect(printedOpened(renderEventCard(MITO))[1]).toBe(
      MITO.naive_opened_home_away[1],
    );
  });

  it("LEAVE ALONE: an out-of-band live pair keeps its honest 97", () => {
    const printed = printedOpened(renderEventCard(THIN));
    expect(printed).toEqual([57, 40]);
  });

  it("the away side is still DERIVED as 1 - home when the payload omits it", () => {
    // The derivation is what makes the pair an exact complement, so removing it
    // would silently remove the defect's precondition rather than fix it. Pinned
    // because the fix reads the derived value and a future edit could drop it.
    const noAway = {
      ...MITO,
      opening_odds: { home_probability: 0.315, away_probability: undefined },
    } as unknown as Spec;
    expect(printedOpened(renderEventCard(noAway))).toEqual([31, 69]);
  });
});

describe("UX-P166 — the two cards cannot disagree with each other", () => {
  it("both surfaces print the same pair for the same event", () => {
    // Two components, one rule. Before this queue they agreed only by both being
    // wrong in the same way.
    expect(printedOpened(renderEventCard(MITO))).toEqual(
      printedOpened(renderFeedCard(MITO)),
    );
  });

  it("and both agree with the shared helper the contract suite proves", () => {
    for (const s of [...ALL_101, YANKEES, THIN]) {
      const [awayPct, homePct] = renderedDuelPercents(
        s.opening_odds.away_probability,
        s.opening_odds.home_probability,
      );
      expect([s.id, [homePct, awayPct]]).toEqual([s.id, s.expected_opened_home_away]);
    }
  });
});

describe("UX-P166 — the artifact", () => {
  it("renders every panel", () => {
    const dir = process.env.UX_CAPTURE_DIR;

    const panel = (title: string, note: string, html: string) => `
      <section class="panel">
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="card">${html}</div>
      </section>`;

    const panels = [
      panel(
        "Athletic Bilbao @ Barcelona — the exemplar",
        `Served <code>opening_odds</code> and <code>current_odds</code> hold the same two floats.
         The strip printed <b>85/15</b>; the footer printed <b>Opened 85/16</b>.
         Now the opening pair reads <b>${printedOpened(renderFeedCard(BARCELONA)).join("/")}</b>
         — and since ux/1036 it reads it beside each team's name rather than in a footer.`,
        renderFeedCard(BARCELONA),
      ),
      panel(
        "FC Machida Zelvia @ Mito HollyHock — LIVE when measured",
        `The single live 101 in the census. Away is the favourite, so the derived point
         lands on HOME: was <b>Opened 32/69</b>, now
         <b>Opened ${printedOpened(renderFeedCard(MITO)).join("/")}</b> — still a footer,
         because this one is LIVE.`,
        renderFeedCard(MITO),
      ),
      panel(
        "Lyngby @ AC Horsens — the exactly-representable pair",
        `0.625 / 0.375: both sides land on a true <code>.5</code> with no floating-point
         excuse, and both rounded up. Was <b>Opened 38/63</b>, now
         <b>${printedOpened(renderFeedCard(LYNGBY)).join("/")}</b>, per team.`,
        renderFeedCard(LYNGBY),
      ),
      panel(
        "Boston Red Sox @ New York Yankees — LEFT ALONE",
        `23,910 of the 24,117 measured events are this case: an ordinary complement pair
         off the boundary. Prints <b>${printedOpened(renderFeedCard(YANKEES)).join("/")}</b>,
         exactly the numbers it printed before.`,
        renderFeedCard(YANKEES),
      ),
      panel(
        "A thin book — ALSO LEFT ALONE",
        `A pair summing to 0.97 is not two halves of one question. Forcing it to 100 would
         invent three points of probability, so it keeps
         <b>Opened ${printedOpened(renderFeedCard(THIN)).join("/")}</b> — total 97, on purpose.`,
        renderFeedCard(THIN),
      ),
      panel(
        "The live card on /sports and /search",
        `A second component, the same rule:
         <b>Opened ${printedOpened(renderEventCard(MITO)).join("/")}</b>.`,
        renderEventCard(MITO),
      ),
    ].join("\n");

    const html = `<!doctype html>
<meta charset="utf-8">
<title>UX-P166 — the "Opened" line stops adding up to 101</title>
<style>${appStylesheet()}</style>
<style>
  body { background:#f6f7f9; font-family:ui-sans-serif,system-ui,sans-serif; margin:0; padding:28px; }
  h1 { font-size:19px; margin:0 0 6px; }
  .lede { color:#555; max-width:900px; font-size:13px; line-height:1.6; margin:0 0 22px; }
  .lede b { color:#111; }
  .panel { margin:0 0 22px; max-width:520px; }
  .panel h2 { font-size:13px; margin:0 0 4px; color:#111; }
  .note { font-size:12px; color:#666; margin:0 0 8px; line-height:1.55; }
  .note code { background:#eceef1; padding:1px 4px; border-radius:3px; }
  .card { background:#fff; border:1px solid #e3e5e8; border-radius:12px; padding:12px; }
</style>
<h1>UX-P166 — a game card's "Opened" line stops adding up to 101</h1>
<p class="lede">
  Measured on the deployed build, 2026-08-29, over <b>every</b> event carrying an opening
  line — a census, not a sample. All <b>24,117</b> are complement pairs; <b>207</b> printed a
  pair summing to <b>101</b> (115 completed, 91 closed, 1 live) and <b>none</b> printed 99.
  The one-directional skew is the signature of the half-cent grid: only an exact
  <code>.5</code> misfires, and it rounds both sides up.
  Every panel below is the SHIPPED component rendered over the payload
  <code>GET /api/events/{id}</code> actually served.
</p>
${panels}
`;

    expect(html).toContain("Opened");
    if (dir) {
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "ux-p166-opened-pair.html"), html);
    }
  });
});
