// #4309: a reader on a phone must be able to tell which golfer each row of the
// Tournament Progression table is.
//
// The name column is capped at 104px on a phone. That cap is #4261's fix and it
// is load-bearing — it is the only reason the Make Cut bars render whole — so
// the answer here can never be "widen the column". At 14px Inter the cap fits
// roughly twelve characters and `truncate` eats the END of the name, which is
// the half that identifies a golfer.
//
// Measured on production (2026-09-09, Amgen Irish Open, 390px, leaf
// `scrollWidth > clientWidth`): THIRTEEN name cells truncate, not the five the
// first screen showed. The specimen is two players three rows apart:
//
//     Rasmus Hojgaard   116.00px  ->  rendered "Rasmus Hojg…"
//     Nicolai Hojgaard  108.55px  ->  rendered "Nicolai Hojga…"
//
// Both stubs are unreadable and neither is the other's. Abbreviating the given
// name spends the 104px on the surname instead — measured in the real cell at
// the real font, `R. Hojgaard` is 77.22px and `N. Hojgaard` is 78.39px, both
// comfortably inside the cap and plainly different.
//
// WHAT THIS SUITE ASSERTS, AND WHAT IT DELIBERATELY DOES NOT.
//
// It asserts the TRANSFORM and the rendered DOM, never a pixel width: jsdom has
// no font metrics, so any "it fits" claim made here would be a number this file
// invented. The pixel claim is the production geometry probe's job
// (`.lat283-fit-probe.mjs`, which clones the live cell and measures candidate
// strings in the real font) and it is quoted above.
//
// It identifies the two players BY CONSTRUCTION — same surname, different given
// name — and asserts their rendered labels DIFFER. It never asserts that a
// label equals "R. Hojgaard". A guard that pins the literal passes just as
// happily when both rows render the same wrong string, which is the actual bug.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable, {
  progressionDisplayName,
} from "../../components/TournamentProgressionTable";
import type { ProgressionResponse } from "../../lib/types";

function table(sport: string, names: string[]): ProgressionResponse {
  return {
    sport,
    tournament_name: "Amgen Irish Open",
    stages: [
      { key: "make_cut", label: "Make Cut", order: 0, market_id: null, market_name: null, resolved: false },
      { key: "win", label: "Win", order: 1, market_id: null, market_name: null, resolved: false },
    ],
    participants: names.map((name, i) => ({
      name,
      team_id: null,
      logo_url: null,
      primary_color: null,
      conference: null,
      region: null,
      seed: null,
      record: null,
      probabilities: { make_cut: 0.8 - i * 0.05, win: 0.05 },
      changes_24h: {},
      status: {},
      sources_data: {},
    })),
  };
}

function html(sport: string, names: string[]): string {
  return renderToStaticMarkup(
    <TournamentProgressionTable data={table(sport, names)} pageType="golf" />,
  );
}

/**
 * The labels a PHONE reader actually sees, in render order.
 *
 * Scoped to the phone span specifically. Reading "the name cell's text" would
 * pick up the `sm:` copy and the `sr-only` copy too and quietly pass on a
 * change that never reached the phone.
 */
function phoneLabels(markup: string): string[] {
  return Array.from(
    markup.matchAll(/data-testid="progression-name-short"[^>]*>([^<]*)</g),
  ).map((m) => m[1]);
}

/**
 * The name CELL's text, phone span or not — the "is it there at all" read.
 *
 * Anchored on `<td`, because the header `<th>` carries the same `sticky left-8`
 * and a class-only match runs past `</th>` into the first body cell.
 */
function nameCellText(markup: string): string {
  const cell = markup.match(/<td[^>]*sticky left-8[^]*?<\/td>/);
  return cell ? cell[0].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() : "";
}

// The live specimen, by construction: identical surname, different given name.
const SHARED_SURNAME = "Hojgaard";
const TWINS = [`Rasmus ${SHARED_SURNAME}`, `Nicolai ${SHARED_SURNAME}`];

describe("#4309 — a phone reader can tell which golfer a row is", () => {
  it("renders two same-surname golfers as two DIFFERENT phone labels", () => {
    const labels = phoneLabels(html("golf", TWINS));

    // Positive control: the specimen reached the name cell at all. Without this
    // an empty match set satisfies every assertion below vacuously.
    expect(labels).toHaveLength(2);

    const [a, b] = labels;
    expect(a).not.toBe(b);
    // ...and neither collapsed to the bare shared surname, which would be two
    // identical rows wearing a different bug.
    expect(a).not.toBe(SHARED_SURNAME);
    expect(b).not.toBe(SHARED_SURNAME);
  });

  it("keeps the SURNAME whole in both phone labels — the surname is the identity", () => {
    const labels = phoneLabels(html("golf", TWINS));
    expect(labels).toHaveLength(2);
    for (const label of labels) {
      expect(label).toContain(SHARED_SURNAME);
      // The surname must not itself be shortened: it is the part worth the width.
      expect(label.endsWith(SHARED_SURNAME)).toBe(true);
    }
  });

  it("spends the width by SHORTENING the given name, not the surname", () => {
    for (const full of TWINS) {
      const short = progressionDisplayName(full, "golf");
      const [given, surname] = full.split(" ");
      expect(short.length).toBeLessThan(full.length);
      expect(short).toContain(surname);
      expect(short).not.toContain(given);
      // The given name survives as its initial, so the two rows stay separable.
      expect(short.startsWith(`${given[0]}. `)).toBe(true);
    }
  });

  it("still carries the FULL name for assistive tech and for sm: and up", () => {
    const markup = html("golf", TWINS);
    for (const full of TWINS) {
      // once in the `sm:` span, once in `sr-only` — a phone screen reader still
      // hears the whole name, which it does today via the untruncated text node.
      expect(markup.split(full).length - 1).toBeGreaterThanOrEqual(2);
    }
    expect(markup).toContain("sr-only");
  });

  // ---- the #4261 weld -----------------------------------------------------
  //
  // The tempting "fix" for this issue is to put the 240px cap back. That
  // re-opens #4261 (the name column grew to 206.5px inside a 302px scroller and
  // every Make Cut bar clipped at one shared pixel). Assert the cap here too, so
  // reverting it fails THIS suite as well as that one.
  it("does NOT widen the phone name cap — #4261's 104px must survive this fix", () => {
    const markup = html("golf", TWINS);
    expect(markup).toContain("max-w-[104px]");
    expect(markup).not.toContain("max-w-[240px]");
  });

  // ---- the abbreviation must not escape its domain ------------------------

  it("leaves TEAM names alone — 'Kansas City Chiefs' is not 'K. City Chiefs'", () => {
    const teams = ["Kansas City Chiefs", "San Francisco 49ers"];
    expect(phoneLabels(html("americanfootball_nfl", teams))).toHaveLength(0);
    for (const team of teams) {
      expect(progressionDisplayName(team, "americanfootball_nfl")).toBe(team);
      expect(nameCellText(html("americanfootball_nfl", [team]))).toContain(team);
    }
  });

  it("leaves MARKET OUTCOME rows alone on a person-field domain", () => {
    // Tennis IS a person-field domain, so the domain gate alone would abbreviate
    // these into gibberish ("O. 16.5 games"). The per-row gate is what stops it.
    for (const row of ["Over 16.5 games", "Under 63.5", "Golfer 1"]) {
      expect(progressionDisplayName(row, "tennis")).toBe(row);
      expect(progressionDisplayName(row, "golf")).toBe(row);
    }
  });

  it("leaves a single-word name alone — there is no given name to spend", () => {
    expect(progressionDisplayName("Alpha", "golf")).toBe("Alpha");
    expect(phoneLabels(html("golf", ["Alpha"]))).toHaveLength(0);
  });

  it("is idempotent — an already-abbreviated name does not gain a second dot", () => {
    expect(progressionDisplayName("R. Hojgaard", "golf")).toBe("R. Hojgaard");
  });

  it("keeps a compound surname whole rather than dropping half of it", () => {
    // The one live name too long to fit even abbreviated (151.77px measured).
    // It must still degrade to a readable, unique surname PREFIX — so the
    // abbreviation may not quietly drop "-Petersen" to make it fit.
    expect(progressionDisplayName("Rasmus Neergaard-Petersen", "golf")).toBe(
      "R. Neergaard-Petersen",
    );
    // A two-part surname keeps both parts.
    expect(progressionDisplayName("Jacob Skov Olesen", "golf")).toBe("J. Skov Olesen");
  });
});
