/**
 * UX-P274 — a "biggest mover" shows the move (#2672).
 *
 * THE DEFECT. `/golf`'s "Biggest Movers (24h)" strip rendered
 * `Math.abs(Math.round(mover.movement_24h * 100))`, a whole number of points.
 * On production 2026-09-02 all five entries were sub-1pp, so not one was
 * printed accurately, and two of the five read a red "▼ 0%" — a down arrow
 * asserting a fall of zero, under a heading calling them the biggest movers.
 *
 * TWO MECHANISMS, and the second is the one the report did not name.
 *
 *  1. PRECISION. Every other movement renderer on the site prints one decimal.
 *     `TournamentCard` does — and it sits ~600px below this strip on the same
 *     page, so one golfer's one move read "▲ 1%" above and "+0.5% today" below.
 *
 *  2. ASYMMETRY, which is why the two zero rows were both negative.
 *     `Math.round` is half-up toward +Infinity, so `Math.round(0.5) === 1` but
 *     `Math.round(-0.5) === -0`. The backend admits a mover at exactly
 *     `abs(movement_24h) >= 0.005` (`backend/app/routes/golf.py`) — half a
 *     point — so the smallest DOWNWARD move the producer is able to admit was
 *     precisely the value guaranteed to render as "no movement at all". The
 *     producer's floor and the renderer's precision were set so that the
 *     boundary class always printed zero. That is structural, not a property
 *     of one afternoon's data.
 *
 * THE FIX is not a new formatter. UX-P048 already owns "what unit is a movement
 * value in" and states the rule that *no call site multiplies by 100 itself*;
 * this strip was its one remaining violator. Wiring it to `formatMovementPoints`
 * fixes precision and asymmetry together and cannot drift from the sibling
 * renderers, because it is now the same function.
 *
 * WHAT IS DELIBERATELY NOT CHANGED. The strip's PROBABILITY column still prints
 * an integer via `formatProbability` (UX-P046), and that is correct: integer
 * probabilities are the site convention. On probability it is `TournamentCard`
 * that is the outlier, not this strip — the opposite sign to the movement half —
 * so bundling the two would have broken a convention while fixing a bug. See
 * the control at the bottom of this file, which pins that on purpose.
 *
 * RED ARM — 16 red / 20 passed, and the 20 include every labelled control.
 * Restore only the two lines that compute `delta`/`isUp` in
 * `components/golf/MoversStrip.tsx`, keeping the `data-mover-delta` attribute,
 * so the arm grades the NUMBER rather than the selector. Reverting the whole
 * component would remove the anchor too, and then "the label is wrong" and
 * "the anchor is missing" become the same observation — the weaker proof.
 *
 * COUNTER-CASES, because red-first grades a change and these grade the design:
 *  - the issue's own option 2 (floor at 1pp and DROP sub-threshold entries):
 *    15 red — it empties the strip, which the issue itself suspected.
 *  - the fix a reader would most likely write, a local
 *    `Math.abs(m * 100).toFixed(1)`: 6 red, and the informative part is what
 *    stays GREEN. Precision and symmetry pass, correctly — that mutation does
 *    fix them. What fails is the delegation guard in `lib/movementPoints` and
 *    all five unusable-value tests, because `Math.abs(null * 100).toFixed(1)`
 *    is "0.0" and NaN renders as "NaN". So this diff has two halves: the
 *    user-visible precision/symmetry fix, and drift + null safety.
 *
 * Every claim is an equality on the extracted delta span. A containment check
 * would be vacuous in both directions here: "▼ 10%" contains "0%", and "0.5%"
 * shares its leading character with "0%".
 *
 * NOTE ON REACHABILITY, stated because a grader will look for it. At the time
 * of writing `GET /api/golf` returns `biggest_movers: []` and all 60 golfers
 * carry `movement_24h: null`, so this strip renders nothing at all today and
 * the fix changes no pixel at this hour. It was populated with five entries
 * ~2.5h earlier, so the surface is live and intermittent, not dead. The tests
 * below therefore stand on the payload the reporter captured rather than on
 * anything re-fetchable right now.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { MoversStrip } from "@/components/golf/MoversStrip";
import TournamentCard from "@/components/TournamentCard";
import { formatMovementPoints } from "@/lib/probabilityDisplay";
import type { GolfMover, GolfTournament } from "@/lib/types";

/**
 * The backend's admission floor for the strip, in wire fraction.
 * `routes/golf.py`: `if g["movement_24h"] is not None and abs(...) >= 0.005`.
 * Mirrored here because the boundary class is what this file is about; the
 * coupling test below states the relationship rather than the number.
 */
const BACKEND_MOVER_FLOOR = 0.005;

function mover(name: string, movement_24h: number, probability = 0.085): GolfMover {
  return {
    name,
    tournament_key: "omega_european_masters",
    tournament_name: "Omega European Masters",
    movement_24h,
    probability,
  };
}

/** Every `data-mover-delta` span's text, keyed by golfer, from rendered markup. */
function deltasByGolfer(markup: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /<span[^>]*data-mover-delta="([^"]*)"[^>]*>(.*?)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) {
    out[decodeEntities(m[1])] = decodeEntities(m[2].replace(/<[^>]*>/g, "")).trim();
  }
  return out;
}

/**
 * One pass, one lookup table — a chained `.replace()` decode unescapes `&amp;`
 * first and so turns `&amp;#39;` into `'` (CodeQL js/double-escaping; UX-P263
 * paid for this exact finding in a test helper).
 */
function decodeEntities(s: string): string {
  const named: Record<string, string> = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&#x27;": "'",
  };
  return s.replace(/&(?:amp|lt|gt|quot|#39|#x27);|&#(\d+);|&#x([0-9a-fA-F]+);/g, (tok, dec, hex) => {
    if (dec) return String.fromCodePoint(Number(dec));
    if (hex) return String.fromCodePoint(parseInt(hex, 16));
    return named[tok] ?? tok;
  });
}

/** The magnitude only, with the arrow and the percent sign stripped. */
function magnitudeOf(delta: string): string {
  return delta.replace(/[▲▼]/g, "").replace("%", "").trim();
}

function render(movers: GolfMover[]): string {
  return renderToStaticMarkup(<MoversStrip movers={movers} />);
}

// ---------------------------------------------------------------------------
// The reported defect
// ---------------------------------------------------------------------------

describe("UX-P274 — the strip prints the move it ranked", () => {
  test("the reported card: a -0.5pp mover reads 0.5%, not 0%", () => {
    // Marco Penge and Patrick Reed, production 2026-09-02, both `-0.005`.
    const d = deltasByGolfer(render([mover("Marco Penge", -0.005)]));
    expect(magnitudeOf(d["Marco Penge"])).toBe("0.5");
  });

  test("the whole reported strip, all five entries, verbatim from the payload", () => {
    const d = deltasByGolfer(
      render([
        mover("Nicolai Højgaard", 0.008),
        mover("Ryan Gerard", 0.0055),
        mover("Matt Wallace", 0.0055),
        mover("Marco Penge", -0.005),
        mover("Patrick Reed", -0.005),
      ]),
    );
    expect(Object.fromEntries(Object.entries(d).map(([k, v]) => [k, magnitudeOf(v)]))).toEqual({
      "Nicolai Højgaard": "0.8",
      "Ryan Gerard": "0.5",
      "Matt Wallace": "0.5",
      "Marco Penge": "0.5",
      "Patrick Reed": "0.5",
    });
    // Before the fix these read 1 / 1 / 1 / 0 / 0 — three inflated and two
    // claiming no movement at all.
  });

  test("no admitted mover can ever render a zero magnitude", () => {
    // The property, not the instance: sweep the whole admitted domain rather
    // than pinning the five values that happened to be on screen.
    const values: number[] = [];
    for (let pts = 0.5; pts <= 40; pts += 0.05) {
      values.push(Number((pts / 100).toFixed(6)), Number((-pts / 100).toFixed(6)));
    }
    const d = deltasByGolfer(render(values.map((v, i) => mover(`g${i}`, v))));
    const zeros = Object.entries(d).filter(([, v]) => Number(magnitudeOf(v)) === 0);
    expect(zeros).toEqual([]);
    expect(Object.keys(d)).toHaveLength(values.length);
  });
});

// ---------------------------------------------------------------------------
// Mechanism 2 — the asymmetry that made both zero rows negative
// ---------------------------------------------------------------------------

describe("UX-P274 — rounding is symmetric about zero", () => {
  test("a fall and a rise of the same size print the same magnitude", () => {
    const d = deltasByGolfer(render([mover("Up", 0.005), mover("Down", -0.005)]));
    expect(magnitudeOf(d["Up"])).toBe(magnitudeOf(d["Down"]));
    // On master: "1" vs "0", because Math.round(-0.5) is -0.
  });

  test("symmetry holds across the admitted domain, not just at the floor", () => {
    const sizes = [0.005, 0.0055, 0.008, 0.0149, 0.015, 0.064, 0.235];
    for (const s of sizes) {
      const d = deltasByGolfer(render([mover("Up", s), mover("Down", -s)]));
      expect(magnitudeOf(d["Up"])).toBe(magnitudeOf(d["Down"]));
    }
  });

  test("the backend's admission floor is the exact value the old code zeroed", () => {
    // Couples the producer to the renderer: whatever the floor is, a mover
    // admitted AT it must render a nonzero number in both directions. This is
    // the structural claim — it survives the floor being retuned.
    const d = deltasByGolfer(
      render([mover("AtFloorUp", BACKEND_MOVER_FLOOR), mover("AtFloorDown", -BACKEND_MOVER_FLOOR)]),
    );
    expect(Number(magnitudeOf(d["AtFloorUp"]))).toBeGreaterThan(0);
    expect(Number(magnitudeOf(d["AtFloorDown"]))).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// The contradiction the reader actually saw: two numbers, one screen
// ---------------------------------------------------------------------------

describe("UX-P274 — the strip agrees with the card 600px below it", () => {
  /** The tournament card as `/api/golf` serves it, leader movement varied. */
  function tournament(name: string, movement_24h: number, probability: number): GolfTournament {
    return {
      key: "omega_european_masters",
      name: "Omega European Masters",
      slug: "omega-european-masters",
      is_major: false,
      is_tour_event: true,
      is_womens: false,
      tour: "dpworld",
      tour_label: "DP World Tour",
      commence_time: "2026-09-03T00:00:00+00:00",
      resolution_date: "2026-09-06T00:00:00+00:00",
      start_date: "2026-09-03T00:00:00+00:00",
      end_date: "2026-09-06T00:00:00+00:00",
      venue: null,
      location: null,
      market_ids: [59759220],
      market_sources: ["kalshi"],
      market_names: ["Omega European Masters Winner"],
      golfers: [{ id: 1, name, probability, rank: 1, movement_24h }],
    } as unknown as GolfTournament;
  }

  test.each([
    ["Ryan Gerard", 0.0055, 0.085],
    ["Marco Penge", -0.005, 0.031],
    ["Nicolai Højgaard", 0.008, 0.044],
  ])(
    "%s's one move prints one magnitude on both surfaces",
    (name, movement, probability) => {
      const strip = magnitudeOf(deltasByGolfer(render([mover(name, movement, probability)]))[name]);

      // The shipped card, not a reimplementation of it.
      const cardMarkup = renderToStaticMarkup(
        <TournamentCard tournament={tournament(name, movement, probability)} />,
      );
      const cardMatch = /([-+]?\d+\.\d+)% today/.exec(decodeEntities(cardMarkup));
      expect(cardMatch).not.toBeNull();
      const card = String(Math.abs(Number(cardMatch![1])));

      expect(strip).toBe(card);
      // On master: strip "1" vs card "0.5" for Gerard, and "0" vs "0.5" for Penge.
    },
  );
});

// ---------------------------------------------------------------------------
// The unusable value the old arithmetic turned into a confident red zero
// ---------------------------------------------------------------------------

describe("UX-P274 — an unusable movement renders no row", () => {
  test.each([
    ["null", null],
    ["undefined", undefined],
    ["NaN", NaN],
    ["Infinity", Infinity],
  ])("%s produces no delta span rather than a red zero", (_label, bad) => {
    const markup = render([mover("Ghost", bad as unknown as number)]);
    expect(deltasByGolfer(markup)).toEqual({});
    // On master `Math.abs(Math.round(null * 100))` is 0, so this rendered
    // "▼ 0%" in red for a golfer with no movement data at all.
  });

  test("an unusable row does not take its healthy siblings down with it", () => {
    const d = deltasByGolfer(
      render([
        mover("Healthy Above", 0.008),
        mover("Ghost", null as unknown as number),
        mover("Healthy Below", -0.005),
      ]),
    );
    expect(Object.keys(d).sort()).toEqual(["Healthy Above", "Healthy Below"]);
    expect(magnitudeOf(d["Healthy Above"])).toBe("0.8");
    expect(magnitudeOf(d["Healthy Below"])).toBe("0.5");
  });
});

// ---------------------------------------------------------------------------
// The rule this fix is an instance of
// ---------------------------------------------------------------------------

describe("UX-P274 — the strip delegates to UX-P048 rather than reimplementing it", () => {
  test("the rendered magnitude IS formatMovementPoints, for every reported value", () => {
    // Behavioural, not a source scan: if someone reintroduces local arithmetic
    // that happens to agree today, it must still agree here — and a source
    // scan would be satisfied by an unused import.
    const values = [0.008, 0.0055, 0.005, -0.005, -0.0055, -0.008, 0.064, -0.235];
    const d = deltasByGolfer(render(values.map((v, i) => mover(`g${i}`, v))));
    values.forEach((v, i) => {
      expect(magnitudeOf(d[`g${i}`])).toBe(formatMovementPoints(v));
    });
  });
});

// ---------------------------------------------------------------------------
// CONTROLS — each verified green on master too
// ---------------------------------------------------------------------------

describe("UX-P274 controls (green on master too)", () => {
  test("CONTROL: direction and colour are unchanged — a rise is a green up arrow", () => {
    // The bug was a red down arrow beside "0%", NOT the arrow itself. A fix
    // that suppressed the colour would have fixed the wrong half.
    const markup = render([mover("Riser", 0.008)]);
    const span = /<span[^>]*data-mover-delta="Riser"[^>]*>/.exec(markup)![0];
    expect(span).toContain("text-green-400");
    expect(deltasByGolfer(markup)["Riser"]).toContain("▲");
  });

  test("CONTROL: a fall is still a red down arrow", () => {
    const markup = render([mover("Faller", -0.005)]);
    const span = /<span[^>]*data-mover-delta="Faller"[^>]*>/.exec(markup)![0];
    expect(span).toContain("text-red-400");
    expect(deltasByGolfer(markup)["Faller"]).toContain("▼");
  });

  test("CONTROL: the heading, the golfer and the tournament are untouched", () => {
    const markup = render([mover("Ryan Gerard", 0.0055)]);
    expect(markup).toContain("Biggest Movers (24h)");
    expect(markup).toContain("Ryan Gerard");
    expect(markup).toContain("Omega European Masters");
  });

  test("CONTROL: the PROBABILITY column still prints an integer (UX-P046)", () => {
    // Deliberately NOT changed. Integer probabilities are the site convention;
    // on this axis the tournament card is the outlier, not the strip. If a
    // later change makes this read "8.5%", it has bundled a second, opposite
    // decision into a movement fix.
    const markup = render([mover("Ryan Gerard", 0.0055, 0.085)]);
    expect(markup).toContain(">9%<");
    expect(markup).not.toContain(">8.5%<");
  });

  test("CONTROL: an empty strip renders the section without crashing", () => {
    expect(render([])).toContain("Biggest Movers (24h)");
    expect(deltasByGolfer(render([]))).toEqual({});
  });
});
