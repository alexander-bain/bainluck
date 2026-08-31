/**
 * SETTLED MEANS SETTLED, ON A PROP CARD — UX-P207.
 *
 * TOP-PRODUCT-DEFECTS item 6 (Alex, 2026-08-30): *"Will Sinner actually play?"
 * still a live question after play began — time-bounded props need settled
 * rendering.*
 *
 * THE SPECIMEN, from `GET /api/tournaments/us-open` at 2026-08-31T00:58Z — ten
 * hours after the main draw started and after the fixture had been played:
 *
 *     key=sinner-competes  title="Will Sinner actually play?"
 *     price_state=live     probability_is_live=true
 *     probability=0.01     age_hours=0.34   answer_entity_key=sinner-competes:yes
 *
 * So the card rendered in the confident treatment, with a fresh chip, printing
 * **1%** as the current answer to a question that no longer had one.
 *
 * THE SPLIT. Deciding that a question has closed needs the schedule and the
 * results, and belongs where the register is written (lane1's rule adds
 * `settled` / `settled_answer` / `settled_at`). This file owns the other half —
 * what a settled card LOOKS like — and every assertion is against the RENDER,
 * because a pure-layer test stays green the day the component stops printing it
 * (`reference_plant_must_hit_the_render`).
 *
 * ⚠️ THE SHIP IS LATENT UNTIL THE REGISTER EMITS THE FIELD, and that is said
 * out loud rather than implied: the last two tests here pin the fail-safe, so a
 * payload without `settled` renders exactly as it did the day before.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentProps from "@/components/tournament/TournamentProps";
import {
  propIsPresentedAsLive,
  propSettlement,
  type PropMarket,
} from "@/lib/tournamentProps";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);

/** `sinner-competes` as production served it, minus the settlement fields. */
function sinnerCompetes(overrides: Partial<PropMarket> = {}): PropMarket {
  return {
    key: "sinner-competes",
    title: "Will Sinner actually play?",
    hook: "A withdrawal reshapes the entire men's board.",
    draw: "mens-singles",
    source: "kalshi",
    legs: 1,
    unpriced_legs: [],
    outcomes: [
      {
        entity_key: "sinner-competes:yes",
        display_name: "Yes",
        probability: 0.01,
        probability_is_live: true,
        observed_at: "2026-08-31T00:58:18.923119+00:00",
        age_hours: 0.34,
        price_state: "live",
        is_answer: true,
      },
    ],
    answer_entity_key: "sinner-competes:yes",
    price_state: "live",
    observed_at: "2026-08-31T00:58:18.923119+00:00",
    age_hours: 0.34,
    freshest_observed_at: "2026-08-31T00:58:18.923119+00:00",
    freshest_age_hours: 0.34,
    stale_outcomes: [],
    mixed_freshness: false,
    ...overrides,
  };
}

/** The same card once the register has ruled the window closed. */
const SETTLED = {
  settled: true,
  settled_answer: "No",
  settled_at: "2026-08-30T15:00:00+00:00",
};

describe("UX-P207 — a settled prop card shows a result, not a price", () => {
  it("REPRODUCES the defect on the payload Alex read", () => {
    // Everything below is a change to THIS render, so it is worth pinning what
    // it is a change from: a live-treatment card whose headline is 1%.
    const html = render(
      <TournamentProps markets={[sinnerCompetes()]} draw="mens-singles" />
    );
    expect(html).toContain('data-live="true"');
    expect(html).toContain('data-settled="false"');
    expect(html).toContain('data-testid="prop-probability"');
    expect(html).toContain("1%");
  });

  it("prints the RESULT in the headline slot, and no probability there", () => {
    const html = render(
      <TournamentProps markets={[sinnerCompetes(SETTLED)]} draw="mens-singles" />
    );
    expect(html).toContain('data-settled="true"');
    expect(html).toContain('data-testid="prop-settled-answer"');
    expect(html).toContain(">No</span>");
    // Ruling 2: a settled card shows a result. The probability must not be the
    // thing the eye lands on any more.
    expect(html).not.toContain('data-testid="prop-probability"');
  });

  it("is never LIVE, however fresh the quote behind it is", () => {
    // The market really was quoted twenty minutes earlier. A live QUOTE on a
    // closed question is not a live ANSWER, and this is the rule every surface
    // reads — so the section banner and the stale list follow it too.
    const settled = sinnerCompetes(SETTLED);
    expect(propIsPresentedAsLive(sinnerCompetes())).toBe(true);
    expect(propIsPresentedAsLive(settled)).toBe(false);
    const html = render(<TournamentProps markets={[settled]} draw="mens-singles" />);
    expect(html).toContain('data-live="false"');
  });

  it("drops the age chip, which was answering the wrong question at 0.3h", () => {
    const html = render(
      <TournamentProps markets={[sinnerCompetes(SETTLED)]} draw="mens-singles" />
    );
    expect(html).not.toContain('data-testid="prop-age"');
    // …and the liquidity mark with it — "thin book" is advice about a trade
    // nobody can make any more.
    expect(html).not.toContain('data-testid="liquidity-mark"');
  });

  it("KEEPS the last reading, demoted and labelled as the last one", () => {
    // Deleting it throws away a true fact. Printing it in the headline makes a
    // finished question look open. It goes in the muted line, named.
    const html = render(
      <TournamentProps markets={[sinnerCompetes(SETTLED)]} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="prop-settled"');
    expect(html).toContain('data-testid="prop-settled-last"');
    expect(html).toContain("last reading");
    expect(html).toContain("1%");
    // The muted line, not the 17px headline: the only 1% on the card sits after
    // the words "last reading".
    const headline = html.indexOf('data-testid="prop-settled-answer"');
    expect(html.indexOf("last reading")).toBeGreaterThan(headline);
  });

  it("says so plainly when the register knows THAT it closed but not HOW", () => {
    // `settled` with no answer is a real state, not a broken payload — a
    // schedule rule can know the window has passed before the result lands.
    // Inventing "No" here would be the guess the whole split exists to prevent.
    const html = render(
      <TournamentProps
        markets={[sinnerCompetes({ settled: true, settled_at: SETTLED.settled_at })]}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-settled="true"');
    expect(html).toContain('data-testid="prop-settled-unknown"');
    expect(html).toContain("result not published");
    expect(html).not.toContain('data-testid="prop-settled-answer"');
    // The card is still not live, and still not printing a headline price.
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-testid="prop-probability"');
  });

  it("reads only an EXPLICIT true — a truthy value is an open question", () => {
    // A payload that grows `settled: "yes"` should render OPEN and be caught
    // here, rather than silently flipping every card into the settled
    // treatment. Cast because the type says boolean and the wire does not.
    expect(propSettlement(sinnerCompetes())).toBeNull();
    expect(propSettlement(sinnerCompetes({ settled: false }))).toBeNull();
    expect(propSettlement(sinnerCompetes({ settled: null }))).toBeNull();
    const loose = sinnerCompetes({ settled: "yes" as unknown as boolean });
    expect(propSettlement(loose)).toBeNull();
    expect(render(<TournamentProps markets={[loose]} draw="mens-singles" />))
      .toContain('data-settled="false"');
  });

  it("blank and whitespace answers read as NOT PUBLISHED, not as a blank result", () => {
    for (const settled_answer of ["", "   "]) {
      expect(propSettlement(sinnerCompetes({ settled: true, settled_answer })))
        .toEqual({ answer: null, at: null });
    }
    expect(propSettlement(sinnerCompetes(SETTLED)))
      .toEqual({ answer: "No", at: "2026-08-30T15:00:00+00:00" });
  });

  it("FAIL-SAFE: a payload with no settlement fields renders as it always did", () => {
    // The ship is latent until lane1's register rule emits the field, so the
    // most important property in this file is that nothing changes before then.
    const html = render(
      <TournamentProps markets={[sinnerCompetes()]} draw="mens-singles" />
    );
    expect(html).toContain('data-settled="false"');
    expect(html).toContain('data-testid="prop-probability"');
    expect(html).toContain('data-testid="prop-answer"');
    expect(html).not.toContain('data-testid="prop-settled"');
    expect(html).not.toContain("Settled");
  });

  it("does not disturb the OTHER cards on the page", () => {
    // One settled card among open ones must not settle the section.
    const open = sinnerCompetes({
      key: "usa-men-final-berth",
      title: "Will an American reach the men's final?",
      answer_entity_key: "usa:yes",
      outcomes: [
        {
          entity_key: "usa:yes", display_name: "Yes", probability: 0.395,
          probability_is_live: true, observed_at: "2026-08-31T00:58:18+00:00",
          age_hours: 0.34, price_state: "live", is_answer: true,
        },
      ],
    });
    const html = render(
      <TournamentProps
        markets={[sinnerCompetes(SETTLED), open]}
        draw="mens-singles"
      />
    );
    expect((html.match(/data-settled="true"/g) ?? []).length).toBe(1);
    expect((html.match(/data-settled="false"/g) ?? []).length).toBe(1);
    expect(html).toContain("40%");
    expect(html).toContain(">No</span>");
  });
});
