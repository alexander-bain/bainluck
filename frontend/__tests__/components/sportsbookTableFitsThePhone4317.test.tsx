/**
 * #4317 — THE SPORTSBOOK TABLE'S FOURTH COLUMN SURVIVES A 390px PHONE.
 *
 * ═══ WHAT A READER GOT ═══
 *
 * `/events/15307463` (Khachanov–Blockx, a US Open quarter-final), 390×844,
 * "Sportsbooks" disclosure open, read off production 2026-09-09:
 *
 *     scroll container   scrollWidth 382 vs clientWidth 334  →  48px over
 *     `Status` column    right edge 409.7 against a 390px viewport
 *     rows affected      11 of 11
 *
 * Not merely clipped — unreadable. The header rendered as `St` and every row
 * read `Clo` with the capture time sliced to `51r` / `yest` / `7`. The column
 * that went over the edge is the one carrying the caveat about whether the
 * number beside it is still live, so the table lost exactly the thing a reader
 * needs when its rows disagree with each other.
 *
 * ═══ WHY THIS GUARD IS AN ARITHMETIC BUDGET AND NOT A CLASS-NAME CHECK ═══
 *
 * jsdom has no layout engine, so nothing here can measure a rendered column. The
 * obvious substitute — assert the cells say `px-2` — is a guard that restates the
 * diff: it passes on any padding spelled `px-2` and says nothing about whether
 * that padding FITS, which is the actual claim.
 *
 * So the padding is read back OUT of the emitted markup and spent against a
 * budget measured on the real page. The model is
 *
 *     intrinsic width = CONTENT_PX + 2 * pad * columns
 *
 * and it is not a hypothesis: it reproduces all three production readings to
 * within a tenth of a pixel, which is why it can be trusted to price a padding
 * nobody has shot yet.
 *
 *     pad 16px (`px-4`)   253.7 + 128 = 381.7   measured 381.7   48px over
 *     pad 12px (`px-3`)   253.7 +  96 = 349.7   measured 349.7   16px over
 *     pad  8px (`px-2`)   253.7 +  64 = 317.7   measured  0 over (it fits)
 *
 * A future `px-3` "tidy-up" therefore fails here with the same 16px production
 * would have shown, rather than passing a spelling check and shipping.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A table that renders no cells at all has no padding to object to and would
 * satisfy every budget below, so the cell census is asserted first and the
 * fourth column is required BY NAME. The desktop width is pinned too: this is a
 * phone fix, and silently taking `px-4` away from `sm` and up would be a second
 * regression wearing the first one's fix.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import BookmakerTable from "@/components/BookmakerTable";
import type { BookmakerOddsDetail } from "@/lib/types";

/** The scroll container on the filed page, measured — not the 390px viewport. */
const CONTAINER_PX = 334;

/**
 * The table's content with every horizontal padding removed, measured.
 *
 * Derived from the shipped render rather than from glyph counting: at `px-4` the
 * four columns totalled 381.7px and carried 128px of chrome. `px-3` independently
 * gave 349.7 − 96 = 253.7, which is what makes it a measurement of the content
 * and not an artifact of one padding.
 */
const CONTENT_PX = 253.7;

const COLUMNS = 4;

/**
 * Both status branches, on every run.
 *
 * `isStale` is a 30-minute window measured against `new Date()` at render time,
 * so a fixture with wall-clock timestamps would drift into one branch and stop
 * exercising the other — offsets, not dates (gotcha #44). One row is inside the
 * window and one is well outside it, so the `Open` pill and the `Closed` pill are
 * both in the markup whenever this file runs.
 */
const ODDS: BookmakerOddsDetail[] = [
  { bookmaker: "betmgm", home_probability: 0.614, away_probability: 0.386,
    captured_at: new Date(Date.now() - 5 * 60_000).toISOString() },
  { bookmaker: "fanduel", home_probability: 0.598, away_probability: 0.402,
    captured_at: new Date(Date.now() - 3 * 60 * 60_000).toISOString() },
  { bookmaker: "draftkings", home_probability: 0.602, away_probability: 0.398,
    captured_at: new Date(Date.now() - 26 * 60 * 60_000).toISOString() },
] as unknown as BookmakerOddsDetail[];

function tableHtml(): string {
  return renderToStaticMarkup(
    <BookmakerTable bookmakerOdds={ODDS} homeTeam="Karen Khachanov" awayTeam="Alexander Blockx" />
  );
}

/** Every `<th>`/`<td>`'s class attribute, in document order. */
function cellClasses(html: string): string[] {
  return [...html.matchAll(/<(?:th|td)\b([^>]*)>/g)].map(
    (match) => /class="([^"]*)"/.exec(match[1])?.[1] ?? ""
  );
}

/**
 * The phone padding this markup actually asks for, in px.
 *
 * Reads the Tailwind step off the class and converts it, so the budget below is
 * spent against what the component emits rather than against a number this file
 * keeps in step by hand. Throws on a spelling it does not recognise — an
 * arbitrary `px-[13px]` must not silently price as zero and pass.
 */
function phonePaddingPx(cls: string): number {
  const step = /(?:^|\s)px-(\d+(?:\.\d+)?)(?:\s|$)/.exec(cls);
  if (!step) throw new Error(`no unprefixed px-* padding on a cell: ${JSON.stringify(cls)}`);
  return Number(step[1]) * 4;
}

/**
 * The words inside one `<th>`, for naming the columns this budget is about.
 *
 * Reads the two shapes this header really emits — a bare string, and the team
 * columns' `<div>` wrapper — rather than stripping tags with a `replace`. That is
 * not fussiness: a strip is a sanitizer shape, CodeQL flags it
 * `js/incomplete-multi-character-sanitization` at HIGH severity, and the first
 * draft of this file was red on exactly that (the same finding
 * `sportsbookNamesNotRawKeys4284` records against its own first draft). Reading
 * the shapes you expect, and throwing on one you do not, is both cleaner and
 * louder than a strip that silently half-works.
 */
function headerLabel(body: string): string {
  const divs = [...body.matchAll(/<div\b[^>]*>([^<]*)<\/div>/g)];
  if (divs.length > 0) return divs.map((match) => match[1]).join(" ").trim();
  if (body.includes("<")) {
    throw new Error(`unrecognised <th> body shape: ${JSON.stringify(body)}`);
  }
  return body.trim();
}

describe("#4317 — the sportsbook table fits a 390px phone", () => {
  it("renders the four columns this budget is about", () => {
    // The positive control. Everything below is vacuous against a table that
    // drew nothing, and `BookmakerTable` really does have an empty state.
    const html = tableHtml();
    const headers = [...html.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((m) =>
      headerLabel(m[1])
    );
    expect(headers).toHaveLength(COLUMNS);
    expect(headers[0]).toBe("Sportsbook");
    // The column that went over the edge, by name — this fix is about that one.
    expect(headers[COLUMNS - 1]).toBe("Status");
    expect(cellClasses(html).length).toBeGreaterThanOrEqual(COLUMNS);
  });

  it("spends a padding the measured container can afford", () => {
    const html = tableHtml();
    const paddings = [...new Set(cellClasses(html).map(phonePaddingPx))];
    // One padding for the whole table: a per-column mixture would make the
    // budget below meaningless and is not a thing this component should grow.
    expect(paddings).toHaveLength(1);
    const pad = paddings[0];

    const intrinsicPx = CONTENT_PX + 2 * pad * COLUMNS;
    expect(intrinsicPx).toBeLessThanOrEqual(CONTAINER_PX);

    // …and state the headroom the model gives, so the next person changing this
    // knows how much room there is rather than rediscovering it on production.
    expect(pad).toBeLessThanOrEqual((CONTAINER_PX - CONTENT_PX) / (2 * COLUMNS));
  });

  it("prices what shipped, and the tidy-up that would not have worked either", () => {
    // The model earns its authority by reproducing the readings it was not fitted
    // to. If a refactor invalidates these, the budget above is no longer measuring
    // anything and should be re-measured rather than adjusted.
    expect(CONTENT_PX + 2 * 16 * COLUMNS).toBeCloseTo(381.7, 1); // px-4, 48px over
    expect(CONTENT_PX + 2 * 12 * COLUMNS).toBeCloseTo(349.7, 1); // px-3, 16px over
    expect(CONTENT_PX + 2 * 16 * COLUMNS - CONTAINER_PX).toBeCloseTo(47.7, 1);
    expect(CONTENT_PX + 2 * 12 * COLUMNS).toBeGreaterThan(CONTAINER_PX);
  });

  it("keeps the full padding from `sm` up, where there was never a problem", () => {
    // Both directions. Shrinking the phone is the fix; shrinking the desktop with
    // it would be a regression this file had waved through.
    const classes = cellClasses(tableHtml());
    expect(classes.length).toBeGreaterThan(0);
    for (const cls of classes) {
      expect(cls).toContain("sm:px-4");
    }
  });
});
