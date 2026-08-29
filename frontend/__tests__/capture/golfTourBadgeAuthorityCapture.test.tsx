/**
 * UX-P181 — THE OMEGA EUROPEAN MASTERS STOPS BEING BADGED "PGA TOUR".
 *
 * ═══ WHAT THIS IS ═══
 *
 * `GET /api/golf` served, in ONE payload, two contradictory answers about the
 * same tournament:
 *
 *   tournaments[].tour_label   "PGA Tour"                  <- the card's ⛳ chip
 *   pga_schedule[].tour        "euro"  (= DP World Tour)   <- the same payload
 *
 * The Omega European Masters is a DP World Tour event. Its only open market is
 * `KXDPWORLDTOUR-OMEM26` — Kalshi's own series ticker names the tour — and its
 * sibling one week earlier, the Husqvarna British Masters, was already filed
 * correctly as `dp_world`. `_classify_tour` (backend, `app/routes/golf.py`)
 * consulted neither the ticker nor the schedule and ended in a bare
 * `return "pga"`: 69 of 110 open golf markets were decided by that default and
 * 8 of them carried a ticker that contradicted it.
 *
 * The fix is backend-only. THIS file's job is the other half — proving the fixed
 * value actually reaches a pixel, because a backend guard that stops at the
 * return value is blind to a render that never reads it.
 *
 * ═══ THE READER ═══
 *
 * `components/TournamentCard.tsx:66` — `tour_label || tour?.toUpperCase() ||
 * "Golf"` — rendered at SIX call sites across FIVE files, including
 * `components/FeedCard.tsx` (the Discover feed) and `/sport/*`.
 *
 * And it is not only a chip: on `/categories/golf` the `tour` key is the SECTION
 * GROUPING (`app/categories/golf/page.tsx:246-273`, `TOUR_ORDER` at :144) and
 * `tour_label` is the section HEADING. The page filed two consecutive-week DP
 * World Tour events under two different headings, one of them wrong.
 *
 * (The per-tour Follow control at page.tsx:292 is decorative — it does not
 * filter — so no content was hidden. Stated rather than overclaimed.)
 *
 * ═══ WHY THE GUARDS LOOK LIKE THIS ═══
 *
 * No timezone gate. Unlike UX-P179 and UX-P180 — its two immediate predecessors
 * on this same card — this defect has nothing to do with dates, so a zone guard
 * would buy nothing and copying one would be cargo cult.
 *
 * `theProbeCanTellTheTwoApart` proves the instrument: it requires the served
 * (defective) payload and the fixed payload to render DIFFERENT badges through
 * the identical probe. A discriminator nobody has watched discriminate is a
 * decoration.
 *
 *   cd frontend && npx jest --testPathPatterns=golfTourBadgeAuthority
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

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";

import fixture from "../fixtures/uxp181_golf_tour_badge.json";

type Served = {
  tournaments_as_served: GolfTournament[];
  pga_schedule_rows: { name: string; tour: string }[];
  expected_after: Record<string, { tour: string; tour_label: string }>;
};

const FX = fixture as unknown as Served;

function served(key: string): GolfTournament {
  const t = FX.tournaments_as_served.find((x) => x.key === key);
  if (!t) throw new Error(`fixture no longer carries ${key}`);
  return t;
}

/** The tournament as it WILL be served once the backend fix deploys. */
function fixed(key: string): GolfTournament {
  const after = FX.expected_after[key];
  if (!after) throw new Error(`fixture declares no expected_after for ${key}`);
  return { ...served(key), ...after };
}

const OMEGA = "omega_european_masters";
const HUSQVARNA = "husqvarna_british_masters";
const TOUR_CHAMPIONSHIP = "tour_championship";

/**
 * The tour chip, and only the tour chip. `⛳` prefixes exactly one element in
 * this component, so anchoring the probe to it keeps the card's other prose —
 * leaderboard strings, "Final", the live label — out of the read. (UX-P180 paid
 * for the looser version: a `visibleText` sweep matched "End of Round 3".)
 */
const CHIP = /<span>⛳ ([^<]*)<\/span>/;

function badge(t: GolfTournament): string {
  const markup = renderToStaticMarkup(
    React.createElement(TournamentCard as React.FC, { tournament: t } as never),
  );
  const m = markup.match(CHIP);
  if (!m) throw new Error("no ⛳ chip in the rendered card — the probe has drifted");
  return m[1];
}

/* ═══════════════════════════════════════════════════════════════════════ */
/* 1 · THE PREMISE — one payload, two answers.                              */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P181 · the premise, on the banked production payload", () => {
  it("the schedule row in the SAME payload calls Omega a euro (DP World) event", () => {
    const row = FX.pga_schedule_rows.find((r) => r.name === "Omega European Masters");
    expect(row).toBeDefined();
    expect(row!.tour).toBe("euro");
  });

  it("...while the tournament it serves alongside it was labelled PGA Tour", () => {
    expect(served(OMEGA).tour).toBe("pga");
    expect(served(OMEGA).tour_label).toBe("PGA Tour");
  });

  it("its sibling one week earlier was already filed correctly as DP World", () => {
    const h = served(HUSQVARNA);
    expect(h.tour).toBe("dp_world");
    expect(h.tour_label).toBe("DP World Tour");
    // Same tour, consecutive weeks, and the page split them across two sections.
    expect(served(OMEGA).tour).not.toBe(h.tour);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 2 · THE SHIP — rendered by the real card.                                */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P181 · the rendered ⛳ chip", () => {
  it("the served payload renders the defect — ⛳ PGA Tour", () => {
    expect(badge(served(OMEGA))).toBe("PGA Tour");
  });

  it("the fixed payload renders ⛳ DP World Tour", () => {
    expect(badge(fixed(OMEGA))).toBe("DP World Tour");
  });

  it("theProbeCanTellTheTwoApart — the instrument is not a decoration", () => {
    expect(badge(served(OMEGA))).not.toBe(badge(fixed(OMEGA)));
  });

  it("the chip is driven by tour_label, so a backend fix reaches this pixel", () => {
    const t = { ...served(OMEGA), tour_label: "Sunshine Tour" } as GolfTournament;
    expect(badge(t)).toBe("Sunshine Tour");
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 3 · THE CONTROLS — nothing that was right moves.                         */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P181 · controls", () => {
  it.each([
    [HUSQVARNA, "DP World Tour"],
    [TOUR_CHAMPIONSHIP, "PGA Tour"],
  ])("%s renders %s both before and after", (key, expected) => {
    expect(badge(served(key))).toBe(expected);
    expect(badge(fixed(key))).toBe(expected);
  });

  it("exactly ONE of the three banked tournaments changes", () => {
    const moved = Object.keys(FX.expected_after).filter(
      (k) => badge(served(k)) !== badge(fixed(k)),
    );
    expect(moved).toEqual([OMEGA]);
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 4 · THE GROUPING CONSUMER — the chip is also a section heading.          */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P181 · the /categories/golf section grouping", () => {
  // The page buckets with `const tour = t.tour || "other"` (page.tsx:250). The
  // grouping itself lives inside a Next.js route file and cannot be imported,
  // so this asserts the payload-level fact the grouping consumes rather than
  // re-implementing the grouping — a partial replication would count a
  // population the route never sees.
  const bucket = (t: GolfTournament) => t.tour || "other";

  it("before: the two DP World events land in DIFFERENT buckets", () => {
    expect(bucket(served(OMEGA))).not.toBe(bucket(served(HUSQVARNA)));
  });

  it("after: they land in the SAME bucket", () => {
    expect(bucket(fixed(OMEGA))).toBe(bucket(fixed(HUSQVARNA)));
    expect(bucket(fixed(OMEGA))).toBe("dp_world");
  });

  it("the Tour Championship stays in the pga bucket", () => {
    expect(bucket(fixed(TOUR_CHAMPIONSHIP))).toBe("pga");
  });
});

/* ═══════════════════════════════════════════════════════════════════════ */
/* 5 · THE HONEST FALLBACK — the precondition for the parked inversion.     */
/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P181 · what the card does with no tour at all", () => {
  // UX-P181 did NOT invert the backend's bare `return "pga"` default; the census
  // that would justify it is in the report. This pins the render side of that
  // decision so the next queue can invert without also having to prove the card
  // degrades safely.
  it('an unknown tour renders "⛳ Golf", not a blank chip', () => {
    const t = {
      ...served(OMEGA),
      tour: null,
      tour_label: null,
    } as unknown as GolfTournament;
    expect(badge(t)).toBe("Golf");
  });
});
