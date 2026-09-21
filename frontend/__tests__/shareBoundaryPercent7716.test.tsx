/**
 * #7716 — A PASTED LINK STOPS PRINTING A NUMBER THE PAGE IT DEPICTS DOES NOT.
 *
 * ═══ THE DEFECT, BOTH ENDS, MEASURED ON PRODUCTION 2026-09-21 ═══
 *
 * `formatShareProbability` was a bare `Math.round(p * 100)` — the rule the rest
 * of the site has stopped using twice. Read with a crawler UA, the same minute:
 *
 *   /sport/baseball/mlb/team/baltimore-orioles-mlb   (championship_path 0.004)
 *     og:description  "Baltimore Orioles: 0% to win the championship."      ❌
 *     og:image        a 92px "0%" beside a bar drawn at its 3% floor — the
 *                     picture contradicting its own number in one frame     ❌
 *     the page        "CHAMPIONSHIP  <1%"                             (#7710) ✅
 *
 *   /futures/400   (La Liga Winner, `status: open`, Barcelona at 0.995)
 *     og:title        "Barcelona 100% - La Liga Winner"                     ❌
 *     og:image        a 96px "100%" above a bar clamped to 97               ❌
 *
 * `0%` does not read as "unlikely", it reads as IMPOSSIBLE (UX-P046's opening
 * sentence), and "100%" over an open market in the second week of a league
 * season is a claim nobody made. Neither number is a rendering nicety: they are
 * the only number on the most public screen we have.
 *
 * ═══ REACH, SO THIS IS NOT ONE ORIOLE ═══
 *
 * Single db-query over open markets, 2026-09-21:
 *
 *   (0, 0.005)      6,799 outcomes, 120 of them the rank-1 leader a share NAMES
 *   [0.995, 1)      1,904 outcomes,   891 of them that leader
 *   the four #3867  1,715 outcomes,   388 of them that leader
 *     wire values (0.145 / 0.285 / 0.565 / 0.575), where `renderedPercent`
 *     recovers the quoted decimal and the old share rounding did not
 *
 * ═══ WHAT THIS FILE ASSERTS, AND IN WHICH DIRECTION ═══
 *
 * Both, per gotcha #43. The boundary must APPEAR where a value is inside (0, 1),
 * and the two things that must not move must be shown still not moving — an
 * exact 0 still dropping the number entirely, an exact 1 still printing plainly.
 * A fix that marked everything would satisfy half of this file, and it is the
 * obvious way to "pass" it.
 *
 * The specimens are driven through the REAL routes rather than the formatter,
 * because the formatter agreeing with itself is not the ship: the ship is that
 * the sentence and the picture a stranger receives both changed.
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

import TeamOgImage from "@/app/sport/[sport]/[league]/team/[team]/opengraph-image";
import FuturesOgImage from "@/app/futures/[id]/opengraph-image";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import { buildTeamShareCopy, classifyTeamShare } from "@/lib/teamShareMeta";
import { futuresBoardPrice } from "@/lib/futuresDetailDisplay";
import { eventConceptShareFacts } from "@/lib/eventConceptShareMeta";
import { tournamentShareFacts } from "@/lib/tournamentShareMeta";
import {
  ABOVE_NINETY_NINE_PERCENT,
  BELOW_ONE_PERCENT,
  formatProbabilityPercent,
} from "@/lib/probabilityDisplay";
import { renderedPercent } from "@/lib/renderedPercent";
import { formatShareProbability } from "@/lib/share";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * `GET /api/teams/10738`, 2026-09-21, trimmed to what these two surfaces read.
 *
 * The three `championship_path` rows are production's own. `teamHeadline` takes
 * the tier-1 entry, so 0.004 — the value the `og:description` printed as "0%" —
 * is the number under test, and the two rows behind it are carried so the
 * headline is CHOSEN here rather than being the only candidate.
 */
const ORIOLES = {
  team: {
    id: 10738,
    slug: "baltimore-orioles-mlb",
    name: "Baltimore Orioles",
    abbreviation: "BAL",
    sport_key: "baseball_mlb",
    sport_name: "MLB",
    location: "Baltimore",
    primary_color: "#df4601",
    secondary_color: "#000000",
    logo_small: null,
    logo_large: null,
    record: "75-81",
    standings: {
      pct: ".481",
      wins: 75,
      losses: 81,
      div_rank: 5,
      division: "East",
      conference: "American League",
    },
    season_stats: null,
    roster: null,
  },
  championship_path: [
    {
      tier: 1,
      label: "Championship",
      market_name: "MLB: 2026 AL Hank Aaron Winner",
      market_id: 206625,
      probability: 0.004,
      rank: 5,
      movement: -0.001,
      season: "2026",
    },
    {
      tier: 2,
      label: "Conference",
      market_name: "American League Cy Young Finalists",
      market_id: 58728334,
      probability: 0.0251,
      rank: 19,
      movement: null,
      season: "2026",
    },
    {
      tier: 4,
      label: "Division",
      market_name: "MLB: 2026 AL East Champion",
      market_id: 199055,
      probability: 0.001,
      rank: 5,
      movement: null,
      season: "2026",
    },
  ],
  futures: [],
};

const ORIOLES_ROUTE = {
  sport: "baseball",
  league: "mlb",
  team: "baltimore-orioles-mlb",
};

/**
 * `GET /api/futures/400`, 2026-09-21 — the market whose `og:title` read
 * "Barcelona 100% - La Liga Winner" while `status` was `open`.
 *
 * The two rivals behind Barcelona really are served at 0.0 (the board is 20
 * outcomes deep and only the leader is priced). They are carried because they
 * are the population the `0 -> null` contract sheds, so the SAME fixture proves
 * the marker appeared and the zeros stayed silent.
 */
const LA_LIGA = {
  id: 400,
  name: "La Liga Winner",
  status: "open",
  llm_sport_category: "soccer",
  sport_name: "Soccer",
  outcome_count: 20,
  hook_description: null,
  outcomes: [
    {
      name: "Barcelona",
      probability: 0.995,
      probability_change_24h: null,
      is_winner: null,
    },
    { name: "Oviedo", probability: 0.0, probability_change_24h: null, is_winner: null },
    { name: "Mallorca", probability: 0.0, probability_change_24h: null, is_winner: null },
  ],
};

/* ────────────────────────────── the harness ────────────────────────────── */

function respondWith(status: number, body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/**
 * Every string a card DRAWS, as one blob.
 *
 * `renderToStaticMarkup` and not a walk over `element.props`: `UnfurlCard` takes
 * its strings as props, so a props-blind reader returns nothing and scores every
 * absence below as a pass. `teamUnfurlCard.test.tsx` carries the mutation that
 * proves the point; this file inherits the technique and re-proves the rig is
 * not blind in its first two tests before asserting any absence.
 */
function drawn(element: React.ReactElement): string {
  return renderToStaticMarkup(element)
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

async function drawTeamCard(body: unknown): Promise<string> {
  mockImageResponseCalls.length = 0;
  respondWith(200, body);
  await (TeamOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: Promise.resolve(ORIOLES_ROUTE),
  });
  if (mockImageResponseCalls.length !== 1) {
    throw new Error(`expected 1 ImageResponse, got ${mockImageResponseCalls.length}`);
  }
  return drawn(mockImageResponseCalls[0]);
}

async function drawFuturesCard(body: unknown): Promise<string> {
  mockImageResponseCalls.length = 0;
  respondWith(200, body);
  await (FuturesOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: { id: String((body as { id: number }).id) },
  });
  if (mockImageResponseCalls.length !== 1) {
    throw new Error(`expected 1 ImageResponse, got ${mockImageResponseCalls.length}`);
  }
  return drawn(mockImageResponseCalls[0]);
}

async function futuresWords(body: unknown): Promise<string> {
  respondWith(200, body);
  const meta = await (futuresMetadata as unknown as (a: {
    params: unknown;
  }) => Promise<{ title?: unknown; description?: unknown }>)({
    params: Promise.resolve({ id: String((body as { id: number }).id) }),
  });
  return `${String(meta.title ?? "")} ${String(meta.description ?? "")}`;
}

const oriolesWords = () =>
  buildTeamShareCopy(
    classifyTeamShare({ ok: true, payload: ORIOLES }, "baseball"),
    "mlb",
  ).description;

/* ─────────────────────── the rig, before it is trusted ─────────────────── */

describe("the reader can see these two cards at all", () => {
  it("the team card draws the Orioles' own facts", async () => {
    const card = await drawTeamCard(ORIOLES);
    expect(card).toContain("Baltimore Orioles");
    expect(card).toContain("Championship");
    expect(card).toContain("75-81");
  });

  it("the market card draws La Liga's own facts", async () => {
    const card = await drawFuturesCard(LA_LIGA);
    expect(card).toContain("La Liga Winner");
    expect(card).toContain("Barcelona");
  });
});

/* ──────────────────────── the two filed specimens ───────────────────────── */

describe("#7716 the sentence and the picture stop claiming a boundary", () => {
  it("the Orioles unfurl no longer says 0% to win the championship", () => {
    const description = oriolesWords();
    // The filed string, verbatim, is gone.
    expect(description).not.toContain("Baltimore Orioles: 0%");
    expect(description).toContain(`Baltimore Orioles: ${BELOW_ONE_PERCENT} to win`);
  });

  it("the Orioles CARD draws the same number the sentence does", async () => {
    const card = await drawTeamCard(ORIOLES);
    expect(card).toContain(BELOW_ONE_PERCENT);
    // The whole defect was a 92px zero, so it is scored as an absence too — and
    // the rig above proved it can see this card's strings before this ran.
    expect(card).not.toMatch(/(^|\s)0%/);
  });

  it("the La Liga market stops unfurling a certainty while it is open", async () => {
    const words = await futuresWords(LA_LIGA);
    expect(words).not.toContain("Barcelona 100%");
    expect(words).toContain(`Barcelona ${ABOVE_NINETY_NINE_PERCENT}`);

    const card = await drawFuturesCard(LA_LIGA);
    expect(card).toContain(ABOVE_NINETY_NINE_PERCENT);
    expect(card).not.toMatch(/(^|\s)100%/);
  });

  it("a DUEL's underdog gets the marker too, on the one path the formatter misses", () => {
    // `pairedDuel` prints its two percents WITHOUT going back through
    // `formatShareProbability` — deliberately, because a pair's integers are
    // decided together or they sum to 101 (#6849). That made it the one share
    // path the shared formatter cannot reach, and it re-acquired the low half of
    // this defect: a hand-built `${second}%` rounded 0.004 to a flat "0%" beside
    // a favourite, which is the "impossible" render UX-P046 refuses.
    //
    // 0.6 / 0.004 and not a complement: a pair totalling ~1.0 with an underdog
    // this small pushes the favourite to 100 and `pairedDuel` withholds the board
    // whole two lines earlier, so the complement shape can never exercise this.
    const facts = eventConceptShareFacts({
      event: { name: "Power Slap 23", status: "live" },
      primary: {
        label: "Main event",
        competitors: [
          { name: "Brandon Wilson", probability: 0.6 },
          { name: "Brian Ellis", probability: 0.004 },
        ],
      },
    });
    expect(facts.priced.map((c) => c.probability)).toEqual(["60%", BELOW_ONE_PERCENT]);
  });

  it("the market's two 0.0 rivals stay silent on the same card", async () => {
    // Same fixture, opposite contract: the marker arrived for the leader and the
    // `0 -> null` drop is untouched for the rows behind it. Asserting these on
    // ONE payload is what stops a later "just mark everything" from passing.
    const card = await drawFuturesCard(LA_LIGA);
    expect(card).not.toContain("Oviedo");
    expect(card).not.toContain(BELOW_ONE_PERCENT);
  });
});

/* ─────────────────── the contract that deliberately did not move ─────────── */

describe("an exact zero still means 'say no number', not 'say <1%'", () => {
  it("the formatter returns null, which is what every caller branches on", () => {
    expect(formatShareProbability(0)).toBeNull();
    // Not the same question: `formatProbabilityPercent` prints a zero plainly,
    // because ITS callers keep their own em-dash rule. The two functions differ
    // on exactly this input and that difference is the reason this one survives.
    expect(formatProbabilityPercent(0)).toBe("0%");
  });

  it("the three surfaces that withhold on it still withhold", () => {
    // `futuresBoardPrice` — a board nobody has priced draws no 96px number.
    expect(futuresBoardPrice({ name: "Oviedo", probability: 0 })).toBeNull();

    // `pricedCompetitors` — the field behind a settled winner is shed whole.
    const field = eventConceptShareFacts({
      event: { name: "Amgen Irish Open", status: "live" },
      primary: {
        competitors: [
          { name: "Shane Lowry", probability: 0.85 },
          { name: "Ryan Gerard", probability: 0.0 },
          { name: "Marco Penge", probability: 0.0 },
        ],
      },
    });
    expect(field.priced.map((c) => c.name)).toEqual(["Shane Lowry"]);

    // `boardLeader` — a draw whose leader has no price says nothing numeric.
    const board = tournamentShareFacts({
      title: "T",
      subtitle: null,
      boards: [{ label: "Men's Singles", rows: [{ display_name: "A", probability: 0 }] }],
    });
    expect(board.leaders).toEqual([]);
  });

  it("an exact one still prints plainly — that IS a boundary", () => {
    expect(formatShareProbability(1)).toBe("100%");
  });

  it("a non-finite value is no number at all, where it used to print one", () => {
    // `Math.round(Infinity * 100)` printed "Infinity%" into a share sentence.
    // `NaN` was already caught; this widens the same guard to its sibling.
    expect(formatShareProbability(Number.POSITIVE_INFINITY)).toBeNull();
    expect(formatShareProbability(Number.NEGATIVE_INFINITY)).toBeNull();
    expect(formatShareProbability(Number.NaN)).toBeNull();
    expect(formatShareProbability(null)).toBeNull();
    expect(formatShareProbability(undefined)).toBeNull();
  });
});

/* ────────────────────────── one rule, not a second copy ─────────────────── */

describe("the share percent IS the page percent", () => {
  /**
   * The ship stated as an equivalence rather than as a list of cases.
   *
   * A case list is satisfiable by special-casing the two boundaries and leaving
   * the middle on the old rounding — which is where #3867's four wire values
   * live, and they are 388 rank-1 leaders on open markets today. Sweeping the
   * whole grid is the only form of this assertion a partial fix fails.
   */
  it("agrees with `formatProbabilityPercent` on every finite non-zero value", () => {
    const disagreements: Array<[number, string | null, string]> = [];
    for (let thousandths = 1; thousandths <= 1000; thousandths += 1) {
      const p = thousandths / 1000;
      const share = formatShareProbability(p);
      const page = formatProbabilityPercent(p);
      if (share !== page) disagreements.push([p, share, page]);
    }
    expect(disagreements).toEqual([]);
  });

  it("the four wire values #3867 measured now print the page's answer", () => {
    // Measured live on open markets 2026-09-21: 1,715 outcomes, 388 of them a
    // rank-1 leader. The old share rounding printed the left number.
    const moved: Array<[number, number]> = [
      [0.145, 15],
      [0.285, 29],
      [0.565, 57],
      [0.575, 58],
    ];
    for (const [p, expected] of moved) {
      expect([p, formatShareProbability(p)]).toEqual([p, `${expected}%`]);
      // Derived, not asserted twice: the page's own contract is the authority.
      expect([p, renderedPercent(p)]).toEqual([p, expected]);
      // And the rule this replaced, spelled out, so the delta is in the file.
      expect(Math.round(p * 100)).toBe(expected - 1);
    }
  });
});

/* ───────────────────────────── the fixed boxes ──────────────────────────── */

describe("the marker fits the slots Satori will not reflow", () => {
  /**
   * The directive's third worry, answered by measurement rather than by an
   * argument about glyph widths.
   *
   * A share percent is drawn at 92px in `UnfurlCard`'s hero row and 96px on
   * `/futures/[id]`'s card, into a slot nothing wraps. The claim is that the
   * LONGEST string this rule can now produce is one those slots already drew:
   * `>99%` is four characters, exactly as many as the `100%` it replaces, and
   * `<1%` is three against `0%`'s two — shorter than `100%` either way.
   *
   * Asserted against what the CARD actually drew, not against the formatter, so
   * a future card that re-formats its own number is in scope.
   */
  it("neither card draws a percent longer than the 100% it always drew", async () => {
    const percentsIn = (blob: string) => blob.match(/[<>]?\d+%/g) ?? [];

    const teamCard = await drawTeamCard(ORIOLES);
    const marketCard = await drawFuturesCard(LA_LIGA);

    const widest = [...percentsIn(teamCard), ...percentsIn(marketCard)]
      .map((p) => p.length)
      .reduce((a, b) => Math.max(a, b), 0);

    // Non-zero first: a card drawing no percent at all would pass a bare `<= 4`.
    expect(percentsIn(teamCard).length + percentsIn(marketCard).length).toBeGreaterThan(0);
    expect(widest).toBeLessThanOrEqual("100%".length);
  });

  it("the marker survives rendering rather than being escaped away", async () => {
    // `<` and `>` are the two characters an HTML-ish renderer is most likely to
    // eat. The blob above un-escapes entities on purpose, so this asserts the
    // RAW markup carries them — otherwise the test would pass on a card drawing
    // `&lt;1%` to a reader.
    mockImageResponseCalls.length = 0;
    respondWith(200, ORIOLES);
    await (TeamOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
      params: Promise.resolve(ORIOLES_ROUTE),
    });
    const raw = renderToStaticMarkup(mockImageResponseCalls[0]);
    expect(raw).toMatch(/(&lt;|<)1%/);
  });
});
