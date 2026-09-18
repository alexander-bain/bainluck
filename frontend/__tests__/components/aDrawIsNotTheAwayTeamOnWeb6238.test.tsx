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
  /** Exactly the shape `page.tsx` now passes, so this tests the call site's decision. */
  const renderFor = (sport: string, homeProb: number, homePct: number, away: number, awayPct: number) =>
    renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={homeProb}
        awayProb={printableAway(away, sport)}
        homePct={homePct}
        awayPct={printableAway(awayPct, sport)}
        awayWithheld={sportPricesADraw(sport)}
      />,
    );

  const raw = (props: Partial<React.ComponentProps<typeof EventHeroProbabilityPair>>) =>
    renderToStaticMarkup(
      <EventHeroProbabilityPair homeProb={null} awayProb={null} homePct={null} awayPct={null} {...props} />,
    );

  /**
   * 🔴 THE FIRST CUT OF THIS SHIP PASSED ITS TESTS AND LOOKED BROKEN.
   *
   * Nulling the away side alone is the em-dash path, and at `text-[48px]
   * font-black` an em-dash is a ~41px solid rectangle: the 390px LOOK showed
   * `69% – ▬%`, a grey redaction bar trailed by a naked `%`. Twelve green tests
   * did not see it. These assertions are what that LOOK bought — the slot is
   * OMITTED, so there is no dash and no orphan `%` to draw.
   */
  it("the León specimen draws one number and omits the away slot entirely", () => {
    const html = renderFor(LIGA_MX, 0.683, 68, 0.317, 32);
    expect(html).toContain(">68<");
    expect(html).not.toContain(">32<");
    // No redaction bar, and no separator left dangling after it.
    expect(html).not.toContain("—");
    expect(html).not.toContain("–");
    // Exactly one `%` survives — the home one. Two would mean an orphan.
    expect(html.match(/>%</g) ?? []).toHaveLength(1);
  });

  it("the same numbers on an NFL page still print BOTH — the control", () => {
    const html = renderFor("americanfootball_nfl", 0.683, 68, 0.317, 32);
    expect(html).toContain(">68<");
    expect(html).toContain(">32<");
    expect(html).toContain("–");
    expect(html.match(/>%</g) ?? []).toHaveLength(2);
  });

  it("a two-way page renders byte-identically to a page with no rule at all", () => {
    // The strongest form of "nothing else moved": an equivalence, not a word-ban.
    // A ranking or a relabelling cannot survive a byte comparison.
    expect(renderFor("basketball_nba", 0.683, 68, 0.317, 32)).toBe(
      raw({ homeProb: 0.683, awayProb: 0.317, homePct: 68, awayPct: 32 }),
    );
  });

  /**
   * THE OTHER DIRECTION, AND THE REASON `awayWithheld` IS A SEPARATE PROP.
   * A genuinely ABSENT away reading on a two-way sport still draws the em-dash,
   * because there it means "we have no number for this side" — which is a true
   * statement and a different one. Inferring the omission from `awayProb ===
   * null` would have silently changed that case too.
   */
  it("an absent away reading on a two-way sport still dashes — unchanged", () => {
    const html = raw({ homeProb: 0.683, awayProb: null, homePct: 68, awayPct: null });
    expect(html).toContain("—");
    expect(html).toContain(">68<");
  });

  it("withholding away does NOT collapse the hero into the no-price copy", () => {
    // #3459's both-null case draws words instead of two redaction bars; one
    // withheld side must not be mistaken for that.
    const html = renderFor(LIGA_MX, 0.683, 68, 0.317, 32);
    expect(html).not.toContain("No price");
    expect(html).toContain(">68<");
  });

  it("the home probability still reaches the rail that cross-checks the card", () => {
    // UX-P003: `data-probability` is the PROBABILITY and is asserted against the
    // Discover card linking here. Withholding the away slot must not disturb it.
    expect(renderFor(LIGA_MX, 0.683, 68, 0.317, 32)).toContain('data-probability="0.683"');
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

  /**
   * ═══ #6614 NARROWED THIS FROM FOUR TO TWO, BY MEASUREMENT ═══
   *
   * This read "all four away values", and that was right for as long as both
   * pairs on the page were believed to be the same kind of object. They are
   * not. `current_odds.away_probability` is derived as `1 - home`;
   * `opening_odds` is de-vigged across the whole quoted board (#1011), so its
   * two legs are real independently sourced prices summing to ~0.76.
   *
   * Measured on production 2026-09-18, `/api/feed?mode=sports`, 25 soccer
   * cards: `current_odds` is a complement on 25/25, `opening_odds` on only
   * 16/25. The blanket rule was deleting a real away price on the other 9 —
   * `/events/15298749`, a 21% underdog that WON, printed no pregame mark at all.
   *
   * So the CURRENT pair keeps `printableAway` verbatim (that is still the whole
   * protection, and the arm below is unchanged), and the OPENING pair moves to
   * the per-pair `awayIsTheComplement`. This is a narrowing of the rule's
   * DOMAIN, not a relaxation of it: #6238's defect — a served away value
   * reaching a render unguarded — is still caught on both pairs.
   */
  it("the CURRENT away values are taken through printableAway", () => {
    for (const name of ["servedAwayProb", "servedAwayPct"]) {
      expect(PAGE).toMatch(new RegExp(`printableAway\\(${name},\\s*event\\.sport\\)`));
    }
  });

  it("#6614 — the OPENING away values are taken through the per-PAIR rule", () => {
    // The predicate is asked about this pair's own two legs...
    expect(PAGE).toMatch(
      /const openingAwaySlotWithheld = awayIsTheComplement\(\s*servedOpeningAwayProb,\s*openingHomeProb,\s*event\.sport,?\s*\)/,
    );
    // ...and both values are gated on its answer.
    for (const name of ["servedOpeningAwayProb", "servedOpeningAwayPct"]) {
      expect(PAGE).toMatch(
        new RegExp(`openingAwaySlotWithheld \\? null : ${name}`),
      );
    }
    // #6238's defect, still refused: neither opening value may reach a render
    // as the raw served figure.
    expect(PAGE).not.toMatch(/openingAwayProb=\{servedOpeningAwayProb\}/);
    expect(PAGE).not.toMatch(/rendered: servedOpeningAwayPct/);
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

  it("the hero is told to OMIT the slot, not just handed a null", () => {
    // Without this the page renders the redaction bar the LOOK caught.
    expect(PAGE).toMatch(/awayWithheld=\{awaySlotWithheld\}/);
    expect(PAGE).toMatch(/const awaySlotWithheld = sportPricesADraw\(event\.sport\)/);
  });

  it("the opening line is covered too, not just the hero", () => {
    // #5696's lesson: a hero that withholds above an `Opened 64% – 36%` line that
    // does not has moved the false number three rows down, not deleted it.
    expect(PAGE).toMatch(/Opened \{formatProbability\(openingHomeProb/);
    // …and its separator is gated with it, or the line reads `Opened 64% – -`.
    //
    // #6614: gated on the OPENING pair's own answer. Gating it on
    // `awaySlotWithheld` — the hero pair's — is what deleted `Opened 32% – 40%`
    // down to `Opened 32%` on 9 of 25 live soccer cards. The two loci on one
    // screen legitimately answer differently, because they are two different
    // pairs from two different producers.
    expect(PAGE).toMatch(/!openingAwaySlotWithheld && <>[\s\S]{0,80}openingAwayProb/);
  });
});

describe("#6238 the chart readout — the gap this ship named, now CLOSED", () => {
  /**
   * ✅ CLOSED by ux/1292 (2026-09-16). This block used to pin the gap OPEN — it
   * asserted that `GamePlayCard` still re-derived its away percent — and it is
   * rewritten rather than deleted so the two halves of #6238 stay legible from
   * one file.
   *
   * It is NOT a frozen verbatim control (notice 50): its content was never the
   * defect, it was a NOTE saying "not yet covered", and a note whose subject is
   * covered is simply false. The evidence it carried is preserved in
   * `chartReadoutWithholdsTheDraw6238.test.tsx`, which owns the behaviour; this
   * keeps only the structural fact that the card was told at all, so deleting
   * the prop cannot go green here.
   *
   * What the second half found, worth keeping in one sentence: the readout had
   * moved on from the `Citizen 63% — Steelers 37%` recorded above. Re-shot on
   * 2026-09-16 the same page read **`2 - 2   Citizen 1% — Steelers 99%`** — the
   * blend's last point is `home 0.01`, so the complement handed the whole draw
   * price to a team the page's own markets card marks `Lost`.
   */
  it("GamePlayCard takes the withholding decision, and takes it as a prop", () => {
    const card = readFileSync(join(__dirname, "..", "..", "components", "GamePlayCard.tsx"), "utf8");
    expect(card).toMatch(/awayWithheld\?: boolean/);
    expect(card).toMatch(/!awayWithheld && \(/);
  });

  it("the away half is the ONLY thing gated — the home number is unconditional", () => {
    // The failure mode of a withheld pair is withholding the wrong half, or
    // both. The reader keeps the one number we can source.
    const card = readFileSync(join(__dirname, "..", "..", "components", "GamePlayCard.tsx"), "utf8");
    const gated = card.match(/!awayWithheld && \(/g) || [];
    expect(gated).toHaveLength(1);
    expect(card).not.toMatch(/awayWithheld && [\s\S]{0,40}homeProb/);
  });
});
