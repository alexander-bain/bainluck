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
 * ═══ UX-P146: THE LINE ON "PRICE" MOVED, AND IT MOVED ALL THE WAY ═══
 *
 * UX-P145 drew a line down the middle of the word: *priced* as a verb was
 * jargon and banned, *price* as the noun a market publishes was plain English
 * and stayed — "Prices paused", "the last prices we saw", "cells carry a market
 * price". The reasoning was that three surfaces already shared that vocabulary
 * and splitting them would be worse.
 *
 * Alex overruled it on 2026-08-27, as a PERMANENT, PRODUCT-WIDE ruling:
 *
 *   > "price" as a noun is banned in user-facing copy — the word is
 *   > PROBABILITY.
 *
 * That is the right call and the half-line was the wrong one. A price is what
 * you pay; a probability is what we sell. This product's entire premise is that
 * a reader should never have to think in the trading layer — "60% vs 40%"
 * instead of "-150 / +130" — and a page that then tells them their number is a
 * *price* hands the trading layer straight back. Consistency across three
 * surfaces is worth something; it is not worth being consistently in the wrong
 * vocabulary.
 *
 * SCOPE OF THIS FILE. The ruling is product-wide and applies to all future
 * copy. What is SWEPT here is the tournament surfaces, which is what the queue
 * covered. `/calibration`, the Discover cards and the event pages still say
 * *price* in places; they are named in the report as owed, not silently
 * counted as done. This guard fails loudly for anything under
 * `components/tournament/` so the tournament half cannot drift back.
 *
 * `BANNED` therefore matches the whole stem — noun, verb, participle and
 * gerund — instead of the eleven hand-written variants UX-P145 needed to catch
 * the verb without catching the noun.
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
import { ALL_COPY_BANS, findBannedCopy } from "@/lib/copyBans";
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
 * UX-P150 moved this list out to `lib/copyBans.ts`. It did not change what is
 * banned here; it changed how many bodies of text the SAME list gets applied
 * to. This file sweeps rendered components. `shippedCopyBans.test.ts` sweeps
 * the built bundle and, on demand, the chunks production actually serves —
 * which is the layer that was missing when Alex found three already-"fixed"
 * sentences live on 2026-08-28. Two consumers, one list, no drift.
 *
 * `ALL_COPY_BANS` therefore now also carries ruling 141 (venue names) and
 * ruling 142 (future-tense promises) on top of the UX-P145 jargon list and
 * ruling 138's `price` stem.
 */
const BANNED = ALL_COPY_BANS;

function assertPlain(html: string, where: string) {
  const text = visibleText(html);
  const [hit] = findBannedCopy(text, BANNED);
  if (hit) {
    throw new Error(
      `${where}: internal jargon in user-visible copy — ${hit.ban.why}.\n` +
        `  matched: "${hit.matched}"\n` +
        `  context: …${hit.context}…`
    );
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
      // Pinned verbatim on purpose: a paraphrase that drifts back toward the
      // pipeline is the regression, and only an equality catches a drift that
      // stays inside the banned-word list.
      //
      // UX-P150 dropped the second half. UX-P145 added "New questions are
      // coming — check back soon." so the section would not read as a dead
      // feature; ruling 142 (Alex, 2026-08-28) rules that fix out — we do not
      // control when a market lists, so naming a time was a promise we could
      // not keep. What remains is the whole of the FACT, which is what the
      // count was always for.
      const curated = curatedProps(darkMarkets(), "mens-singles");
      expect(curatedPropsEmptyReason(curated)).toBe(
        "We have not seen a new number on 3 questions in a while, so they are hidden for now."
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
        "We have not seen a new number on 1 question in a while, so it is hidden for now."
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

  /* ─────────── UX-P146: THE WORD IS PROBABILITY, AND THE HONESTY SURVIVES ─────────── */

  describe('Alex\'s product-wide ruling: "price" as a noun is banned', () => {
    /** The board in the state that used to say "Prices paused". */
    const darkBoard = () => ({
      ...payload.boards[0],
      price_state: "dark" as const,
      age_hours: 300,
      rows: payload.boards[0].rows.map((row) => ({
        ...row,
        probability_is_live: false,
        price_state: "dark" as const,
        age_hours: 300,
      })),
    });

    it("the stale-board admission no longer says it in trading words", () => {
      // UX-P145 pinned "Prices paused" and "the last prices we saw" as
      // deliberately-kept language. Alex overruled it. Pinned in the negative
      // AND in the positive, because the failure mode of a copy ruling is a
      // rewrite that removes the banned word and the meaning with it.
      const html = renderToStaticMarkup(<TournamentBoard board={darkBoard()} />);
      expect(html).not.toContain("Prices paused");
      assertPlain(html, "TournamentBoard (dark)");
    });

    it("…and still ADMITS the staleness, which was the point of that copy", () => {
      // The honesty property UX-P145 was protecting is real and independent of
      // the vocabulary. A reader looking at a three-hundred-hour-old board must
      // be told that is what they are looking at.
      const text = visibleText(renderToStaticMarkup(<TournamentBoard board={darkBoard()} />));
      expect(text).toContain("Updates paused");
      expect(text).toContain(
        "These are the last probabilities we saw, not live ones."
      );
    });

    it("the data contract is untouched — the words moved, the attributes did not", () => {
      // `price_state` is an enum on a data attribute and CERT-411 and the
      // sentinels read it. Our names belong there; the ruling is about copy.
      const html = renderToStaticMarkup(<TournamentBoard board={darkBoard()} />);
      expect(html).toContain('data-price-state="dark"');
    });

    it("no tournament component ships the word in a user-visible string", () => {
      // The render sweep above covers the states these fixtures reach. This is
      // the backstop for the ones they do not: a grep of the SOURCE for the
      // stem outside comments, attribute names and identifiers.
      //
      // Deliberately crude and deliberately narrow — it reads JSX text nodes
      // and nothing else — because a clever version of this test is one that
      // gets disabled the first time it is wrong.
      const dir = path.join(__dirname, "..", "..", "components", "tournament");
      const offenders: string[] = [];
      for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".tsx"))) {
        const source = fs.readFileSync(path.join(dir, file), "utf8");
        // Strip block comments, line comments and every attribute value, then
        // look at what is left between tags.
        const stripped = source
          .replace(/\/\*[\s\S]*?\*\//g, " ")
          .replace(/^\s*\/\/.*$/gm, " ")
          .replace(/\w+(-\w+)*=(\{[^}]*\}|"[^"]*"|'[^']*')/g, " ");
        for (const [, text] of stripped.matchAll(/>([^<>{}]{4,})</g)) {
          if (/\b(un)?pric(e|es|ed|ing)\b/i.test(text)) {
            offenders.push(`${file}: ${text.trim().slice(0, 90)}`);
          }
        }
      }
      expect(offenders).toEqual([]);
    });
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
    // UX-P146: the NOUN, which UX-P145 deliberately allowed and Alex overruled.
    expect(() => assertPlain("<p>Prices paused</p>", "canary")).toThrow(/price/i);
    expect(() => assertPlain("<p>the last prices we saw</p>", "canary")).toThrow(/price/i);
    expect(() => assertPlain("<p>cells carry a market price</p>", "canary")).toThrow(/price/i);
    expect(() => assertPlain("<p>12 players have no price yet</p>", "canary")).toThrow(/price/i);
    expect(() => assertPlain("<p>12 more registered players</p>", "canary")).toThrow(/registered/i);
    expect(() => assertPlain("<p>Probabilities blended across markets</p>", "canary")).toThrow(
      /blend/i
    );
    expect(() => assertPlain("<p>this reading is stale</p>", "canary")).toThrow(/stale/i);

    // UX-P150, ruling 141: a venue name in a sentence aimed at a reader.
    expect(() =>
      assertPlain("<p>we asked Kalshi and Polymarket and neither runs that market</p>", "canary")
    ).toThrow(/Kalshi/);
    expect(() => assertPlain("<p>Polymarket 20 days ago</p>", "canary")).toThrow(/Polymarket/);

    // UX-P150, ruling 142: a promise about what the section WILL be.
    expect(() => assertPlain("<p>New questions are coming — check back soon.</p>", "canary")).toThrow(
      /check back/i
    );
    expect(() => assertPlain("<p>Matches appear here as they are scheduled.</p>", "canary")).toThrow(
      /appear here/i
    );
    expect(() =>
      assertPlain("<p>Once the main draw starts, more of them are listed</p>", "canary")
    ).toThrow(/once the/i);
    expect(() => assertPlain("<p>the number comes later</p>", "canary")).toThrow(/comes later/i);

    // And it must NOT fire on the data attributes that carry the same words —
    // including the venue ids, which are enum values the sentinels read.
    expect(() =>
      assertPlain('<li data-price-state="dark" data-placeholder="register-hole">Alcaraz 62%</li>', "canary")
    ).not.toThrow();
    expect(() =>
      assertPlain('<li data-source="kalshi" data-group="polymarket:88">Alcaraz 62%</li>', "canary")
    ).not.toThrow();
    // …nor on a market's OWN question, which is content and not our voice.
    expect(() => assertPlain("<h3>Will Sinner actually play?</h3>", "canary")).not.toThrow();
  });
});
