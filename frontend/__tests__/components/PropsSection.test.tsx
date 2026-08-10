// L2-118 Phase 1: the archetype-agnostic props body — THE SCRIPT / THE
// DIVERGENCE / WHAT HIT. Phase-1 honesty: the pregame-mark + graded fields ship
// with #195; until then the section renders an explicit "pending" line behind the
// same interface (never a fabricated number). Phase 2 is a payload swap.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection, { deriveState } from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import { SETTLED_NO_GRADE_LABEL } from "../../lib/propGrade";

const ITEMS: PropMark[] = [
  { key: 1, label: "LeBron 25+ points", pregame_mark: 0.6, current: 0.72, graded_result: "hit" },
  { key: 2, label: "Under 220.5 total", pregame_mark: 0.5, current: 0.41, graded_result: "miss" },
];

describe("deriveState (settled-means-settled)", () => {
  test("upcoming → script", () => {
    expect(deriveState("scheduled")).toBe("script");
    expect(deriveState(undefined)).toBe("script");
  });
  test("live → divergence", () => {
    expect(deriveState("live")).toBe("divergence");
    expect(deriveState("in_progress")).toBe("divergence");
  });
  test("settled → graded", () => {
    expect(deriveState("completed")).toBe("graded");
    expect(deriveState("closed")).toBe("graded");
    expect(deriveState("final")).toBe("graded");
  });
});

describe("PropsSection rendering", () => {
  test("THE SCRIPT shows pregame marks when present", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="script" />);
    expect(html).toContain("The script");
    expect(html).toContain("LeBron 25+ points");
    expect(html).toContain("60%"); // pregame_mark
  });

  test("THE DIVERGENCE shows pregame → current with a signed delta", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="divergence" />);
    expect(html).toContain("The divergence");
    expect(html).toContain("72%"); // current
    expect(html).toContain("↑ 12"); // +12 pts, up = accent-brand
    expect(html).toContain("↓ 9"); // -9 pts, down = accent-danger
    expect(html).toContain("text-accent-danger");
  });

  test("WHAT HIT shows graded results", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="graded" />);
    expect(html).toContain("What hit");
    expect(html).toContain("Hit");
    expect(html).toContain("Miss");
  });

  test("honest 'pending' placeholder when #195 fields are null (no fabricated number)", () => {
    const pending: PropMark[] = [
      { key: 9, label: "Anytime TD", pregame_mark: null, current: 0.44, graded_result: null },
    ];
    const script = renderToStaticMarkup(<PropsSection items={pending} state="script" />);
    expect(script).toContain("pregame mark pending");
    const graded = renderToStaticMarkup(<PropsSection items={pending} state="graded" />);
    // UX-P044 (#1650): this asserted "grading pending" — the SECOND of the three
    // vocabularies one settled state wore on one screen. It is now the same
    // phrase the Player Props card uses, imported from the module that decides.
    expect(graded).toContain(SETTLED_NO_GRADE_LABEL);
    expect(graded).not.toContain("grading pending");
  });

  // #1650: the header claimed a fourth thing — "The pregame script, graded." over
  // a list where nothing was graded.
  test("the graded blurb does not claim 'graded' over an ungraded list", () => {
    const ungraded: PropMark[] = [
      { key: 9, label: "Anytime TD", pregame_mark: null, current: 0.44, graded_result: null },
    ];
    const html = renderToStaticMarkup(<PropsSection items={ungraded} state="graded" />);
    expect(html).toContain("What hit"); // the section keeps its name
    expect(html).not.toContain("The pregame script, graded.");
    expect(html).toContain("No grades published");
  });

  // Both directions (gotcha #43): one real grade and the claim is true again.
  test("the graded blurb DOES claim graded when something on the list is", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="graded" />);
    expect(html).toContain("The pregame script, graded.");
  });

  test("L2-123: pending_label renders the honest state, never a fabricated flat", () => {
    // A degenerate (no-price) family — the #199 wide-spread/no-trade class. It must
    // show the honest label in EVERY state, never the fake number, never blank.
    const degenerate: PropMark[] = [
      { key: 7, label: "Round 2 Leader", pregame_mark: null, current: null, pending_label: "Opens after Round 1" },
    ];
    for (const state of ["script", "divergence", "graded"] as const) {
      const html = renderToStaticMarkup(<PropsSection items={degenerate} state={state} />);
      expect(html).toContain("Round 2 Leader");
      expect(html).toContain("Opens after Round 1");
      // Never the fabricated flat, never a bare em-dash value, never the #195 seams.
      expect(html).not.toContain("24%");
      expect(html).not.toContain("pregame mark pending");
      expect(html).not.toContain("script pending");
    }
  });

  test("L2-123: pending_label wins even if a stray current sneaks through", () => {
    // Defense in depth: if the store still holds a fabricated flat, the pending
    // label suppresses it rather than rendering the lie.
    const items: PropMark[] = [
      { key: 8, label: "Top 5 Finish", pregame_mark: null, current: 0.011, pending_label: "No market yet" },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).toContain("No market yet");
    expect(html).not.toContain("1%");
  });

  test("derives state from eventStatus when state omitted", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} eventStatus="completed" />);
    expect(html).toContain("What hit");
  });

  test("The Open 2026 p0: a settled mark renders graded even while the section is live", () => {
    // A completed round on a still-live tournament. The whole section is in the
    // DIVERGENCE (live) state, but this individual mark is settled → it must show
    // WHAT HIT (the graded leader), NEVER a live number for a concluded round.
    const items: PropMark[] = [
      { key: 1, label: "Round 1 Leader: Jackson Suber", pregame_mark: null, current: null,
        graded_result: "hit", graded_label: "Jackson Suber led", settled: true },
      // A genuinely live sibling in the same live section still diverges.
      { key: 2, label: "Playoff", pregame_mark: 0.28, current: 0.2, settled: false },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).toContain("Jackson Suber led"); // graded, not live
    expect(html).not.toContain("grading pending"); // it IS graded, not a #195 seam
    // The live sibling still shows its divergence number — the override is per-mark.
    expect(html).toContain("20%");
  });

  test("The Open 2026 p0: a settled mark never shows live odds even with a stray current", () => {
    // Defense in depth: a completed round must not leak a live probability.
    const items: PropMark[] = [
      { key: 3, label: "Round 3 Leader: Sam Burns", pregame_mark: 0.05, current: 0.99,
        graded_result: "hit", graded_label: "Sam Burns led", settled: true },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).toContain("Sam Burns led");
    expect(html).not.toContain("99%"); // no live number for a settled round
    expect(html).not.toContain("→"); // no divergence arrow
  });

  // L2-147 Item 2: a named field card (e.g. "Top American Golfer") carries a
  // Wikipedia headshot next to each competitor for a person-field domain (golf) —
  // Alex: "I'm not seeing golfer images on the Props section." SSR renders the
  // initials chip (no network); "SS" for Scottie Scheffler proves the avatar slot
  // mounted (his name has no "SS" substring).
  const golferField: PropMark[] = [
    {
      key: 1,
      label: "Top American Golfer",
      question: "Top American Golfer",
      kind: "field",
      pregame_mark: null,
      current: null,
      outcomes: [
        { name: "Scottie Scheffler", probability: 0.42 },
        { name: "Xander Schauffele", probability: 0.18 },
      ],
    },
  ];

  test("field card carries golfer headshots for a person-field domain (golf)", () => {
    const html = renderToStaticMarkup(
      <PropsSection items={golferField} state="divergence" domain="golf" />,
    );
    expect(html).toContain("Scottie Scheffler"); // name still shown
    expect(html).toContain("SS"); // initials avatar (SSR fallback) mounted
    expect(html).toContain("XS"); // Xander Schauffele avatar
  });

  test("no headshots without a person-field domain (unchanged text-only render)", () => {
    const html = renderToStaticMarkup(
      <PropsSection items={golferField} state="divergence" />,
    );
    expect(html).toContain("Scottie Scheffler");
    expect(html).not.toContain("SS"); // no avatar chip when domain is absent
  });

  test("empty items render nothing", () => {
    expect(renderToStaticMarkup(<PropsSection items={[]} />)).toBe("");
  });

  test("never renders american_odds / moneyline", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="divergence" />);
    expect(html).not.toContain("american_odds");
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });
});

describe("THE DIVERGENCE ranking (biggest mover first)", () => {
  const UNSORTED: PropMark[] = [
    { key: "small", label: "Small mover", pregame_mark: 0.5, current: 0.52 }, // 2
    { key: "big", label: "Big mover", pregame_mark: 0.4, current: 0.72 }, // 32
    { key: "mid", label: "Mid mover", pregame_mark: 0.5, current: 0.62 }, // 12
  ];

  test("divergence sorts by absolute movement, biggest first", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNSORTED} state="divergence" />);
    const iBig = html.indexOf("Big mover");
    const iMid = html.indexOf("Mid mover");
    const iSmall = html.indexOf("Small mover");
    expect(iBig).toBeGreaterThanOrEqual(0);
    expect(iBig).toBeLessThan(iMid);
    expect(iMid).toBeLessThan(iSmall);
  });

  test("rows with no computable movement sink below movers, keeping order", () => {
    const withNulls: PropMark[] = [
      { key: "pending-a", label: "Pending A", pregame_mark: null, current: 0.5 },
      { key: "mover", label: "Real mover", pregame_mark: 0.4, current: 0.6 }, // 20
      { key: "pending-b", label: "Pending B", pregame_mark: 0.5, current: null },
    ];
    const html = renderToStaticMarkup(<PropsSection items={withNulls} state="divergence" />);
    const iMover = html.indexOf("Real mover");
    const iA = html.indexOf("Pending A");
    const iB = html.indexOf("Pending B");
    expect(iMover).toBeLessThan(iA); // movers rank above null-movement rows
    expect(iA).toBeLessThan(iB); // null rows keep original relative order (stable)
  });

  test("SCRIPT state preserves payload order (no divergence re-rank)", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNSORTED} state="script" />);
    const iSmall = html.indexOf("Small mover");
    const iBig = html.indexOf("Big mover");
    expect(iSmall).toBeLessThan(iBig); // original order intact
  });
});

// ---------------------------------------------------------------------------
// UX-P036 (gap K14) — "the divergence section is unintelligible".
//
// Measured on production 2026-08-09, Athletics @ Red Sox (live, the game Alex
// ran the preference test on): props_script carried 81 marks, 73 of which named
// no statistic ("Tommy White: 4+" — 4+ WHAT?), 36 of which read "±0", and three
// families were interleaved into one flat list. The statistic was on the wire
// the whole time, in the key.
// ---------------------------------------------------------------------------

describe("UX-P036: prop families and the unchanged-row drawer", () => {
  // The production shape, in miniature: `market_name|outcome_name` keys, a
  // matchup prefix shared by every family, movers and non-movers mixed.
  const GAME_PROPS: PropMark[] = [
    { key: "Boston vs A's: Hits + Runs + RBIs|Tommy White: 4+", label: "Tommy White: 4+", pregame_mark: 0.84, current: 0.23 },
    { key: "Boston vs A's: Hits + Runs + RBIs|Carlos Cortes: 3+", label: "Carlos Cortes: 3+", pregame_mark: 0.84, current: 0.84 },
    { key: "Boston vs A's: Hits|Jacob Wilson: 2+", label: "Jacob Wilson: 2+", pregame_mark: 0.05, current: 0.41 },
    { key: "Boston vs A's: Hits|Anthony Seigler: 2+", label: "Anthony Seigler: 2+", pregame_mark: 0.5, current: 0.5 },
    { key: "Boston vs A's: Home Runs|Nick Sogard: 1+", label: "Nick Sogard: 1+", pregame_mark: 0.1, current: 0.1 },
  ];

  test("the statistic a row measures is finally on screen, as a family header", () => {
    const html = renderToStaticMarkup(<PropsSection items={GAME_PROPS} state="divergence" />);
    // The three families, with the redundant matchup prefix stripped.
    expect(html).toContain("Hits + Runs + RBIs");
    expect(html).toContain("Home Runs");
    expect(html).not.toContain("Boston vs A&#x27;s: Hits"); // prefix gone from headers
    // And the ambiguous row now sits UNDER its statistic.
    expect(html.indexOf("Hits + Runs + RBIs")).toBeLessThan(html.indexOf("Tommy White: 4+"));
  });

  test("families appear biggest-mover-first (ranking survives grouping)", () => {
    const html = renderToStaticMarkup(<PropsSection items={GAME_PROPS} state="divergence" />);
    // Tommy White moved 61 pts, Jacob Wilson 36, Nick Sogard 0.
    expect(html.indexOf("Hits + Runs + RBIs")).toBeLessThan(html.indexOf("Home Runs"));
    expect(html.indexOf("Tommy White: 4+")).toBeLessThan(html.indexOf("Jacob Wilson: 2+"));
  });

  test("BOTH DIRECTIONS: unchanged rows leave the list but stay reachable", () => {
    const html = renderToStaticMarkup(<PropsSection items={GAME_PROPS} state="divergence" />);

    // Direction 1 — the wall collapses: every ±0 row is inside a <details>, and
    // the drawer states its own count rather than hiding silently.
    expect(html).toContain("1 unchanged");
    const firstDetails = html.indexOf("<details");
    expect(firstDetails).toBeGreaterThan(-1);
    expect(html.indexOf("Carlos Cortes: 3+")).toBeGreaterThan(firstDetails);
    // The movers are NOT in a drawer — they render above the first one.
    expect(html.indexOf("Tommy White: 4+")).toBeLessThan(firstDetails);

    // Direction 2 — nothing is deleted (gotcha #43): all five marks still render.
    for (const item of GAME_PROPS) expect(html).toContain(item.label);
  });

  test("a mark missing an endpoint is NOT 'unchanged' — it stays in plain sight", () => {
    // Zero movement means measured-and-flat. A null endpoint is a pending chip,
    // and burying it in the drawer would hide an honest gap.
    const items: PropMark[] = [
      { key: "M: Hits|mover", label: "Real mover", pregame_mark: 0.4, current: 0.6 },
      { key: "M: Hits|pending", label: "Pending row", pregame_mark: null, current: 0.5 },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).not.toContain("unchanged");
    expect(html).not.toContain("<details");
    expect(html).toContain("script pending");
  });

  test("THE SCRIPT and WHAT HIT group but never collapse (no movement notion)", () => {
    for (const state of ["script", "graded"] as const) {
      const html = renderToStaticMarkup(<PropsSection items={GAME_PROPS} state={state} />);
      expect(html).toContain("Hits + Runs + RBIs"); // still grouped
      expect(html).not.toContain("unchanged"); // but nothing is folded away
      expect(html).not.toContain("<details");
      for (const item of GAME_PROPS) expect(html).toContain(item.label);
    }
  });

  test("a single family keeps its full name (sharedness is the only strip evidence)", () => {
    const items: PropMark[] = [
      { key: "Best Picture: Winner|Nominee A", label: "Nominee A", pregame_mark: 0.3, current: 0.5 },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).toContain("Best Picture: Winner"); // NOT cut down to "Winner"
  });

  test("DEGRADED PATH: numeric keys render exactly as before — no headers, no drawer", () => {
    // The golf/combat concept page builds marks with `key: mid`. A regression
    // here breaks The Open's props section, so it is pinned explicitly.
    const golfShape: PropMark[] = [
      { key: 101, label: "Playoff", pregame_mark: 0.28, current: 0.28 },
      { key: 102, label: "Top 10 Finish", pregame_mark: 0.4, current: 0.6 },
    ];
    const html = renderToStaticMarkup(<PropsSection items={golfShape} state="divergence" />);
    expect(html).not.toContain("<details"); // a ±0 row is NOT collapsed here
    expect(html).not.toContain("unchanged");
    expect(html).toContain("Playoff");
    expect(html).toContain("Top 10 Finish");
    // Byte-identical to the pre-grouping markup: rows sit directly in the
    // original `space-y-2` list, with no family wrapper around them.
    expect(html).not.toContain("space-y-4");
  });

  test("scale: all 81 marks of the measured payload survive the render", () => {
    const many: PropMark[] = Array.from({ length: 81 }, (_, i) => ({
      key: `Boston vs A's: F${i % 3}|Player ${i}: 2+`,
      label: `Player ${i}: 2+`,
      pregame_mark: 0.5,
      // 36 of 81 flat, mirroring the production ratio.
      current: i % 9 < 4 ? 0.5 : 0.5 + (i % 5 + 1) / 100,
    }));
    const html = renderToStaticMarkup(<PropsSection items={many} state="divergence" />);
    for (let i = 0; i < 81; i += 1) expect(html).toContain(`Player ${i}: 2+`);
  });
});
