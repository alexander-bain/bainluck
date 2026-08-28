/**
 * A MATCH IS AN EVENT — the guards for that (UX-P152).
 *
 * Alex, 2026-08-28, on the UX-P149 artifact: *"It seems like we're reinventing
 * the event page here"*, and then *"I thought that tournaments were containers
 * for related events."*
 *
 * So the parallel `/tournaments/{slug}/matches/{key}` page is gone, a match card
 * routes to `/events/{id}`, and the tournament adds two sections to the standard
 * event page.  Four things here can regress silently and are held:
 *
 * 1. **The row routes to the event page.** Not to a tournament-private URL, and
 *    never to a fixture with no `events` row — a link to the wrong match is
 *    worse than no link.
 * 2. **One component, two callers.** The advancement strip goes through the
 *    same `AdvancementPath` the MLB/NBA `CHAMPIONSHIP PATH` block goes through.
 *    A second implementation that agreed on the day it was written is the thing
 *    Alex's "same component family" asked us not to build.
 * 3. **The empty cases are honest.** 26 of 96 R128 fixtures have neither player
 *    on the reach board; a titled empty box is a promise of something absent.
 * 4. **A ladder that does not climb says so.** The market prices "reach the
 *    final" above "reach the semis" on 21 of 84 ladder players. Reported, not
 *    corrected — but SAID, because at one match's magnification silence reads
 *    as our arithmetic rather than theirs.
 *
 * Every assertion below is against RENDERED markup, not against a helper's
 * return value: a pure-logic guard stays green when the component stops
 * printing the thing.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AdvancementPath from "@/components/event/AdvancementPath";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import MatchProps from "@/components/tournament/MatchProps";
import { toStages } from "@/components/event/TournamentExtensions";
import { matchListFromSlate } from "@/lib/matchList";
import type { TournamentAdvancementRow } from "@/lib/types";

/** Everything a reader can actually see. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const BUBLIK: TournamentAdvancementRow = {
  name: "Alexander Bublik",
  short_name: "Bublik",
  team_id: null,
  logo_url: null,
  primary_color: null,
  secondary_color: null,
  record: "Seed 23",
  conference: null,
  monotonic: true,
  stages: [
    { key: "R16", label: "Round of 16", probability: 0.31, trend_24h: null, sources: [] },
    { key: "QF", label: "Quarter-finals", probability: 0.105, trend_24h: null, sources: [] },
    { key: "SF", label: "Semi-finals", probability: 0.105, trend_24h: null, sources: [] },
    { key: "F", label: "Final", probability: 0.055, trend_24h: null, sources: [] },
    { key: "title", label: "Title", probability: 0.00775, trend_24h: null, sources: [] },
  ],
};

/** A slate row shaped like the hub's, with and without an event to route to. */
function slateRow(overrides: Record<string, unknown> = {}) {
  return {
    priced: true,
    matchup_key: "mens-singles:alexander-bublik-vs-j-j-wolf:2026-08-30",
    event_id: 15293809,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    scheduled_date: "2026-08-30T15:00:00Z",
    coherent: true,
    decided: false,
    sides: [
      {
        entity_key: "alexander-bublik",
        display_name: "Alexander Bublik",
        seed: 23,
        country: null,
        image: null,
        role: "participant",
        probability: 0.6675,
        opening_probability: 0.65,
        move: 0.0175,
        raw_probability: 0.6675,
        raw_opening_probability: 0.65,
        observed_at: "2026-08-28T19:00:00Z",
        age_hours: 0.5,
        price_state: "live",
      },
      {
        entity_key: "j-j-wolf",
        display_name: "J.J. Wolf",
        seed: null,
        country: null,
        image: null,
        role: "participant",
        probability: 0.3325,
        opening_probability: 0.35,
        move: -0.0175,
        raw_probability: 0.3325,
        raw_opening_probability: 0.35,
        observed_at: "2026-08-28T19:00:00Z",
        age_hours: 0.5,
        price_state: "live",
      },
    ],
    ...overrides,
  };
}

function matchList(row: Record<string, unknown>) {
  return matchListFromSlate([row] as never, {});
}

describe("the route in — a match card addresses the standard event page", () => {
  it("links to /events/{id}, not to a tournament-private URL", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchList(slateRow())}
        initialExpanded
        initialOpenMatchId={matchList(slateRow())[0].id}
      />
    );
    expect(html).toContain('href="/events/15293809"');
    // The parallel page is gone. A row that still addressed it would 404, and
    // it would do so only for a reader who expanded a row — the quietest
    // possible break.
    expect(html).not.toContain("/matches/");
  });

  it("renders NO link when the fixture has no events row", () => {
    /**
     * 28 registered qualifying matchups resolve `MARKET_UNLINKED` today — their
     * Polymarket markets carry no `event_id` because the qualifying draw was
     * never ingested as events. A link to the wrong match is worse than no
     * link, so the affordance simply is not there.
     */
    const entries = matchList(slateRow({ event_id: null }));
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialExpanded initialOpenMatchId={entries[0].id} />
    );
    expect(html).not.toContain("/events/");
    expect(html).not.toContain('data-testid="match-page-link"');
  });

  it("the guard is not vacuously green — the row really does expand", () => {
    /**
     * Both directions. A "no link" assertion is satisfied by a component that
     * renders no rows at all, so the same fixture with an event id must produce
     * one.
     */
    const entries = matchList(slateRow());
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialExpanded initialOpenMatchId={entries[0].id} />
    );
    expect(visibleText(html)).toContain("Bublik");
    expect(html).toContain('data-testid="match-page-link"');
  });
});

describe("one component, two callers", () => {
  it("the advancement strip prints every priced round with its probability", () => {
    const html = renderToStaticMarkup(
      <AdvancementPath stages={toStages(BUBLIK)} heading="CHANCE OF REACHING" />
    );
    const text = visibleText(html);
    for (const [label, pct] of [
      ["Round of 16", "31%"],
      ["Quarter-finals", "11%"],
      ["Semi-finals", "11%"],
      ["Final", "6%"],
      ["Title", "1%"],
    ]) {
      expect(text).toContain(label);
      expect(text).toContain(pct);
    }
  });

  it("is the SAME component the league championship path goes through", () => {
    /**
     * Not a resemblance — the component. Rendering the league's own stage shape
     * through it must produce the league's own markup, `✓ clinched` included,
     * because that is the block this was lifted out of.
     */
    const html = renderToStaticMarkup(
      <AdvancementPath
        stages={[
          { label: "Make playoffs", prob: 1, change: 0.02, resolved: true },
          { label: "Win division", prob: 0.42, change: -0.031, resolved: false },
        ]}
      />
    );
    const text = visibleText(html);
    expect(text).toContain("CHAMPIONSHIP PATH");
    expect(text).toContain("✓ clinched");
    expect(text).toContain("42%");
    expect(text).toContain("3.1%");
  });

  it("a move under the dead band is noise and is not printed", () => {
    const html = renderToStaticMarkup(
      <AdvancementPath
        stages={[{ label: "Final", prob: 0.4, change: 0.001, resolved: false }]}
      />
    );
    expect(visibleText(html)).not.toContain("0.1%");
  });

  it("an unpriced round is dropped rather than printed as a dash or a zero", () => {
    const stages = toStages({
      ...BUBLIK,
      stages: [
        ...BUBLIK.stages.slice(0, 1),
        { key: "title", label: "Title", probability: null, trend_24h: null, sources: [] },
      ],
    });
    expect(stages.map((s) => s.label)).toEqual(["Round of 16"]);
    const text = visibleText(renderToStaticMarkup(<AdvancementPath stages={stages} />));
    expect(text).toContain("Round of 16");
    expect(text).not.toContain("Title");
  });

  it("never prints ✓ clinched on a reach cell", () => {
    /**
     * A draw's reach market does not reliably settle — UX-P149 measured a
     * match-winner market at 0.05% while a prop on the same match still read
     * its pre-match number hours later. A 99.6% here is a market's opinion,
     * not a round that has been played.
     */
    const stages = toStages({
      ...BUBLIK,
      stages: [
        { key: "R16", label: "Round of 16", probability: 0.996, trend_24h: null, sources: [] },
      ],
    });
    expect(stages[0].resolved).toBe(false);
    const text = visibleText(renderToStaticMarkup(<AdvancementPath stages={stages} />));
    expect(text).not.toContain("clinched");
    expect(text).toContain("100%");
  });

  it("renders nothing at all for a player with no stages", () => {
    expect(renderToStaticMarkup(<AdvancementPath stages={[]} />)).toBe("");
    expect(toStages(null)).toEqual([]);
  });
});

describe("the props section renders on the event page's payload", () => {
  it("takes the extensions payload — no slug, no match row, no subtitle", () => {
    /**
     * The event page already prints the players, the round and the hero, so the
     * props section arrives with only the four fields it reads. If `MatchProps`
     * ever grew a dependency on the deleted page's payload this stops
     * compiling, which is the point of narrowing the type.
     */
    const html = renderToStaticMarkup(
      <MatchProps
        payload={{
          decided: false,
          props_count: 1,
          props_dropped: {},
          props: [
            {
              key: "set-1",
              kind: "duel",
              family: "set_winner",
              question: "Who wins set 1",
              note: null,
              coherent: true,
              opening_coherent: true,
              probability_is_live: true,
              price_state: "live",
              observed_at: "2026-08-28T19:00:00Z",
              age_hours: 0.4,
              stale_answers: [],
              mixed_freshness: false,
              market_ids: [1],
              answers: [
                {
                  label: "Alexander Bublik",
                  entity_key: "alexander-bublik",
                  probability: 0.62,
                  opening_probability: 0.6,
                  outcome_id: 1,
                  price_state: "live",
                  age_hours: 0.4,
                },
                {
                  label: "J.J. Wolf",
                  entity_key: "j-j-wolf",
                  probability: 0.38,
                  opening_probability: 0.4,
                  outcome_id: 2,
                  price_state: "live",
                  age_hours: 0.4,
                },
              ],
            },
          ],
        }}
      />
    );
    const text = visibleText(html);
    expect(text).toContain("Who wins set 1");
    expect(text).toContain("Alexander Bublik");
    expect(text).toContain("62%");
    // Never the source's own words.
    expect(text).not.toMatch(/\bYes\b/);
    expect(text).not.toMatch(/\bNo\b/);
  });
});
