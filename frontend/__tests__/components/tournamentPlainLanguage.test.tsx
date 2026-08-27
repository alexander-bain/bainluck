/**
 * UX-P145 — THE TOURNAMENT SURFACES DO NOT SPEAK TO USERS IN OUR WORDS.
 *
 * Alex, reading /tournaments/us-open in a desktop browser on 2026-08-27:
 *
 *   > The props empty-state copy is FORBIDDEN language: "3 curated questions
 *   > have gone dark and rotated out. They come back when they are priced
 *   > again." — "gone dark", "rotated out", "priced" are our internal words.
 *
 * He is right about every one of them, and the sentence is worse than the sum
 * of its words: it tells a tennis reader four facts about our ingest pipeline
 * and none about their tournament. *Curated* is our editorial step. *Gone dark*
 * is a `price_state` enum value. *Rotated out* is a render rule in
 * `curatedProps`. *Priced* is a trading verb.
 *
 * ═══ WHAT THIS FILE PINS, AND WHY IT IS A LIST AND NOT A SNAPSHOT ═══
 *
 * A snapshot of the fixed copy would go green forever and catch nothing: the
 * failure mode is not "this sentence changed", it is "somebody wrote a NEW
 * sentence in the old vocabulary", which a snapshot of the old sentence cannot
 * see. So the guard is a BANNED-WORD sweep over rendered output, plus a small
 * number of positive assertions on the strings Alex quoted.
 *
 * ═══ THE LINE THIS DRAWS ON "PRICE", WHICH IS DELIBERATE ═══
 *
 * *Priced* as a VERB done to a question or a player is jargon and is banned:
 * "nobody has priced it yet", "a priced round to reach", "they are priced
 * again". *Price* / *prices* as the NOUN a market publishes is plain English on
 * a prediction-market page, and it is the honesty vocabulary the boards, the
 * slate and the calibration page already share — "Prices paused", "the last
 * prices we saw". Ripping that out would not make the page clearer; it would
 * make three surfaces disagree about how to admit the same thing.
 *
 * This is the same line ALEX HIMSELF drew in ruling 3 (see `GRID_SECTION_LABEL`
 * in `lib/playoffGrid.ts`), where "priced to get there" became "Chance of
 * reaching" while "cells carry a market price" stayed. The rule below encodes
 * it: `BANNED` matches the verb forms and the possessive-pipeline nouns, and
 * `price`/`prices` standing alone is allowed.
 *
 * Likewise `dark`, `stale` and `register` survive as DATA — `data-price-state`,
 * `data-placeholder="register-hole"`, `data-dropped-dark`. Those are contracts
 * that CERT-411 and the sentinels read, and no user sees them. The sweep runs
 * over rendered TEXT with the attributes stripped, so it is indifferent to them
 * by construction rather than by an exception list.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import { buildMatchList } from "@/lib/matchList";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import {
  curatedProps,
  curatedPropsEmptyReason,
  type PropMarket,
  type PropOutcome,
} from "@/lib/tournamentProps";
import type { SlateData } from "@/lib/slate";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-27.json"
);

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}

/**
 * Rendered markup → the words a reader actually sees.
 *
 * Attributes go first and entities are decoded after, in that order. Stripping
 * tags without stripping attributes would drag `data-price-state="dark"` and
 * `class="border-dashed"` into the text and every banned word would "fail"
 * forever, which is how a guard like this gets deleted for crying wolf.
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The words a Bain Luck reader has no reason to know.
 *
 * Every entry is a word Alex named, in the grammatical form that makes it
 * jargon. `priced`/`prices`-as-a-verb is caught by requiring a subject-ish
 * context around it rather than by banning the stem; see the file header.
 */
const BANNED: { pattern: RegExp; why: string }[] = [
  { pattern: /\bgone dark\b/i, why: '"gone dark" is our price_state enum' },
  { pattern: /\bgoes dark\b/i, why: '"goes dark" is our price_state enum' },
  { pattern: /\bwent dark\b/i, why: '"went dark" is our price_state enum' },
  { pattern: /\brotated out\b/i, why: '"rotated out" is our render rule' },
  { pattern: /\brotation\b/i, why: '"rotation" is our render rule' },
  { pattern: /\bcurated\b/i, why: '"curated" is our editorial process' },
  { pattern: /\bcuration\b/i, why: '"curation" is our editorial process' },
  { pattern: /\bregistered\b/i, why: '"registered" is the name of our JSON file' },
  { pattern: /\bthe register\b/i, why: '"the register" is the name of our JSON file' },
  { pattern: /\bcensus(ed)?\b/i, why: '"census" is our data-collection step' },
  { pattern: /\bblend(ed|s)?\b/i, why: '"blend" is our aggregation step' },
  { pattern: /\bstale\b/i, why: '"stale" is our price_state enum' },
  // *Priced* as a verb, in every shape the surfaces actually used it.
  { pattern: /\bis priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bare priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bhas priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bthey are priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bnever priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bunpriced\b/i, why: '"unpriced" is trading vocabulary' },
  { pattern: /\ba priced\b/i, why: '"priced" as an adjective is trading vocabulary' },
  { pattern: /\bno priced\b/i, why: '"priced" as an adjective is trading vocabulary' },
  { pattern: /\bsources priced\b/i, why: '"priced" as a verb is trading vocabulary' },
  { pattern: /\bmarket prices how\b/i, why: '"prices" as a verb is trading vocabulary' },
  { pattern: /\bsource prices this\b/i, why: '"prices" as a verb is trading vocabulary' },
  { pattern: /\bis pricing\b/i, why: '"pricing" as a verb is trading vocabulary' },
];

function assertPlain(html: string, where: string) {
  const text = visibleText(html);
  for (const { pattern, why } of BANNED) {
    const hit = text.match(pattern);
    if (hit) {
      const at = text.indexOf(hit[0]);
      throw new Error(
        `${where}: internal jargon in user-visible copy — ${why}.\n` +
          `  matched: "${hit[0]}"\n` +
          `  context: …${text.slice(Math.max(0, at - 90), at + 110)}…`
      );
    }
  }
}

/**
 * Three questions, all long unread — the state Alex was looking at.
 *
 * Fully typed rather than cast: `as PropMarket[]` over a partial literal is how
 * a fixture drifts from the shape the backend emits and keeps passing anyway.
 */
function darkMarkets(): PropMarket[] {
  const outcome = (name: string, p: number, ageHours: number): PropOutcome => ({
    entity_key: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    display_name: name,
    probability: p,
    probability_is_live: false,
    observed_at: null,
    age_hours: ageHours,
    price_state: "dark",
    is_answer: name === "Yes" || name === "2+",
  });
  const market = (
    key: string,
    title: string,
    ageHours: number,
    outcomes: [string, number][]
  ): PropMarket => ({
    key,
    title,
    hook: null,
    draw: "mens-singles",
    source: "kalshi",
    outcomes: outcomes.map(([name, p]) => outcome(name, p, ageHours)),
    answer_entity_key: outcomes[0][0].toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    price_state: "dark",
    observed_at: null,
    age_hours: ageHours,
    freshest_observed_at: null,
    freshest_age_hours: ageHours,
    stale_outcomes: [],
    mixed_freshness: false,
  });
  return [
    market("sinner-competes", "Will Sinner actually play?", 190, [
      ["Yes", 0.63],
      ["No", 0.37],
    ]),
    market("sinner-second-major", "Can Sinner win a second major this year?", 810, [
      ["2+", 0.555],
      ["1", 0.445],
    ]),
    market("alcaraz-slam-count", "How many slams for Alcaraz this year?", 400, [
      ["2+", 0.4],
      ["1", 0.6],
    ]),
  ];
}

describe("UX-P145: the tournament surfaces speak the reader's language", () => {
  const payload = loadPayload();

  /* ─────────── ALEX'S SENTENCE, PINNED BOTH WAYS ─────────── */

  describe("the props empty state — the string Alex quoted", () => {
    it("no longer says any of the four words he named", () => {
      const curated = curatedProps(darkMarkets(), "mens-singles");
      // The premise: this really is the empty-with-dark-drops branch, so the
      // assertion below is about the sentence Alex read and not a sibling.
      expect(curated.markets).toHaveLength(0);
      expect(curated.dropped.dark).toBe(3);

      const reason = curatedPropsEmptyReason(curated);
      expect(reason).not.toBeNull();
      expect(reason).not.toMatch(/curated/i);
      expect(reason).not.toMatch(/gone dark/i);
      expect(reason).not.toMatch(/rotated out/i);
      expect(reason).not.toMatch(/priced/i);
    });

    it("is EXACTLY this sentence — the copy Alex signs off, pinned", () => {
      // Pinned verbatim on purpose. Alex named the replacement register ("New
      // questions are coming — check back soon."); a paraphrase that drifts
      // back toward the pipeline is the regression, and only an equality
      // catches a drift that stays inside the banned-word list.
      const curated = curatedProps(darkMarkets(), "mens-singles");
      expect(curatedPropsEmptyReason(curated)).toBe(
        "We have not seen a new number on 3 questions in a while, so they are hidden for now. " +
          "New questions are coming — check back soon."
      );
    });

    it("still tells the reader HOW MANY — the count was never the problem", () => {
      // The old sentence's one virtue: a section that quietly shrinks reads as
      // "not much is happening" when the truth is that three questions aged
      // out. Plain language must not cost the number.
      const curated = curatedProps(darkMarkets(), "mens-singles");
      expect(curatedPropsEmptyReason(curated)).toContain("3 questions");
    });

    it("reads plainly in the singular too", () => {
      const curated = curatedProps(darkMarkets().slice(0, 1), "mens-singles");
      const reason = curatedPropsEmptyReason(curated);
      expect(reason).toBe(
        "We have not seen a new number on 1 question in a while, so it is hidden for now. " +
          "New questions are coming — check back soon."
      );
      // "1 questions have" is the kind of thing a reader files under "nobody
      // looked at this", which is the opposite of what this sentence is for.
      expect(reason).not.toMatch(/1 questions/);
    });

    it("every other branch of the same function is plain as well", () => {
      // The dark branch is the one Alex saw. The other three are one bad day
      // away from being the one he sees next.
      const build = (dropped: Partial<Record<string, number>>) =>
        curatedPropsEmptyReason({
          markets: [],
          considered: 3,
          dropped: { advance: 0, resolved: 0, dark: 0, template: 0, ...dropped },
        } as never);

      for (const dropped of [{ resolved: 2 }, { template: 2 }, { advance: 8 }]) {
        const reason = build(dropped);
        expect(reason).not.toBeNull();
        assertPlain(reason as string, `curatedPropsEmptyReason(${JSON.stringify(dropped)})`);
      }
    });
  });

  /* ─────────── AND IT HAS TO SURVIVE THE RENDER ─────────── */

  it("the RENDERED empty section carries no jargon", () => {
    // Through the component, not just the pure function: the section wraps the
    // reason in two more paragraphs of its own prose, and one of those was the
    // "appear here as they are priced" line.
    const html = renderToStaticMarkup(
      <TournamentProps markets={darkMarkets()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="props-empty"');
    assertPlain(html, "TournamentProps (empty)");

    // The data contract the cert and the sentinels read is UNTOUCHED — the
    // words changed, the attributes did not.
    expect(html).toContain('data-dropped-dark="3"');
  });

  it("the RENDERED populated section carries no jargon either", () => {
    // The `props-rotated-out` line only renders when something was dropped AND
    // something survived, so it needs a mixed set: one fresh, three not.
    const fresh: PropMarket = {
      ...darkMarkets()[0],
      key: "fresh-question",
      title: "Will there be a five-setter on Ashe tonight?",
      price_state: "live",
      age_hours: 0.4,
      freshest_age_hours: 0.4,
      outcomes: darkMarkets()[0].outcomes.map((o) => ({
        ...o,
        probability_is_live: true,
        price_state: "live" as const,
        age_hours: 0.4,
      })),
    };
    const html = renderToStaticMarkup(
      <TournamentProps markets={[fresh, ...darkMarkets()]} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="prop-market"');
    expect(html).toContain('data-testid="props-rotated-out"');
    assertPlain(html, "TournamentProps (populated)");
  });

  /* ─────────── THE WHOLE SURFACE, NOT JUST THE SECTION HE CAUGHT ─────────── */

  it("the championship board is plain — on real data and when it is empty", () => {
    for (const board of payload.boards) {
      assertPlain(renderToStaticMarkup(<TournamentBoard board={board} />), `board ${board.draw}`);
    }
    // The empty board said "nobody has priced it yet"; the unpriced footer said
    // "N more registered players have no price". Both are branches real data
    // does not currently take, which is exactly why they rotted unread.
    const empty = { ...payload.boards[0], rows: [], unpriced: 0 };
    assertPlain(renderToStaticMarkup(<TournamentBoard board={empty} />), "board (empty)");

    const withUnpriced = { ...payload.boards[0], unpriced: 12 };
    const html = renderToStaticMarkup(<TournamentBoard board={withUnpriced} />);
    expect(html).toContain('data-testid="board-unpriced"');
    assertPlain(html, "board (unpriced footer)");
  });

  it("the playoff grid is plain — cells, legend, sum check and alarm banner", () => {
    const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);
    expect(grid).not.toBeNull();
    const html = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} drawLabel="Men's singles" initialExpanded />
    );
    // The `title=` attributes are the point here: `gridCellExplanation` builds
    // them from BACKEND-authored `note` strings, which is the one place on this
    // page where the copy is not in the frontend at all.
    assertPlain(html, "PlayoffGrid");
  });

  it("an ALARM cell's tooltip is plain — it names the market without our nouns", () => {
    // The alarm notes come from `tournament_grid.py` and used to read
    // "1 of 2 registered sources priced; unpriced: kalshi KXSFALCARAZ".
    // The market id must survive; the framing must not.
    const grid = readPlayoffGrid({
      draw: "mens-singles",
      label: "Men's singles",
      columns: [
        { key: "semifinals", short_label: "SF", long_label: "Reaches the semi-finals", kind: "reach", slots: 4 },
      ],
      rows: [
        {
          entity_key: "alcaraz",
          display_name: "Carlos Alcaraz",
          seed: 1,
          image: null,
          rank: 1,
          on_board: true,
          cells: {
            semifinals: {
              state: "unlinked",
              probability: null,
              probability_is_live: false,
              age_hours: null,
              source_count: 1,
              note: "We have a number from 1 of 2 markets; still missing: kalshi KXSFALCARAZ",
              blend_rule: null,
            },
          },
        },
      ],
      column_sums: [],
      monotonicity_violations: [],
      // The counters are payload-owned, not derived at read time, so the alarm
      // BANNER (a separate block of prose from the cell's tooltip, and the one
      // that says "this is a fault on our side") only renders when the server
      // says how many. Omitting them renders the cell and silently skips the
      // banner — which is how the first draft of this test passed the sweep
      // without ever sweeping the banner.
      total_cells: 1,
      priced_cells: 0,
      no_market_cells: 0,
      alarm_cells: 1,
    } as never);

    const html = renderToStaticMarkup(<PlayoffGrid grid={grid!} initialExpanded />);
    expect(html).toContain('data-testid="grid-alarm-banner"');
    // The diagnostic half survives — Alex's amendment requires the alarm to
    // name the market that did not resolve.
    expect(html).toContain("kalshi KXSFALCARAZ");
    assertPlain(html, "PlayoffGrid (alarm cell)");
  });

  it("the bracket's pre-draw notice is plain, with and without a grid", () => {
    for (const grid of [null, readPlayoffGrid(payload.grids?.["mens-singles"])]) {
      const html = renderToStaticMarkup(
        <TournamentBracket
          grid={grid}
          drawReleased={false}
          preDrawBoards={payload.boards}
          drawReleaseLabel={payload.draw_release_label}
          mainDrawLabel={payload.main_draw_label}
          initialExpanded
        />
      );
      assertPlain(html, `TournamentBracket (grid: ${grid ? "yes" : "no"})`);
    }
  });

  it("the match list is plain — real fixtures, and the placeholder slots", () => {
    const slate = payload.slate as SlateData;
    // A board row's probability is nullable — an unpriced contender is a real
    // state, and a `null` in this map would render as "null% title".
    const titleChances: Record<string, number> = {};
    for (const row of payload.boards[0].rows) {
      if (row.probability !== null) titleChances[row.entity_key] = row.probability;
    }

    const entries = buildMatchList({
      slate: slate.matches.filter((m) => m.draw === "mens-singles"),
      titleChances,
    });
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialRound="R128" initialExpanded />
    );
    assertPlain(html, "TournamentMatches");
  });

  it("finished matches are plain", () => {
    assertPlain(
      renderToStaticMarkup(
        <TournamentResults results={payload.results} draw="mens-singles" />
      ),
      "TournamentResults"
    );
  });

  /* ─────────── THE LINE ON "PRICE" IS DELIBERATE, SO IT IS PINNED ─────────── */

  it('keeps "prices" as a NOUN — the honesty language is not collateral damage', () => {
    // If a later sweep bans the stem outright, this fails, and it should: the
    // boards, the slate and the calibration page all admit staleness with this
    // exact word, and a page that words one admission three ways teaches the
    // reader that two of them are decorative.
    const dark = {
      ...payload.boards[0],
      price_state: "dark" as const,
      age_hours: 300,
      rows: payload.boards[0].rows.map((row) => ({
        ...row,
        probability_is_live: false,
        price_state: "dark" as const,
        age_hours: 300,
      })),
    };
    const html = renderToStaticMarkup(<TournamentBoard board={dark} />);
    expect(html).toContain("Prices paused");
    expect(visibleText(html)).toContain("These are the last prices we saw, not live prices.");
    assertPlain(html, "TournamentBoard (dark)");
  });

  it("the sweep can actually fail — the guard is not vacuously green", () => {
    // A banned-word test that has never seen a banned word is a test that
    // passes because its regexes are wrong. This renders the sentence Alex
    // objected to, verbatim, and requires the sweep to reject it.
    const offending = `<p>3 curated questions have gone dark and rotated out. They come back when they are priced again.</p>`;
    expect(() => assertPlain(offending, "canary")).toThrow(/curated/i);

    // …and each named word independently, so a partial regex cannot hide.
    expect(() => assertPlain("<p>it has gone dark</p>", "canary")).toThrow(/gone dark/i);
    expect(() => assertPlain("<p>two rotated out</p>", "canary")).toThrow(/rotated out/i);
    expect(() => assertPlain("<p>they are priced again</p>", "canary")).toThrow(/priced/i);
    expect(() => assertPlain("<p>12 more registered players</p>", "canary")).toThrow(/registered/i);
    expect(() => assertPlain("<p>Probabilities blended across markets</p>", "canary")).toThrow(
      /blend/i
    );
    expect(() => assertPlain("<p>this reading is stale</p>", "canary")).toThrow(/stale/i);

    // And it must NOT fire on the data attributes that carry the same words.
    expect(() =>
      assertPlain('<li data-price-state="dark" data-placeholder="register-hole">Alcaraz 62%</li>', "canary")
    ).not.toThrow();
  });
});
