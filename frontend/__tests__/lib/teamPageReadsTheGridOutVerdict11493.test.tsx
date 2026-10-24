/**
 * #11493 — AN ELIMINATED TEAM'S PAGE READS AS OUT, NOT "CHAMPIONSHIP <1%".
 *
 * The consumer half of a notice-46 pair: lane1b's PR #11500 adds an optional
 * `state` ("eliminated" | "won") to each `championship_path[]` step and to each
 * `futures[]` row whose market is a grid column the club is decided on.
 * `probability` is unchanged — the Braves' title leg (Polymarket 114584) keeps
 * trading at 0.001 until the venue grades the series — so every surface must
 * print the verdict, not the price.
 *
 * The specimen below is the producer's own Braves fixture
 * (backend/tests/test_team_page_reads_the_grid_out_verdict_11493.py): out in the
 * NLCS, and an award board at market_tier 1 ("NL Hank Aaron Winner", 206639)
 * that deliberately carries NO state.
 *
 * Both directions (gotcha #43): a decided step prints "Out"/"Won", AND a page
 * whose payload carries no state renders exactly what it did before. And the
 * trap the producer named: the decided path step must never be skipped into the
 * futures fallback, where the award board would lead as "Championship <1%".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import type { ChampionshipPathEntry, TeamFutureItem, TeamPageTeam } from "@/lib/api";
import { teamHeadline } from "@/lib/teamHeadline";
import { decidedState, headlinePathEntry, pickJourneyFuture } from "@/lib/teamSeasonJourney";
import { buildTeamShareCopy, teamCardCopy } from "@/lib/teamShareMeta";
import { TeamChampionshipPath } from "@/components/TeamChampionshipPath";
import { TeamFutureRow } from "@/components/TeamFutureRow";

function future(
  marketId: number,
  name: string,
  tier: number,
  probability: number,
  extra: Partial<TeamFutureItem> = {},
): TeamFutureItem {
  return {
    outcome_id: marketId * 10,
    outcome_name: "Atlanta Braves",
    market_id: marketId,
    market_name: name,
    market_tier: tier,
    category: null,
    source: "polymarket",
    probability,
    probability_change_24h: -0.002,
    rank: 10,
    total_outcomes: 12,
    resolution_date: null,
    ...extra,
  };
}

function step(extra: Partial<ChampionshipPathEntry> = {}): ChampionshipPathEntry {
  return {
    tier: 1,
    label: "Championship",
    market_name: "MLB World Series Champion 2026",
    market_id: 114584,
    probability: 0.001,
    rank: 10,
    movement: -0.2,
    season: "2026",
    ...extra,
  };
}

const TITLE_OUT = future(114584, "MLB World Series Champion 2026", 1, 0.001, {
  state: "eliminated",
});
// The award board the producer deliberately leaves without a state: the title's
// verdict is not its verdict.
const AWARD = future(206639, "MLB: 2026 NL Hank Aaron Winner", 1, 0.001);
const BRAVES_FUTURES = [AWARD, TITLE_OUT];
const BRAVES_PATH = [step({ state: "eliminated" })];

const BRAVES_TEAM: TeamPageTeam = {
  id: 7,
  slug: "atlanta-braves",
  name: "Atlanta Braves",
  abbreviation: "ATL",
  sport_key: "baseball_mlb",
  sport_name: "MLB",
  location: "Atlanta",
  primary_color: "#13274f",
  secondary_color: "#ce1141",
  logo_small: null,
  logo_large: null,
  record: "92-70",
  standings: null,
  season_stats: null,
  roster: null,
};

describe("#11493 headline: the path step's verdict leads", () => {
  it("the Braves' hero reads Championship / Out, from the title step", () => {
    const headline = teamHeadline(BRAVES_PATH, BRAVES_FUTURES);
    expect(headline).toEqual({
      label: "Championship",
      probability: 0.001,
      movement: null,
      state: "eliminated",
    });
  });

  it("STRAWMAN: without the state the same payload still prints the price (today's page)", () => {
    const headline = teamHeadline([step()], [AWARD, future(114584, "MLB World Series Champion 2026", 1, 0.001)]);
    expect(headline).toEqual({
      label: "Championship",
      probability: 0.001,
      movement: -0.2,
      state: null,
    });
  });

  it("a decided step with no number is KEPT, never skipped into the award fallback", () => {
    const path = [step({ probability: null, state: "eliminated" })];
    expect(headlinePathEntry(path)?.market_id).toBe(114584);
    const headline = teamHeadline(path, [AWARD]);
    expect(headline?.state).toBe("eliminated");
    expect(headline?.label).toBe("Championship");
    expect(headline?.probability).toBe(0);
  });

  it("an undecided step with no number still falls through, as before", () => {
    expect(headlinePathEntry([step({ probability: null })])).toBeNull();
  });

  it("with no path, the decided title row outranks a tier-1 award at the same price", () => {
    const headline = teamHeadline([], [AWARD, TITLE_OUT]);
    expect(headline?.state).toBe("eliminated");
    expect(headline?.movement).toBeNull();
    expect(pickJourneyFuture([AWARD, TITLE_OUT])?.marketId).toBe(114584);
  });

  it("the journey charts the title and carries its verdict", () => {
    const pick = pickJourneyFuture(BRAVES_FUTURES, BRAVES_PATH);
    expect(pick?.marketId).toBe(114584);
    expect(pick?.state).toBe("eliminated");
  });

  it("only the two contract words count; anything else is today's behaviour", () => {
    expect(decidedState("eliminated")).toBe("eliminated");
    expect(decidedState("won")).toBe("won");
    expect(decidedState("lost")).toBeNull();
    expect(decidedState("live")).toBeNull();
    expect(decidedState(undefined)).toBeNull();
    const headline = teamHeadline([step({ state: "lost" as never })], []);
    expect(headline?.state).toBeNull();
    expect(headline?.probability).toBe(0.001);
  });
});

describe("#11493 rendered: the path step and the futures row say Out", () => {
  it("the Championship path step prints Out, no <1%, no movement", () => {
    const html = renderToStaticMarkup(
      <TeamChampionshipPath
        entries={[step({ tier: 4, label: "Division", market_id: 1, state: "won", probability: 0.999 }), ...BRAVES_PATH]}
        color="#13274f"
      />,
    );
    expect(html).toContain(">Out<");
    expect(html).toContain(">Won<");
    expect(html).not.toContain("&lt;1%");
    expect(html).not.toContain("pts");
  });

  it("STRAWMAN: the same step without a state prints <1% (the rig can see it)", () => {
    const html = renderToStaticMarkup(<TeamChampionshipPath entries={[step()]} color="#13274f" />);
    expect(html).toContain("&lt;1%");
    expect(html).not.toContain(">Out<");
  });

  it("a decided futures row prints Out with no rank and no movement; its award sibling is unchanged", () => {
    const out = renderToStaticMarkup(<TeamFutureRow item={TITLE_OUT} />);
    expect(out).toContain(">Out<");
    expect(out).not.toContain("&lt;1%");
    expect(out).not.toContain("#10 of 12");
    expect(out).not.toContain("pts");

    const award = renderToStaticMarkup(<TeamFutureRow item={AWARD} />);
    expect(award).toContain("&lt;1%");
    expect(award).toContain("#10 of 12");
    expect(award).not.toContain(">Out<");
  });
});

describe("#11493 share: the link and the picture say out", () => {
  const verdict = {
    kind: "team" as const,
    payload: { team: BRAVES_TEAM, championship_path: BRAVES_PATH, futures: BRAVES_FUTURES },
  };

  it("the description states the result, not the price", () => {
    const copy = buildTeamShareCopy(verdict, "mlb");
    expect(copy.description).toContain("Atlanta Braves: out of the championship.");
    expect(copy.description).not.toContain("<1%");
    expect(copy.description).not.toContain("to win the");
  });

  it("the card draws the verdict slot and no number row", () => {
    const card = teamCardCopy(verdict, "baseball", "mlb");
    expect(card.verdict).toBe("Out of the championship");
    expect(card.rows).toEqual([]);
  });

  it("STRAWMAN: without a state the card keeps its number row", () => {
    const card = teamCardCopy(
      { kind: "team", payload: { team: BRAVES_TEAM, championship_path: [step()], futures: [] } },
      "baseball",
      "mlb",
    );
    expect(card.verdict ?? null).toBeNull();
    expect(card.rows).toHaveLength(1);
    expect(card.rows[0].name).toBe("Championship");
  });
});
