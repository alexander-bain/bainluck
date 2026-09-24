/**
 * #7163 — a person's surname keeps its particles.
 *
 * The defect as a reader met it on `/events/15314434` (390px, production,
 * 2026-09-19): the hero labelled Alex de Minaur **"Minaur"**, which is nobody,
 * while the settled banner on the SAME CARD six lines above read "Settled ·
 * **de Minaur** wins". One card, two spellings of one player, and the correct
 * one already on screen.
 *
 * THE GATE IS THE DESIGN, AND MOST OF THIS FILE DEFENDS IT. The issue proposed
 * an ungated rule — "a trailing token preceded by a lowercase particle belongs
 * to the same name". Measured over every distinct multi-word `events` team
 * name, both sides, whole population (2026-09-19), that rule is correct on the
 * 80 person names and WRONG on a larger set of clubs whose output is right
 * today: "Sport Lisboa e Benfica" would become "e Benfica", "Defensa y
 * Justicia" "y Justicia", "Tigres de la UANL" "la UANL". So the club fixtures
 * below are not decoration — they are the reason the rule is gated on
 * `namesAPerson`, and each of them is a real production name.
 *
 * Three kinds of control, per the house pattern:
 *   - the PREMISE control proves the shipped rule really does emit "Minaur",
 *     so a green run cannot mean "the fixture had nothing to find";
 *   - the SCOPE controls pin what a blunter rule would eat (clubs, unknown
 *     sports, lowercase tokens that are not particles, doubles pairs);
 *   - the WIRING control fails if the event hero stops passing its sport,
 *     which is the one mutant a pure-function battery structurally cannot see
 *     — and it is not hypothetical here: the first draft of this ship passed
 *     `event.sport_key`, a field the payload does not carry.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { teamShortName, teamShortNames } from "@/lib/teamShortName";

/** A person sport, exactly as the specimen's payload spells it. */
const TENNIS = "tennis_other";
const MMA = "mma_mixed_martial_arts";
/** Club sports, as production spells them. */
/**
 * #5634 — a soccer key now has its own club rule (a club of up to three words
 * keeps its whole name), so it can no longer stand in for "a club sport the
 * particle walk must not touch". The gate controls below use this key; the
 * soccer outputs for the same names are pinned in
 * `teamShortNameSoccerWholeClub5634.test.ts`.
 */
const OTHER_CLUB = "aussierules_afl";
const BASEBALL = "baseball_mlb";

describe("#7163 — the premise: the shipped rule really does truncate", () => {
  /**
   * Without a sport, nothing changes — which is also what makes every other
   * caller in the app safe. If this test ever goes green by returning
   * "de Minaur", the gate has stopped being a gate and the club controls below
   * are no longer proving anything.
   */
  it("the last-word rule, unchanged, still names nobody", () => {
    expect(teamShortName("de Minaur")).toBe("Minaur");
    expect(teamShortName("Junior dos Santos")).toBe("Santos");
    expect(teamShortName("Van de Zandschulp")).toBe("Zandschulp");
  });
});

describe("#7163 — a person's surname keeps its particles", () => {
  it("the specimen", () => {
    expect(teamShortName("de Minaur", null, TENNIS)).toBe("de Minaur");
  });

  /**
   * Production names, from the sweep. The stacked ones are why the walk is a
   * loop: stopping after one particle hands back "de Zandschulp", which is the
   * same defect one token along.
   */
  it.each([
    ["Alex de Minaur", "de Minaur"],
    ["Van de Zandschulp", "Van de Zandschulp"],
    ["von der Schulenburg", "von der Schulenburg"],
    ["Meyer auf der Heide", "auf der Heide"],
    ["Santiago De la Fuente", "De la Fuente"],
    ["Huertas del Pino", "del Pino"],
    ["Kathinka von Deichmann", "von Deichmann"],
    ["Benita van Rooij", "van Rooij"],
    ["Connor Henry van Schalkwyk", "van Schalkwyk"],
    ["van Zijl", "van Zijl"],
    ["le Roux", "le Roux"],
    ["Daniel Dutra da Silva", "da Silva"],
  ])("tennis: %s -> %s", (name, expected) => {
    expect(teamShortName(name, null, TENNIS)).toBe(expected);
  });

  it.each([
    ["Junior dos Santos", "dos Santos"],
    ["Edson dos Anjos", "dos Anjos"],
    ["Sabrinna de Sousa", "de Sousa"],
    ["Claudeci Brito de Sousa", "de Sousa"],
    ["Shannon van Tonder", "van Tonder"],
  ])("mma: %s -> %s", (name, expected) => {
    expect(teamShortName(name, null, MMA)).toBe(expected);
  });
});

describe("#7163 — SCOPE: the gate, which is what keeps the clubs right", () => {
  /**
   * Every one of these is a real production name whose CURRENT output is
   * correct and whose ungated output would be a fragment. This is the test
   * that fails if someone later removes `namesAPerson` from the condition.
   */
  it.each([
    ["Sport Lisboa e Benfica", "Benfica"],
    ["Defensa y Justicia", "Justicia"],
    ["Tigres de la UANL", "UANL"],
    ["Heart of Midlothian", "Midlothian"],
    ["Wingate and Finchley", "Finchley"],
    ["Vasco da Gama", "Gama"],
    ["2 de Mayo", "Mayo"],
    ["Aldosivi Mar del Plata", "Plata"],
    ["Churriana de la Vega", "Vega"],
    ["Bourg en Bresse", "Bresse"],
    ["FC United of Manchester", "Manchester"],
  ])("a club is untouched: %s stays %s", (name, expected) => {
    expect(teamShortName(name, null, OTHER_CLUB)).toBe(expected);
    expect(teamShortName(name, null, BASEBALL)).toBe(expected);
    // And identical to the rule with no sport at all.
    expect(teamShortName(name, null, OTHER_CLUB)).toBe(teamShortName(name));
  });

  it("a caller that does not know its sport keeps today's output", () => {
    for (const sport of [undefined, null, "", "   ", OTHER_CLUB]) {
      expect(teamShortName("de Minaur", null, sport)).toBe("Minaur");
    }
  });

  /**
   * A lowercase penultimate token is NOT the test — being a particle is. These
   * are production names whose second-to-last token is lowercase and means
   * nothing of the sort.
   */
  it.each([
    ["nour sahnoun", "sahnoun"],
    ["sofia omati albieri", "albieri"],
    ["tahiri alaoui", "alaoui"],
  ])("a lowercase non-particle is not a particle: %s -> %s", (name, expected) => {
    expect(teamShortName(name, null, TENNIS)).toBe(expected);
  });

  it("a doubles pair is still returned whole (#3110 is not reopened)", () => {
    const pair = "Jose Escurra Isnardi / Antonio Vergara del Puerto";
    expect(teamShortName(pair, null, TENNIS)).toBe(pair);
    expect(teamShortName("Aguilar Cardozo / De la fuente", null, TENNIS)).toBe(
      "Aguilar Cardozo / De la fuente",
    );
  });

  it("a club-type trailing word still wins over the particle rule", () => {
    // The trailing token decides first: this returns the full name either way,
    // and must not become "de Vitoria FC" by a different route.
    expect(teamShortName("Sporting de Vitoria FC", null, TENNIS)).toBe(
      "Sporting de Vitoria FC",
    );
  });

  it("a name with no particle is unchanged in a person sport", () => {
    expect(teamShortName("Kasnikowski", null, TENNIS)).toBe("Kasnikowski");
    expect(teamShortName("Carlos Alcaraz", null, TENNIS)).toBe("Alcaraz");
    expect(teamShortName("Davidovich Fokina", null, TENNIS)).toBe("Fokina");
  });
});

describe("#7163 — the pair helper threads the sport", () => {
  it("the specimen's card, both sides", () => {
    expect(
      teamShortNames({ name: "de Minaur" }, { name: "Kasnikowski" }, TENNIS),
    ).toEqual({ home: "de Minaur", away: "Kasnikowski" });
  });

  it("without the sport the pair is exactly what it is today", () => {
    expect(teamShortNames({ name: "de Minaur" }, { name: "Kasnikowski" })).toEqual({
      home: "Minaur",
      away: "Kasnikowski",
    });
  });

  /**
   * The abbreviation rescue needs BOTH sides to carry one, and a particled
   * surname that IS the whole name reads as "the rule could not shorten this".
   * Pinned because it is the one interaction the change could have moved: with
   * only one abbreviation present, nothing is rescued and the name stands.
   */
  it("one-sided abbreviations do not rescue a particled surname away", () => {
    expect(
      teamShortNames(
        { name: "de Minaur", abbreviation: "DEM" },
        { name: "Kasnikowski" },
        TENNIS,
      ),
    ).toEqual({ home: "de Minaur", away: "Kasnikowski" });
  });

  it("two players who shorten alike still fall back to their full names", () => {
    expect(
      teamShortNames({ name: "Ana de Sousa" }, { name: "Rui de Sousa" }, TENNIS),
    ).toEqual({ home: "Ana de Sousa", away: "Rui de Sousa" });
  });
});

/**
 * THE WIRING CONTROL.
 *
 * Everything above passes on a tree where the event hero never passes its
 * sport, and the hero is the whole ship — so this reads the page's own source
 * and fails if the third argument goes away or names a field the payload does
 * not carry. `sport_key` is spelled out as a refusal because that is the
 * mistake this ship actually made: `Event` has `sport`, and the specimen's
 * payload serves `sport: "tennis_other"` with no `sport_key` at all.
 */
describe("#7163 — WIRING: the event hero passes its sport", () => {
  const PAGE = join(__dirname, "../app/events/[id]/page.tsx");
  const source = readFileSync(PAGE, "utf8");

  /** The `teamShortNames(...)` call that builds the hero, by paren matching. */
  function heroCall(): string {
    const marker = "const heroShortNames = teamShortNames(";
    const start = source.indexOf(marker);
    if (start === -1) return "";
    let depth = 0;
    for (let i = source.indexOf("(", start); i < source.length; i += 1) {
      if (source[i] === "(") depth += 1;
      if (source[i] === ")") {
        depth -= 1;
        if (depth === 0) return source.slice(start, i + 1);
      }
    }
    return "";
  }

  it("the call was found at all (this file's own reachability)", () => {
    // A parser that matches nothing makes every assertion below vacuous.
    expect(heroCall()).toContain("teamShortNames(");
    expect(heroCall().length).toBeGreaterThan(80);
  });

  it("it passes event.sport, and not a field the payload does not carry", () => {
    const call = heroCall();
    expect(call).toMatch(/\bevent\.sport\b/);
    expect(call).not.toMatch(/\bevent\.sport_key\b/);
  });
});
