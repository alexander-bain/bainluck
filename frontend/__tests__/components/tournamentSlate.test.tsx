/**
 * THE SLATE GUARD — /tournaments/us-open Today tab (UX-P132).
 *
 * The slate is the half of this page that has live prices: the outright fields
 * have been dark for 8-32 days (#2199) while the match markets were captured
 * minutes ago. So unlike the boards, the LIVE path is the common one here — and
 * both directions are asserted, because a guard that only proves the cautious
 * case is satisfied by a component that is cautious about everything.
 *
 * These tests assert RENDERED MARKUP, not props. Three failures they exist to
 * catch, each measured rather than imagined:
 *
 * 1. **"Yes 54% / No 47%".** Match-market outcomes are literally named `Yes`
 *    and `No` in our database and nothing in our schema records which player
 *    `Yes` means. The register's `sides` map is what makes this print players;
 *    if it ever stopped being consulted, the page would still render — wrongly.
 *
 * 2. **A laundered incoherent pair.** Two independent binary quotes are not a
 *    distribution (gotcha #23). 0.90 + 0.60 renormalized is a tidy 60/40 with
 *    no referent, and it looks exactly like a real number.
 *
 * 3. **A move that does not equal the row's own two numbers.** The script is
 *    the opening price and the divergence is the move; computing one on a
 *    different basis than the other produces a "+4" that contradicts the
 *    figures printed beside it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentSlate from "@/components/tournament/TournamentSlate";
import {
  dayHeading,
  formatMove,
  formatSlateProbability,
  localDayKey,
  matchNarrative,
  moveDirection,
  orderedSides,
  slateGroups,
  slateNotice,
  slateRowIsPresentedAsLive,
  type SlateData,
  type SlateMatch,
  type SlateSide,
} from "@/lib/slate";

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "clara-burel",
    display_name: "Clara Burel",
    seed: null,
    country: null,
    role: "participant",
    probability: 0.72,
    opening_probability: 0.65,
    move: 0.07,
    raw_probability: 0.72,
    raw_opening_probability: 0.65,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

function match(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "womens-singles:clara-burel-vs-yexin-ma:2026-08-26",
    draw: "womens-singles",
    draw_label: "Women's Singles",
    round: "qualifying",
    scheduled_date: "2026-08-26T15:00:00+00:00",
    sides: [
      side(),
      side({
        entity_key: "yexin-ma",
        display_name: "Yexin Ma",
        probability: 0.28,
        opening_probability: 0.35,
        move: -0.07,
        raw_probability: 0.28,
        raw_opening_probability: 0.35,
      }),
    ],
    coherent: true,
    raw_sum: 1.0,
    opening_raw_sum: 1.0,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-08-26T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-08-26T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "clara-burel",
    has_moved: true,
    source_count: 1,
    ...overrides,
  };
}

function slate(overrides: Partial<SlateData> = {}): SlateData {
  return {
    matches: [match()],
    count: 1,
    incoherent: 0,
    dropped: {},
    price_state: "live",
    newest_observed_at: "2026-08-26T14:50:00+00:00",
    age_hours: 0.2,
    dark_after_hours: 48,
    ...overrides,
  };
}

const render = (data: SlateData) =>
  renderToStaticMarkup(<TournamentSlate slate={data} />);

// ---------------------------------------------------------------------------
// The slate prints players, never Yes/No
// ---------------------------------------------------------------------------

describe("player names, not Yes/No", () => {
  it("renders both players' names", () => {
    const html = render(slate());
    expect(html).toContain("Clara Burel");
    expect(html).toContain("Yexin Ma");
  });

  it("never renders a bare Yes or No as a side", () => {
    const html = render(slate());
    expect(html).not.toMatch(/>\s*Yes\s*</);
    expect(html).not.toMatch(/>\s*No\s*</);
  });

  it("orders the favourite first", () => {
    const ordered = orderedSides(match());
    expect(ordered?.[0].entity_key).toBe("clara-burel");
    const flipped = orderedSides(
      match({
        sides: [
          side({ probability: 0.28 }),
          side({ entity_key: "yexin-ma", display_name: "Yexin Ma", probability: 0.72 }),
        ],
        favourite: "yexin-ma",
      })
    );
    expect(flipped?.[0].entity_key).toBe("yexin-ma");
  });

  it("marks exactly one side as the favourite in the markup", () => {
    const html = render(slate());
    expect(html.match(/data-favourite="true"/g)).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Incoherent pairs are refused, not laundered
// ---------------------------------------------------------------------------

describe("independent binaries", () => {
  const incoherent = match({
    coherent: false,
    raw_sum: 1.5,
    probability_is_live: false,
    favourite: null,
    sides: [
      side({ probability: null, opening_probability: null, move: null }),
      side({
        entity_key: "yexin-ma",
        display_name: "Yexin Ma",
        probability: null,
        opening_probability: null,
        move: null,
      }),
    ],
  });

  it("orderedSides refuses to pick a favourite from a refused split", () => {
    expect(orderedSides(incoherent)).toBeNull();
  });

  it("still shows the match, because the match is still on", () => {
    const html = render(slate({ matches: [incoherent], incoherent: 1 }));
    expect(html).toContain("Clara Burel");
    expect(html).toContain("Yexin Ma");
    expect(html).toContain('data-coherent="false"');
  });

  it("shows no percentage at all rather than a normalized one", () => {
    const html = render(slate({ matches: [incoherent], incoherent: 1 }));
    expect(html).toContain("do not agree");
    expect(html).not.toMatch(/\d+%/);
  });

  it("counts the refusals so a thin slate is explainable", () => {
    const html = render(slate({ matches: [incoherent], incoherent: 1 }));
    expect(html).toContain("1 match has prices that do not agree");
  });
});

// ---------------------------------------------------------------------------
// The script vs the divergence
// ---------------------------------------------------------------------------

describe("script vs divergence", () => {
  it("prints the move beside the number it belongs to", () => {
    const html = render(slate());
    expect(html).toContain("+7");
    expect(html).toContain("−7");
    expect(html).toContain("72%");
    expect(html).toContain("28%");
  });

  it("narrates the opening price and where it went", () => {
    expect(matchNarrative(match())).toBe(
      "Clara Burel opened at 65%, up to 72%."
    );
  });

  it("says a flat match is flat rather than inventing a story", () => {
    const flat = match({
      has_moved: false,
      sides: [
        side({ probability: 0.65, opening_probability: 0.65, move: 0 }),
        side({
          entity_key: "yexin-ma",
          display_name: "Yexin Ma",
          probability: 0.35,
          opening_probability: 0.35,
          move: 0,
        }),
      ],
    });
    expect(matchNarrative(flat)).toBe("Clara Burel opened at 65% and has not moved.");
    expect(render(slate({ matches: [flat] }))).not.toContain("Moved");
  });

  it("refuses to narrate an incoherent pair", () => {
    expect(matchNarrative(match({ coherent: false }))).toBe(
      "Prices for this match do not agree yet."
    );
  });

  it("suppresses a sub-half-point move rather than printing +0", () => {
    expect(formatMove(0.004)).toBe("");
    expect(formatMove(0.006)).toBe("+1");
    expect(formatMove(null)).toBe("");
  });

  it("directions have a dead band", () => {
    expect(moveDirection(0.002)).toBe("flat");
    expect(moveDirection(0.02)).toBe("up");
    expect(moveDirection(-0.02)).toBe("down");
  });
});

// ---------------------------------------------------------------------------
// Honesty — the same treatment as the boards
// ---------------------------------------------------------------------------

describe("honesty treatment", () => {
  it("presents a live row in the live treatment", () => {
    const html = render(slate());
    expect(html).toContain('data-live="true"');
    expect(html).not.toContain("Prices paused");
  });

  it("never upgrades a row the server did not call live", () => {
    expect(slateRowIsPresentedAsLive(match({ probability_is_live: false }))).toBe(false);
    // Not talked into a yes by a fresh-looking price_state.
    expect(
      slateRowIsPresentedAsLive(
        match({ probability_is_live: false, price_state: "live", coherent: true })
      )
    ).toBe(false);
  });

  it("keeps the number but mutes it when stale", () => {
    const stale = match({ probability_is_live: false, price_state: "stale", age_hours: 30 });
    const html = render(slate({ matches: [stale], price_state: "stale", age_hours: 30 }));
    expect(html).toContain('data-live="false"');
    expect(html).toContain("72%"); // kept — discarding real information is its own failure
    expect(html).toContain("text-text-secondary");
  });

  // -------------------------------------------------------------------------
  // THE MIXED-AGE PAIR — `C-USOPEN-DAY3-TIER2` on the slate
  //
  // A slate row normalizes its two sides against each other, so a stale side is
  // not beside the published number, it is inside it. The pair below sums to
  // exactly 1.000 and sails through the coherence gate, which is the point:
  // coherence is not freshness.
  // -------------------------------------------------------------------------

  const MIXED_MATCH = match({
    probability_is_live: false,
    price_state: "dark",
    observed_at: "2026-08-06T15:00:00+00:00",
    age_hours: 20 * 24,
    freshest_observed_at: "2026-08-26T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: ["yexin-ma"],
    mixed_freshness: true,
    sides: [
      side(),
      side({
        entity_key: "yexin-ma",
        display_name: "Yexin Ma",
        probability: 0.28,
        opening_probability: 0.35,
        move: -0.07,
        raw_probability: 0.28,
        raw_opening_probability: 0.35,
        age_hours: 20 * 24,
        price_state: "dark",
      }),
    ],
  });

  it("mutes a pair whose second side is twenty days old", () => {
    const html = render(slate({ matches: [MIXED_MATCH] }));
    expect(html).toContain('data-live="false"');
    expect(html).toContain('data-coherent="true"'); // the pair still sums to 1
    expect(html).toContain("72%"); // and the number is still shown
  });

  it("names the stale side on the row, since the slate banner still reads live", () => {
    const html = render(slate({ matches: [MIXED_MATCH] }));
    // No banner — slate-level freshness is deliberately the NEWEST reading, so
    // the per-row admission is the only thing standing between the reader and
    // a silently greyed row.
    expect(html).not.toContain('data-testid="slate-notice"');
    expect(html).toContain('data-testid="slate-row-age"');
    expect(html).toContain("Yexin Ma 20 days ago");
  });

  it("does not label a live row at all", () => {
    const html = render(slate());
    expect(html).not.toContain('data-testid="slate-row-age"');
  });

  it("does not put an age on a row muted for DISAGREEMENT rather than age", () => {
    // An incoherent-but-fresh pair is muted for a different reason, and the
    // incoherent block already says so. An age here would name the wrong
    // problem, which is how a true label becomes a misleading one.
    const html = render(
      slate({
        matches: [
          match({
            coherent: false,
            probability_is_live: false,
            price_state: "live",
            favourite: null,
            sides: [
              side({ probability: null, opening_probability: null, move: null }),
              side({
                entity_key: "yexin-ma",
                display_name: "Yexin Ma",
                probability: null,
                opening_probability: null,
                move: null,
              }),
            ],
          }),
        ],
      })
    );
    expect(html).toContain('data-testid="slate-incoherent"');
    expect(html).not.toContain('data-testid="slate-row-age"');
  });

  it("says so in words when the slate is not live", () => {
    const html = render(slate({ price_state: "stale", age_hours: 30 }));
    expect(html).toContain("Prices paused");
    expect(html).toContain("not live prices");
  });

  it("distinguishes never-observed from merely stale", () => {
    const notice = slateNotice(
      slate({ price_state: "dark", newest_observed_at: null, age_hours: null })
    );
    expect(notice?.headline).toBe("No prices yet");
  });

  it("is silent when genuinely live", () => {
    expect(slateNotice(slate())).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Grouping and the empty state
// ---------------------------------------------------------------------------

describe("grouping", () => {
  it("buckets by local calendar day", () => {
    const groups = slateGroups(
      [
        match({ matchup_key: "a", scheduled_date: "2026-08-26T15:00:00+00:00" }),
        match({ matchup_key: "b", scheduled_date: "2026-08-27T15:00:00+00:00" }),
        match({ matchup_key: "c", scheduled_date: "2026-08-26T19:00:00+00:00" }),
      ],
      new Date("2026-08-26T12:00:00Z")
    );
    expect(groups).toHaveLength(2);
    expect(groups[0].matches.map((m) => m.matchup_key)).toEqual(["a", "c"]);
  });

  it("calls the reader's own today Today", () => {
    const now = new Date("2026-08-26T12:00:00Z");
    expect(dayHeading(localDayKey(now.toISOString()), now)).toBe("Today");
    const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    expect(dayHeading(localDayKey(tomorrow.toISOString()), now)).toBe("Tomorrow");
  });

  it("renders an honest empty state rather than nothing", () => {
    const html = render(slate({ matches: [], count: 0 }));
    expect(html).toContain("No matches scheduled");
    expect(html).not.toMatch(/\d+%/);
  });
});

describe("formatting", () => {
  it("renders a missing probability as a dash, never as zero", () => {
    expect(formatSlateProbability(null)).toBe("—");
    expect(formatSlateProbability(0)).toBe("0%");
    expect(formatSlateProbability(0.725)).toBe("73%");
  });
});
