/**
 * UX-P201 — THE HURRICANE CARD STOPS PRINTING PERCENTAGES NO MARKET PRODUCED.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/weather` renders `<NaturalEvents />`, which renders `<HurricaneTracker />`
 * as the wide (1.4fr) anchor of its three-card grid. Rendered over the REAL
 * production payload on 2026-08-30, that card printed **twelve** percentages
 * and only **four** of them came from a market:
 *
 *     80%   ← hard-coded hero, captioned "≥1 major hurricane in 2026"
 *     21 34 58 78 88 60 24   ← hard-coded monthly climatology bars
 *     96 95 95 94            ← the four real Kalshi/Polymarket prices
 *
 * The 80% was not a market price, was not close to one, and no market matching
 * its caption existed in the payload at all: of the 45 real hurricane markets
 * served that day, **none** had `prob == 80`. It was rendered through
 * `ProbabilityNumber` — the same component the real prices use — at size 32 with
 * `forceColor="#22C55E"`, directly above four real rows. Nothing distinguished
 * it from a price.
 *
 * This is the TRUTH pillar at its most literal: the product's promise is that a
 * number on the screen is what a market thinks. Eight of these twelve were not.
 *
 * ═══ WHY THEY WERE THERE ═══
 *
 * They are survivors of a purge, not a decision. `567e22b4` ("Weather: remove
 * fabricated Kalshi data") and `8484c3ce` ("Replace weather hardcoded fallback
 * data with loading skeletons") emptied every mock array in `data.ts` —
 * `HURRICANE`, `EARTHQUAKE`, `TORNADOES` and the rest are all `[]` today. But
 * `HurricaneTracker.tsx` held its OWN local `months` array and its own literal
 * `value={80}`, and neither purge commit ever opened the file: its whole history
 * is `b84addc2`, `e566ea87`, `88619fb3`. The sweep missed it.
 *
 * ═══ WHY THE BEFORE FIXTURE IS THE REAL RAIL ═══
 *
 * `uxp201_hurricane_before.html` is not hand-written. It is the markup emitted by
 * the PARENT commit's component — extracted byte-identically via
 * `git show c4742717:frontend/components/weather/HurricaneTracker.tsx` (md5
 * verified against the working tree before the edit) — rendered over
 * `uxp201_weather_events.json`, which is the verbatim `GET /api/weather/events`
 * production response. Neither side is a re-implementation.
 *
 * ═══ WHY THE CORE ASSERTION IS A SUBSET, NOT AN ABSENCE ═══
 *
 * A guard that says `expect(html).not.toContain("80")` is one refactor away from
 * meaning nothing, and this lane has now shipped SEVEN variants of that bug
 * (the "unit-test-the-predicate hole"). So the assertion is instead: the set of
 * percentages the card PRINTS must be a subset of the set of prices the payload
 * CARRIES. That cannot be satisfied vacuously and it does not decay — any future
 * hard-coded number, of any value, in any slot, fails it.
 *
 *   cd frontend && TZ=UTC npx jest --testPathPatterns=weatherHurricaneUnsourced
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import HurricaneTracker from "@/components/weather/HurricaneTracker";
import type { EventMarket } from "@/components/weather/data";

const FIXTURES = path.join(__dirname, "..", "fixtures");

const payload = JSON.parse(
  fs.readFileSync(path.join(FIXTURES, "uxp201_weather_events.json"), "utf8")
) as { hurricane: EventMarket[] };

const HURRICANE = payload.hurricane;

const beforeHtml = fs.readFileSync(
  path.join(FIXTURES, "uxp201_hurricane_before.html"),
  "utf8"
);

const afterHtml = renderToStaticMarkup(<HurricaneTracker items={HURRICANE} />);

/**
 * Every percentage the card puts in front of a reader, in document order.
 *
 * Deliberately matches BOTH renderings a percentage can take here, because the
 * defect used the second one and a guard blind to it would be blind to the
 * defect coming back:
 *   - a plain row price   `>96%<`
 *   - a ProbabilityNumber `>80<span style="...">%</span>`
 * Bar widths (`width:96%` inside a style attribute) are not printed text and are
 * excluded by the leading `>`.
 */
function printedPercents(html: string): number[] {
  const out: number[] = [];
  const re = /(?:>(\d{1,3})<span[^>]*>%<\/span>)|(?:>(\d{1,3})%<)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out.push(Number(m[1] ?? m[2]));
  return out;
}

/**
 * The card's OWN heading — the text it asserts in its own voice, as distinct
 * from the market names it quotes. The distinction is load-bearing: "Atlantic"
 * is still all over this card, because real market questions say it ("When will
 * the next Atlantic hurricane form?"). Those are data and must survive. What
 * must not survive is the card claiming a basin the rail never filtered on.
 */
function heading(html: string): string {
  return html.match(/<h3[^>]*>([^<]*)<\/h3>/)?.[1] ?? "";
}

describe("UX-P201 — the control: the BEFORE rail still carries the defect", () => {
  /**
   * If any of these three ever fail, the BEFORE fixture has lost the defect and
   * every AFTER assertion below is passing vacuously. This is the test that
   * makes the rest of the file mean something.
   */
  it("the parent's card printed twelve percentages over the real payload", () => {
    expect(printedPercents(beforeHtml)).toEqual([
      80, 21, 34, 58, 78, 88, 60, 24, 96, 95, 95, 94,
    ]);
  });

  it("eight of them matched no market in that same payload", () => {
    const real = new Set(HURRICANE.map((m) => m.prob));
    const printed = printedPercents(beforeHtml);
    // 21/34/58/24 are absent outright; 80 is the hero. 78/88/60 collide by
    // coincidence with some market's price, which is exactly why "is this value
    // present somewhere" is the wrong question and position matters: the first
    // eight printed numbers were produced by no market, whatever they equal.
    expect(printed.slice(0, 8)).toEqual([80, 21, 34, 58, 78, 88, 60, 24]);
    expect(real.has(80)).toBe(false);
    expect(beforeHtml).toContain("major hurricane in 2026");
  });

  it("the parent claimed a basin the rail does not filter on", () => {
    expect(heading(beforeHtml)).toBe("Atlantic season tracker");
  });
});

describe("UX-P201 — every printed number is now a market price", () => {
  it("the printed set is a subset of the payload's prices", () => {
    const real = new Set(HURRICANE.map((m) => m.prob));
    const unsourced = printedPercents(afterHtml).filter((p) => !real.has(p));
    expect(unsourced).toEqual([]);
  });

  it("printed numbers correspond one-for-one, in order, to the rows rendered", () => {
    // Stronger than the subset: the card may print a price only where it is
    // actually rendering that market's row. A stray constant that happened to
    // equal some market's price would pass the subset check and fail this one.
    const expected = HURRICANE.slice(0, 8).map((m) => m.prob);
    expect(printedPercents(afterHtml)).toEqual(expected);
  });

  it("the fabricated hero and the climatology chart are both gone", () => {
    expect(afterHtml).not.toContain("major hurricane in 2026");
    for (const month of ["May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]) {
      expect(afterHtml).not.toContain(`>${month}<`);
    }
  });

  it("the card no longer claims a basin in its own voice", () => {
    expect(heading(afterHtml)).toBe("Hurricane markets");
    expect(heading(afterHtml)).not.toMatch(/atlantic|pacific/i);
    // ...but it still quotes the markets that name one. Deleting the word
    // everywhere would have been a data loss dressed up as a truth fix.
    expect(afterHtml).toContain("When will the next Atlantic hurricane form?");
  });
});

describe("UX-P201 — the card did not lose its real content", () => {
  /**
   * The cheap way to pass every assertion above is to render nothing. These
   * assert the ship ADDED truth rather than subtracting the card.
   */
  it("still renders real market rows, with more of them than before", () => {
    expect(printedPercents(afterHtml)).toHaveLength(8);
    expect(printedPercents(beforeHtml).slice(8)).toHaveLength(4);
  });

  it("still names the real markets and their sources", () => {
    expect(afterHtml).toContain("When will the next Atlantic hurricane form?");
    expect(afterHtml).toContain("Hurricane Marie category?");
    expect(afterHtml).toContain("Kalshi");
    expect(afterHtml).toContain("Polymarket");
  });

  it("renders every row it is given, without inventing one", () => {
    const three = HURRICANE.slice(0, 3);
    const html = renderToStaticMarkup(<HurricaneTracker items={three} />);
    expect(printedPercents(html)).toEqual(three.map((m) => m.prob));
  });
});

describe("UX-P201 — the artifact", () => {
  it("writes the rendered before/after card", () => {
    const out = path.join(__dirname, "..", "..", "..", "artifacts-ux-p201");
    if (!fs.existsSync(out)) return; // artifacts dir is scratch, not required
    const panel = (title: string, note: string, html: string) => `
      <section style="margin:0 0 36px;max-width:640px">
        <h2 style="font:600 18px system-ui;margin:0 0 4px">${title}</h2>
        <p style="font:13px system-ui;color:#6B7280;margin:0 0 14px">${note}</p>
        ${html}
      </section>`;
    const doc = `<!doctype html><meta charset="utf-8">
      <title>UX-P201 — /weather hurricane card</title>
      <body style="padding:32px;background:#F9FAFB;font-family:system-ui">
      <h1 style="font:600 22px system-ui">UX-P201 — the hurricane card stops printing percentages no market produced</h1>
      <p style="font:13px system-ui;color:#6B7280;max-width:60em">
        Both panels are the shipped <code>HurricaneTracker</code> rendered over the same verbatim
        <code>GET /api/weather/events</code> production payload (2026-08-30, 45 real hurricane markets).
        BEFORE is the parent commit <code>c4742717</code> extracted byte-identically.
      </p>
      ${panel("BEFORE — 12 percentages, 4 of them from a market", "The 80% hero matched no market in the payload; the seven monthly bars matched nothing at all.", beforeHtml)}
      ${panel("AFTER — 8 percentages, all 8 from a market", "Hero and climatology chart removed; the freed space carries four more real markets.", afterHtml)}
      </body>`;
    const dest = path.join(out, "hurricane-card.html");
    fs.writeFileSync(dest, doc);
    // A capture that silently wrote nothing proves nothing.
    expect(fs.statSync(dest).size).toBeGreaterThan(2000);
  });
});
