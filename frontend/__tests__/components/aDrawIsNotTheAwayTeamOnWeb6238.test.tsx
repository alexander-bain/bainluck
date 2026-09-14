/**
 * #6238 — THE WEB EVENT HERO PRINTED A TWO-WAY COMPLEMENT ON A THREE-WAY MARKET.
 *
 * Photographed on production 2026-09-14 by authority/322 under D48 —
 * `/events/15301234`, León v Atlético San Luis, Liga MX, 2h pre-match, 390px.
 * My own BEFORE capture (`artifacts/ux-1266/before-6238-15301234-hero.png`)
 * reads:
 *
 *     L  **68**% – **32**%  ASL
 *     León        7 sportsbooks        Luis
 *
 * while the SAME PAGE's correct-score card puts 0-0 at 22% and 1-1 at 10%. The
 * served away figure is `1 − home` exactly — read from production the same hour,
 * `home_probability 0.683 / away_probability 0.317` — so what sat under San
 * Luis's crest was "León does not win", which is *away win OR draw*.
 *
 * Measured against the books: draftkings −115/+285 implies 53.5%/26.0%, summing
 * to **79.5%**. We divide by that sum to strip vig, which is right for a two-way
 * market and wrong here. León was overstated by ~14pp.
 *
 * This is the web twin of #5271, which native fixed on 2026-09-11. Before this
 * ship the ONLY path outside `ios/` naming the flag was
 * `__tests__/ios/aDrawIsNotTheAwayTeam5271.test.ts` — a jest test that scans the
 * *Swift source*. The guard lived in one client; the other client was unguarded
 * and nothing went red.
 *
 * ## 🔴 WHAT THIS SHIP DOES NOT FIX, ASSERTED RATHER THAN LEFT TO BE DISCOVERED
 *
 * 1. The home number it KEEPS is still draw-dropped (#1011). 68% is not 53%.
 *    `TestTheRetainedHomeNumberIsNotClaimedCorrect` pins that this ship does not
 *    touch it, so nobody reads the merge as #1011 landing.
 * 2. The chart readout below the hero (`GamePlayCard`) is NOT covered — it reads
 *    `point.awayProb`, not the page's. See the last describe block, which pins
 *    the exact reason so the next session does not have to rediscover it.
 *
 * Guards run BOTH directions per gotcha #43: soccer withholds, and a two-way
 * sport is asserted BYTE-IDENTICAL.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { printableAway, sportPricesADraw } from "@/lib/drawPricedWinner";
import { sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";

/** The two real production specimens on the issue, by their real sport keys. */
const LIGA_MX = "soccer_mexico_ligamx"; // /events/15301234, the p1 screenshot
const K_LEAGUE = "soccer_korea_kleague1"; // /events/15305024, finished 2–2

describe("#6238 which sports price a draw — declared, never sniffed", () => {
  /**
   * The specimens matter more than the canonical keys: neither `ligamx` nor
   * `kleague1` is named anywhere in the vocab, and both are covered only because
   * `sportVocab` matches the substring "soccer". A rule written as a list of
   * leagues would have missed both of the events this issue is about.
   */
  it.each([LIGA_MX, K_LEAGUE, "soccer_epl", "soccer_uefa_champs_league", "soccer_usa_mls"])(
    "%s prices a draw",
    (key) => {
      expect(sportPricesADraw(key)).toBe(true);
    },
  );

  it.each([
    "americanfootball_nfl",
    "basketball_nba",
    "baseball_mlb",
    // Level after overtime is settled by a shootout, so the winner market has
    // two outcomes and the complement is honest.
    "icehockey_nhl",
    "tennis_atp_us_open",
  ])("%s does NOT price a draw", (key) => {
    expect(sportPricesADraw(key)).toBe(false);
  });

  it("an undeclared or absent sport keeps its two-sided reading", () => {
    // The polarity that makes widening this rule opt-in: silence means "we have
    // not said", never "withhold".
    expect(UNSCORED_IN_POINTS.winnerMarketPricesADraw).toBe(false);
    expect(sportPricesADraw("cricket_ipl")).toBe(false);
    expect(sportPricesADraw(undefined)).toBe(false);
    expect(sportPricesADraw(null)).toBe(false);
    expect(sportPricesADraw("")).toBe(false);
  });

  it("soccer is the ONLY row that says yes", () => {
    // Guards the widening directly: a future row added with `true` by habit
    // reddens here, at the declaration, rather than silently withholding a
    // number on a sport nobody measured.
    const yes = ["baseball_mlb", "icehockey_nhl", "soccer_epl", "tennis_atp", "basketball_nba", "americanfootball_nfl"]
      .filter((k) => sportVocab(k).winnerMarketPricesADraw);
    expect(yes).toEqual(["soccer_epl"]);
  });
});

describe("#6238 printableAway withholds on a draw-priced sport and passes through elsewhere", () => {
  it("the specimen's served away price is withheld", () => {
    expect(printableAway(0.317, LIGA_MX)).toBeNull();
  });

  it("a two-way sport gets its served away price UNCHANGED — the other direction", () => {
    expect(printableAway(0.317, "americanfootball_nfl")).toBe(0.317);
    expect(printableAway(32, "basketball_nba")).toBe(32);
  });

  it("an already-absent away price stays absent on both kinds of sport", () => {
    expect(printableAway(null, LIGA_MX)).toBeNull();
    expect(printableAway(null, "americanfootball_nfl")).toBeNull();
  });

  /**
   * 🔴 THE REGRESSION THIS SHIP COULD EASILY HAVE CAUSED, PINNED.
   *
   * Native's `printablePair` answers nil for the WHOLE pair when either side is
   * missing on a two-way sport. Porting that shape literally to the web would
   * have withheld the home number too on every two-way event whose away price is
   * absent — the hero prints `68% – —%` there today. The web helper takes the
   * narrower question deliberately; this is the assertion that keeps it narrow.
   */
  it("withholding is scoped to the away side and never reaches home", () => {
    // Zero is a real probability and must survive a truthiness bug.
    expect(printableAway(0, "americanfootball_nfl")).toBe(0);
    expect(printableAway(0, LIGA_MX)).toBeNull();
  });
});

describe("#6238 what the hero actually renders", () => {
  const render = (homeProb: number | null, awayProb: number | null, homePct: number | null, awayPct: number | null) =>
    renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={homeProb}
        awayProb={awayProb}
        homePct={homePct}
        awayPct={awayPct}
      />,
    );

  /**
   * The served pair from production on the specimen, run through the rule the
   * page now applies. 32 must not appear; the em-dash must.
   */
  it("the León specimen draws 68 and withholds 32", () => {
    const html = render(0.683, printableAway(0.317, LIGA_MX), 68, printableAway(32, LIGA_MX));
    expect(html).toContain(">68<");
    expect(html).not.toContain(">32<");
    expect(html).toContain("—");
  });

  it("the same numbers on an NFL page still print BOTH — the control", () => {
    const html = render(0.683, printableAway(0.317, "americanfootball_nfl"), 68, printableAway(32, "americanfootball_nfl"));
    expect(html).toContain(">68<");
    expect(html).toContain(">32<");
    expect(html).not.toContain("—");
  });

  it("a two-way page renders byte-identically to a page with no rule at all", () => {
    // The strongest form of "nothing else moved": not a word-ban, an equivalence.
    expect(render(0.683, printableAway(0.317, "basketball_nba"), 68, printableAway(32, "basketball_nba")))
      .toBe(render(0.683, 0.317, 68, 32));
  });

  /**
   * The home side keeps its reading, which is the difference between
   * "we withheld one number" and "this hero has no numbers" (#3459: both-null
   * draws the words instead of two 48px em-dash bars trailed by naked `%`).
   */
  it("withholding away does NOT collapse the hero into the no-price copy", () => {
    const html = render(0.683, null, 68, null);
    expect(html).not.toContain("No price");
    expect(html).toContain(">68<");
  });
});

describe("#6238 the retained home number is NOT claimed to be correct", () => {
  /**
   * 🔴 READ THIS BEFORE CLOSING #6238.
   *
   * The specimen's books imply León at 53.5%. The page still prints 68, because
   * the blend itself is normalised two ways with the draw discarded — a DATA
   * defect, #1011, at ingest. This ship is the render half only, exactly as
   * #5271 was for native.
   *
   * This test exists so that "the hero agrees with the three-way card" is never
   * mistaken for something this merge delivered.
   */
  it("the hero still prints the draw-dropped home number, unchanged", () => {
    // 68, not the ~53 the raw moneylines imply. Asserted as OUTPUT so the claim
    // is about the reader's screen and not about a helper's return value.
    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.683}
        awayProb={printableAway(0.317, LIGA_MX)}
        homePct={68}
        awayPct={printableAway(32, LIGA_MX)}
      />,
    );
    expect(html).toContain(">68<");
    expect(html).not.toContain(">53<");
  });

  it("the page hands homeProb straight through — no home-side rule exists to drift", () => {
    const page = readFileSync(join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"), "utf8");
    // The destructure renames the four AWAY values and leaves `homeProb` bare.
    expect(page).toMatch(/const \{\s*\n\s*homeProb,/);
    expect(page).not.toMatch(/homeProb:\s*servedHomeProb/);
    expect(page).not.toMatch(/printableHome/);
  });
});

describe("#6238 the event page is actually wired to the rule", () => {
  /**
   * 🔴 THE LIMIT OF THIS ARM, STATED. The behavioural cases above exercise the
   * real helper and the real component, but none of them proves `page.tsx` calls
   * it — which is exactly the shape that let this ship, since native's rule has
   * existed since 2026-09-11 and the web simply never had one.
   *
   * The event page is a 2,000-line Next.js route module with no exported unit to
   * render, so this arm reads the SOURCE and says so rather than dressing itself
   * up as a render assertion. It is not decorative: the defect WAS the served
   * away value reaching the hero, so a guard that reddens when it comes back is
   * the regression this needs.
   */
  const PAGE = readFileSync(
    join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"),
    "utf8",
  );

  it("all four away values are taken through printableAway", () => {
    for (const name of ["servedAwayProb", "servedAwayPct", "servedOpeningAwayProb", "servedOpeningAwayPct"]) {
      expect(PAGE).toMatch(new RegExp(`printableAway\\(${name},\\s*event\\.sport\\)`));
    }
  });

  it("the served away values are renamed at the destructure, so none can reach a render", () => {
    // If `awayProb` came straight out of `resolveProbability` again, the four
    // `const` declarations below it would be a redeclaration and the build would
    // fail — but only if the rename survives. This pins the rename itself.
    expect(PAGE).toMatch(/awayProb:\s*servedAwayProb/);
    expect(PAGE).toMatch(/openingAwayPct:\s*servedOpeningAwayPct/);
    // The defect itself: the served value handed to the hero.
    expect(PAGE).not.toMatch(/awayProb=\{servedAwayProb\}/);
    expect(PAGE).not.toMatch(/awayPct=\{servedAwayPct\}/);
  });

  it("the opening line is covered too, not just the hero", () => {
    // #5696's lesson: a hero that withholds above an `Opened 64% – 36%` line that
    // does not has moved the false number three rows down, not deleted it.
    expect(PAGE).toMatch(/Opened \{formatProbability\(openingHomeProb[\s\S]{0,120}openingAwayProb/);
  });
});

describe("#6238 the chart readout is NOT covered by this ship", () => {
  /**
   * 🔴 FOR WHOEVER TAKES THE REST OF #6238 — the measurement, so it is not
   * rediscovered.
   *
   * `/events/15305024` (Daejeon Citizen v Pohang Steelers, finished **2–2**)
   * prints `Citizen 63% — Steelers 37%` in the chart readout off terminal odds of
   * +600 / +950 — both long shots, because the draw won. That readout is
   * `GamePlayCard`, and it does NOT read the page's `awayProb`: it takes
   * `point.awayProb` off `lastChartPoint`.
   *
   * ⚠️ AND IT CANNOT SIMPLY BE FED `null`. `GamePlayCard.tsx:79` is
   * `awayPct ?? Math.round(point.awayProb * 100)` — a hard re-derivation, so a
   * null away price renders **`NaN%`**, not an em-dash. Covering it means making
   * `GamePlayPoint.awayProb` nullable and giving that card its own withheld
   * render, which is a second component decision and a separate ship.
   *
   * Native did cover its equivalent (`OddsChartView.swift:1602`), so the web is
   * the client still behind here.
   */
  it("GamePlayCard still re-derives its away percent — the named gap", () => {
    const card = readFileSync(join(__dirname, "..", "..", "components", "GamePlayCard.tsx"), "utf8");
    expect(card).toMatch(/Math\.round\(point\.awayProb \* 100\)/);
  });
});
