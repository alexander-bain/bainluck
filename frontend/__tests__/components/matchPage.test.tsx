/**
 * THE MATCH PAGE (UX-P149) — asserted AT THE RENDER, over real payloads.
 *
 * Alex asked, of the match props lane1 measured in Q426: *"Will those flow into
 * the event page for each match, and will they look good?"* The answer has to
 * be a rendered yes, so every guard here goes through `renderToStaticMarkup`
 * of the shipped components over payloads captured from production
 * (`docs/mocks/us-open/match-{upcoming,decided}-2026-08-28.json`, built by
 * `backend/scripts/capture_match_payload.py` through the same `build_*`
 * functions the route calls).
 *
 * `reference_plant_must_hit_the_render`: a pure-library guard stays green the
 * day the component stops printing the feature. Both specimens are real —
 * eight questions each, real Polymarket numbers, one match ESPN has decided
 * and one it has not.
 *
 * ═══ THE THREE CLASSES THIS FILE EXISTS FOR ═══
 *
 * 1. **A number under the wrong player's name.** The worst defect this page
 *    can ship, and the only inferred step on it. The backend suite proves the
 *    attribution rule against the register's own 28 pins; this proves the
 *    names that reach the screen are the two players of THIS match.
 * 2. **`Yes` / `No` / `Over` / `Under` reaching a reader.** The words the
 *    source stores are not words anyone can act on.
 * 3. **A live-looking number on a finished match.** A prop market does not
 *    reliably settle — the decided specimen is the one where the match-winner
 *    market reads 0.05% while "Who wins set 1" still reads the pre-match 62.5%.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MatchHero from "@/components/tournament/MatchHero";
import MatchProps from "@/components/tournament/MatchProps";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import {
  answerPercents,
  heroOrder,
  matchSubheading,
  propFreshnessLabel,
  propIsPresentedAsLive,
  visibleProps,
  type MatchDetailPayload,
} from "@/lib/matchDetail";
import { buildMatchList } from "@/lib/matchList";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import type { SlateMatch } from "@/lib/slate";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");
const NOW = new Date("2026-08-28T12:00:00Z");

function load(name: string): MatchDetailPayload {
  return JSON.parse(
    fs.readFileSync(path.join(MOCKS, name), "utf8")
  ) as MatchDetailPayload;
}

const UPCOMING = load("match-upcoming-2026-08-28.json");
const DECIDED = load("match-decided-2026-08-28.json");

function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function page(payload: MatchDetailPayload): string {
  return renderToStaticMarkup(
    <>
      <MatchHero
        match={payload.match}
        result={payload.result}
        decided={payload.decided}
        now={NOW}
      />
      <MatchProps payload={payload} />
    </>
  );
}

describe("the captured payloads are the specimens these guards need", () => {
  it("carry real questions, one decided match and one not", () => {
    // A rig on a stale or empty file proves nothing — that is the whole lesson
    // of `capture_tournament_payload.py`.
    //
    // THESE TWO FILES ARE FROZEN CAPTURES AND MUST NOT BE RE-RUN CASUALLY.
    // The first `upcoming` specimen stopped being upcoming DURING this queue:
    // ESPN published the Wendelken result twenty minutes after the capture and
    // a re-run turned `decided` from false to true, reddening four guards. A
    // committed mock is a snapshot of a state we want to keep testing, not a
    // mirror of today — re-capture only when the SHAPE changes, and re-check
    // `decided` on both when you do.
    expect(UPCOMING.decided).toBe(false);
    expect(DECIDED.decided).toBe(true);
    expect(UPCOMING.props.length).toBeGreaterThanOrEqual(6);
    expect(DECIDED.props.length).toBeGreaterThanOrEqual(6);
    expect(UPCOMING.props_dropped).toEqual({});
    expect(UPCOMING.match.coherent).toBe(true);
  });

  it("the decided specimen really does carry the stale-prop trap", () => {
    // The whole reason rule 1 exists: the match is over and a prop still
    // reads its pre-match number. If this stops being true the specimen has
    // stopped testing anything.
    const winner = DECIDED.match.sides.find(
      (side) => side.entity_key === DECIDED.result?.winner_entity_key
    );
    expect(winner?.probability).toBeGreaterThan(0.9);
    const loser = DECIDED.match.sides.find((side) => side !== winner)!;
    const setOne = DECIDED.props.find((prop) => prop.question === "Who wins set 1")!;
    const loserAnswer = setOne.answers.find(
      (answer) => answer.entity_key === loser.entity_key
    )!;
    expect(loserAnswer.probability).toBeGreaterThan(0.5);
  });
});

describe("the questions render, grouped under the match", () => {
  it("every card is on the page with its question and its numbers", () => {
    const html = page(UPCOMING);
    for (const prop of visibleProps(UPCOMING)) {
      expect(html).toContain(prop.question);
      for (const answer of prop.answers) expect(html).toContain(answer.label);
    }
    const cards = html.match(/data-testid="match-prop"/g) ?? [];
    expect(cards.length).toBe(visibleProps(UPCOMING).length);
  });

  it("the hero prints the match-winner market above them", () => {
    const html = page(UPCOMING);
    expect(html).toContain('data-testid="match-hero"');
    for (const side of UPCOMING.match.sides) {
      expect(html).toContain(side.display_name);
    }
    expect(html.indexOf('data-testid="match-hero"')).toBeLessThan(
      html.indexOf('data-testid="match-props"')
    );
  });

  it("a ladder is ONE card, not one per strike", () => {
    // Three `Match O/U` markets are one question at three heights. Three cards
    // is the ladder/bucket shape the Discover audit holds at zero.
    const ladders = UPCOMING.props.filter((prop) => prop.kind === "ladder");
    expect(ladders.length).toBeGreaterThan(0);
    for (const ladder of ladders) {
      expect(ladder.market_ids.length).toBeGreaterThan(1);
      expect(ladder.answers.length).toBe(ladder.market_ids.length);
    }
    // Each rung is a row inside its one card, so the question is READ once.
    // Counted over visible text rather than markup: the card's `data-key` is
    // `ladder:<question>` and a raw-HTML count would see it twice.
    const text = visibleText(page(UPCOMING));
    for (const ladder of ladders) {
      const hits = text.split(ladder.question).length - 1;
      expect(hits).toBe(1);
    }
  });

  it("a ladder's rungs descend — the curve IS the card", () => {
    for (const ladder of UPCOMING.props.filter((p) => p.kind === "ladder")) {
      const values = ladder.answers
        .map((answer) => answer.probability)
        .filter((value): value is number => value !== null);
      expect(values).toEqual([...values].sort((a, b) => b - a));
    }
  });
});

describe("the words a reader sees", () => {
  const SOURCE_WORDS = [
    /\bYes\b/,
    /\bNo\b/,
    /\bOver\b/,
    /\bUnder\b/,
    /\bO\/U\b/,
    /\bhandicap\b/i,
    /\bspread\b/i,
  ];

  it.each([
    ["upcoming", UPCOMING],
    ["decided", DECIDED],
  ])("%s: never prints the source's own words", (_name, payload) => {
    const text = visibleText(page(payload as MatchDetailPayload));
    for (const pattern of SOURCE_WORDS) {
      expect(text).not.toMatch(pattern);
    }
  });

  it("the guard is not vacuously green", () => {
    // If the regexes were wrong this file would pass forever. The words it
    // hunts are the ones the SERVER holds, so they must be rejected on sight.
    const raw = "<p>Yes 53% / No 47% — Match O/U 22.5 Over</p>";
    const text = visibleText(raw);
    expect(SOURCE_WORDS.some((pattern) => pattern.test(text))).toBe(true);
  });

  it("every answer label names a player or a plain count", () => {
    for (const payload of [UPCOMING, DECIDED]) {
      const names = payload.match.sides.map((side) => side.display_name);
      for (const prop of payload.props) {
        for (const answer of prop.answers) {
          const namesAPlayer = names.some((name) => answer.label.includes(name));
          const countsSomething = /^(More than|\d+ )/.test(answer.label);
          const isComplement = answer.label === "Anything else";
          expect(namesAPlayer || countsSomething || isComplement).toBe(true);
        }
      }
    }
  });

  it("a duel card names only THIS match's two players", () => {
    for (const payload of [UPCOMING, DECIDED]) {
      const keys = payload.match.sides.map((side) => side.entity_key);
      for (const prop of payload.props) {
        for (const answer of prop.answers) {
          if (answer.entity_key === null) continue;
          expect(keys).toContain(answer.entity_key);
        }
      }
    }
  });
});

describe("settled means settled", () => {
  it("a decided match prints the OPENING number, not the current one", () => {
    const setOne = DECIDED.props.find((prop) => prop.question === "Who wins set 1")!;
    const shown = answerPercents(setOne, true);
    const current = answerPercents(setOne, false);
    const opening = setOne.answers.map((answer) =>
      answer.opening_probability === null
        ? null
        : Math.round(answer.opening_probability * 100)
    );
    expect(shown[0]).toBe(opening[0]);
    // …and it is genuinely a different number, or this proves nothing.
    expect(shown).not.toEqual(current);
  });

  it("no card on a decided match is presented as live", () => {
    for (const prop of DECIDED.props) {
      expect(propIsPresentedAsLive(prop, true)).toBe(false);
      expect(propFreshnessLabel(prop, true)).toBeNull();
    }
  });

  it("the section renames itself rather than pretending to be open", () => {
    const decided = visibleText(page(DECIDED));
    const upcoming = visibleText(page(UPCOMING));
    expect(decided).toContain("What the market thought beforehand");
    expect(decided).not.toContain("More on this match");
    expect(upcoming).toContain("More on this match");
  });

  it("the winner leads the hero, whatever the market thought", () => {
    const ordered = heroOrder(DECIDED.match, DECIDED.result)!;
    expect(ordered[0].entity_key).toBe(DECIDED.result?.winner_entity_key);
    expect(page(DECIDED)).toContain('data-testid="match-hero-won"');
  });

  it("the result carries its score, through the hub's own wording", () => {
    const html = page(DECIDED);
    expect(html).toContain('data-testid="match-hero-result"');
    expect(html).toContain(DECIDED.result?.score as string);
  });
});

describe("honesty", () => {
  it("a pair never sums to 101 — rounded once, together", () => {
    // UX-P147, Alex's item 4, applied to every two-answer card on the page.
    for (const payload of [UPCOMING, DECIDED]) {
      for (const prop of payload.props) {
        if (prop.kind === "ladder" || prop.answers.length !== 2) continue;
        const [a, b] = answerPercents(prop, payload.decided);
        if (a === null || b === null) continue;
        expect(a + b).toBe(100);
      }
    }
  });

  it("a card says WHY it is muted", () => {
    const muted = UPCOMING.props.filter(
      (prop) => !propIsPresentedAsLive(prop, false)
    );
    for (const prop of muted) {
      expect(propFreshnessLabel(prop, false)).not.toBe("");
    }
  });

  it("an incoherent card shows no number at all", () => {
    const broken: MatchDetailPayload = {
      ...UPCOMING,
      props: [
        {
          ...UPCOMING.props[0],
          coherent: false,
          answers: UPCOMING.props[0].answers.map((answer) => ({
            ...answer,
            probability: null,
            opening_probability: null,
          })),
        },
      ],
    };
    // With nothing printable it is not rendered as a question at all, and the
    // drop is counted rather than silent.
    expect(visibleProps(broken)).toEqual([]);
    const html = page(broken);
    expect(html).toContain('data-testid="match-props-empty"');
    expect(html).toContain('data-hidden="1"');
  });

  it("an empty section still appears, and says why", () => {
    const bare: MatchDetailPayload = { ...UPCOMING, props: [], props_count: 0 };
    const text = visibleText(page(bare));
    expect(text).toContain("Nothing else on this match yet");
  });

  it("the provenance line says where these numbers came from", () => {
    expect(visibleText(page(UPCOMING))).toContain("Same market as the probability above");
    expect(visibleText(page(DECIDED))).toContain("before the match");
  });
});

describe("the route in", () => {
  it("a match list row links to its own page, keyed on the register", () => {
    const slate: SlateMatch[] = [UPCOMING.match];
    const entries = buildMatchList({
      slate,
      rounds: [],
      prematch: {},
      titleChances: {},
    });
    expect(entries[0].matchupKey).toBe(UPCOMING.matchup_key);

    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={entries}
        slug="us-open"
        initialExpanded
        initialOpenMatchId={entries[0].id}
      />
    );
    expect(html).toContain('data-testid="match-page-link"');
    expect(html).toContain(
      `/tournaments/us-open/matches/${encodeURIComponent(UPCOMING.matchup_key)}`
    );
  });

  it("no slug, no link — the affordance never points nowhere", () => {
    const entries = buildMatchList({
      slate: [UPCOMING.match],
      rounds: [],
      prematch: {},
      titleChances: {},
    });
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={entries}
        initialExpanded
        initialOpenMatchId={entries[0].id}
      />
    );
    expect(html).not.toContain('data-testid="match-page-link"');
  });
});

describe("the page's own metadata line", () => {
  it("names the draw, the round and when", () => {
    const line = matchSubheading(UPCOMING.match, NOW);
    expect(line).toContain(UPCOMING.match.draw_label);
    // The register writes `qualifying`; the reader sees `Qualifying`. Pinned
    // as the LABEL, not the raw field — printing the raw one is what made the
    // line read like a field somebody forgot to format.
    expect(line).toContain("Qualifying");
    expect(line).not.toContain("· qualifying");
    expect(line.length).toBeGreaterThan(10);
  });

  it("does not branch on the real clock", () => {
    // `reference` gotcha: a test anchor that reads `new Date()` passes today
    // and fails on some future Tuesday. Two different `now`s, same match.
    const a = matchSubheading(UPCOMING.match, new Date("2026-08-28T12:00:00Z"));
    const b = matchSubheading(UPCOMING.match, new Date("2027-01-01T12:00:00Z"));
    expect(a).not.toBe(b);
    expect(b).toContain("2026");
  });
});

describe("the decided hero is the prior, not the result read back", () => {
  it("prints the OPENING pair, never the settled 100 / 0", () => {
    const html = renderToStaticMarkup(
      <MatchHero
        match={DECIDED.match}
        result={DECIDED.result}
        decided
        now={NOW}
      />
    );
    const text = visibleText(html);
    // The settled market on this specimen reads 99.9% / 0.05%.
    expect(text).not.toContain("100%");
    expect(text).not.toContain("0%");
    // The opening pair does reach the screen, rounded once so it sums to 100.
    const opening = DECIDED.match.sides.map((side) => side.opening_probability);
    expect(opening.every((value) => typeof value === "number")).toBe(true);
    const pcts = opening.map((value) => Math.round((value as number) * 100));
    expect(pcts[0] + pcts[1]).toBe(100);
    for (const pct of pcts) expect(text).toContain(`${pct}%`);
  });

  it("the winner still leads, and is still marked as the winner", () => {
    const html = renderToStaticMarkup(
      <MatchHero match={DECIDED.match} result={DECIDED.result} decided now={NOW} />
    );
    expect(html).toContain('data-testid="match-hero-won"');
    const winnerAt = html.indexOf(
      `data-entity="${DECIDED.result?.winner_entity_key}"`
    );
    const otherAt = html.indexOf(
      `data-entity="${DECIDED.match.sides.find(
        (side) => side.entity_key !== DECIDED.result?.winner_entity_key
      )?.entity_key}"`
    );
    expect(winnerAt).toBeGreaterThan(-1);
    expect(winnerAt).toBeLessThan(otherAt);
  });

  it("with no prior it says so, rather than printing two em-dashes", () => {
    const stripped = {
      ...DECIDED.match,
      sides: DECIDED.match.sides.map((side) => ({
        ...side,
        opening_probability: null,
      })),
    };
    const html = renderToStaticMarkup(
      <MatchHero match={stripped} result={DECIDED.result} decided now={NOW} />
    );
    expect(html).toContain('data-testid="match-hero-no-prior"');
    expect(visibleText(html)).toContain("no number from before this match");
  });

  it("an UPCOMING hero is unchanged — it still prints the current pair", () => {
    const html = renderToStaticMarkup(
      <MatchHero match={UPCOMING.match} result={null} decided={false} now={NOW} />
    );
    const text = visibleText(html);
    // Through `renderedDuelPercents`, not `Math.round` per side — 86.5 and
    // 13.5 round independently to 87 and 14, which is the 101 UX-P147's item 4
    // deleted. The first draft of this assertion made exactly that mistake and
    // the component was right.
    const current = renderedDuelPercents(
      UPCOMING.match.sides[0].probability,
      UPCOMING.match.sides[1].probability
    );
    expect(current[0]! + current[1]!).toBe(100);
    for (const pct of current) expect(text).toContain(`${pct}%`);
  });
});
