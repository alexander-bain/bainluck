/**
 * #2447 — ONE RESOLVER SERVES BOTH SURFACES.
 *
 * Alex: *"`/events/15293846` renders `MB` and `SW` avatar initials for
 * Berrettini and Wawrinka. The tournament page renders photographs for the same
 * two players. One resolver should serve both."*
 *
 * ## What it was
 *
 * The event hero's face ladder is `home_team_data.logo_large` →
 * `espnTeamLogoByName(name, sport_key)` → initials. Both of the first two rungs
 * are TEAM resolvers. A tennis player is not a team, has no `teams` row and no
 * ESPN team logo, so every match at this tournament fell straight through to
 * initials — while the register, four sections down the same page, held a
 * censused photograph of the same person.
 *
 * The register's resolver is `player_image`, verified offline by
 * `census_player_images.py` against the article's own description, precisely
 * because a bare-name Wikipedia lookup returns a Serbian footballer for
 * `Aleksandar Kovacevic` and a US President for `Andrew Johnson`. That
 * verification is why the fix READS the pin rather than adding a fourth guess.
 *
 * ## The live shape this is written against
 *
 * `/api/tournaments/by-event/15293846`, fetched 2026-09-01:
 *
 *   - `result.players[]` carries both faces, each a full `{url, flag_url}`;
 *   - `advancement.home_team.logo_url` carries Berrettini's photo;
 *   - **`advancement.away_team` is `null`** — Wawrinka is not on the reach
 *     board, which is the ordinary case (26 of 96 R128 fixtures have neither
 *     player on it).
 *
 * That last line is why there are two branches. Either one alone leaves half of
 * this match on initials, and the test below pins each branch separately so a
 * "simplification" down to one cannot pass.
 *
 * ## And the branch that matters most is the one that returns nothing
 *
 * Both branches match on the event's own `home_team` / `away_team` STRINGS.
 * `result.players` carry no home/away semantics at all, and `advancement`
 * carries them from a different code path. A positional read would swap two
 * faces the day either ordering changed — and a wrong face is exactly the
 * failure the census exists to prevent: instant, confident, and unverifiable by
 * the reader. A name that does not match returns `null` and the side falls back
 * to initials, which is the correct answer, not a degraded one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  TournamentPlayerFace,
  registerFace,
} from "@/components/event/TournamentExtensions";
import type { EventTournamentResponse } from "@/lib/types";

let swrAnswer: { data?: EventTournamentResponse } = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => (key === null ? { data: undefined } : swrAnswer),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

const BERRETTINI_FACE =
  "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/Matteo_Berrettini.jpg";
const WAWRINKA_FACE =
  "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Wawrinka_RG19.jpg";
const SUI_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/sui.png";

/** The live payload's shape: a finished match with both players' pinned images. */
function withResult(): EventTournamentResponse {
  return {
    event_id: 15293846,
    tournament: { slug: "us-open", title: "US Open 2026", url: "/tournaments/us-open" },
    props: [],
    props_count: 0,
    props_dropped: {},
    decided: true,
    result: {
      matchup_key: "mens-singles:matteo-berrettini-vs-stan-wawrinka:2026-08-30",
      draw: "mens-singles",
      draw_label: "Men's Singles",
      round: "Round 1",
      players: [
        {
          entity_key: "stan-wawrinka",
          display_name: "Stan Wawrinka",
          seed: null,
          is_winner: false,
          image: { url: WAWRINKA_FACE, flag_url: SUI_FLAG },
          prematch_probability: 0.217172,
        },
        {
          entity_key: "matteo-berrettini",
          display_name: "Matteo Berrettini",
          seed: null,
          is_winner: true,
          image: { url: BERRETTINI_FACE, flag_url: null },
          prematch_probability: 0.782828,
        },
      ],
      winner_entity_key: "matteo-berrettini",
      score: "7-6, 7-6, 6-0",
      completed_at: "2026-08-30T20:25Z",
      source_round: "Round 1",
      source: "espn",
    },
  } as EventTournamentResponse;
}

/** The other branch: a quoted player on the reach board, no result yet. */
function withAdvancementOnly(): EventTournamentResponse {
  return {
    event_id: 15293846,
    tournament: { slug: "us-open", title: "US Open 2026", url: "/tournaments/us-open" },
    props: [],
    props_count: 0,
    props_dropped: {},
    decided: false,
    advancement: {
      event_id: 15293846,
      league: "us-open",
      league_name: "US Open 2026",
      grid_url: "/tournaments/us-open",
      columns: [],
      home_team: {
        name: "Matteo Berrettini",
        short_name: "Berrettini",
        team_id: null,
        logo_url: BERRETTINI_FACE,
        primary_color: null,
        secondary_color: null,
        record: null,
        conference: null,
        stages: [],
      },
      // MEASURED: null on the live payload. Wawrinka is not quoted to reach a
      // later round, which is the ordinary case for an unseeded first-rounder.
      away_team: null,
    },
  } as unknown as EventTournamentResponse;
}

const FALLBACK = <span data-testid="hero-initials">MB</span>;

function face(side: "home" | "away"): string {
  return renderToStaticMarkup(
    <TournamentPlayerFace
      eventId={15293846}
      sportKey="tennis_atp_us_open"
      homeName="Matteo Berrettini"
      awayName="Stan Wawrinka"
      side={side}
      size={56}
      fallback={FALLBACK}
    />
  );
}

describe("#2447 — the event hero draws the register's face, not initials", () => {
  it("draws BOTH players from the finished match's pinned images", () => {
    swrAnswer = { data: withResult() };

    const home = face("home");
    expect(home).toContain('data-testid="player-avatar"');
    expect(home).toContain('data-kind="face"');
    expect(home).toContain(BERRETTINI_FACE);
    expect(home).not.toContain('data-testid="hero-initials"');

    const away = face("away");
    expect(away).toContain('data-kind="face"');
    expect(away).toContain(WAWRINKA_FACE);
    expect(away).not.toContain('data-testid="hero-initials"');
  });

  /**
   * THE SECOND BRANCH, ALONE. On the live payload `advancement.away_team` is
   * null, so this arm proves the reach board serves the side it has AND that
   * the side it does not have falls back rather than borrowing its opponent's
   * face — which is the failure a positional read would produce.
   */
  it("falls back to the reach board, one side at a time", () => {
    swrAnswer = { data: withAdvancementOnly() };

    const home = face("home");
    expect(home).toContain('data-kind="face"');
    expect(home).toContain(BERRETTINI_FACE);

    const away = face("away");
    expect(away).toContain('data-testid="hero-initials"');
    expect(away).not.toContain(BERRETTINI_FACE);
  });

  /**
   * MATCHED BY NAME, NOT BY POSITION. The payload here has the two players in
   * the order it happens to have them; asking for a third name must return
   * nothing rather than whichever row was first.
   */
  it("returns nothing for a name the register does not carry", () => {
    const data = withResult();
    expect(registerFace(data, "Carlos Alcaraz")).toBeNull();
    expect(registerFace(data, "")).toBeNull();
    expect(registerFace(undefined, "Matteo Berrettini")).toBeNull();
    // And it is the NAME that selects, not the array index: the payload lists
    // Wawrinka first, so a positional read would hand Berrettini his face.
    expect(registerFace(data, "Matteo Berrettini")?.url).toBe(BERRETTINI_FACE);
    expect(registerFace(data, "Stan Wawrinka")?.url).toBe(WAWRINKA_FACE);
  });

  /**
   * THE OTHER DIRECTION (gotcha #43). Every non-tournament event on the site
   * must keep the hero it has. The fallback is not a degraded path here — it is
   * the path for almost every event, and this fix adds a rung to the front of
   * that ladder rather than replacing it.
   */
  it("leaves a non-tournament hero exactly as it was", () => {
    swrAnswer = {};
    const html = renderToStaticMarkup(
      <TournamentPlayerFace
        eventId={999}
        sportKey="basketball_nba"
        homeName="Denver Nuggets"
        awayName="Boston Celtics"
        side="home"
        size={56}
        fallback={FALLBACK}
      />
    );
    expect(html).toBe('<span data-testid="hero-initials">MB</span>');
  });

  /** And a register event whose player simply has no pinned image. */
  it("keeps the fallback when the register holds no image for the player", () => {
    const data = withResult();
    data.result!.players[1].image = { url: null, flag_url: null };
    swrAnswer = { data };
    expect(face("home")).toContain('data-testid="hero-initials"');
  });

  /**
   * A FLAG IS A REAL ANSWER, not a consolation. Every draw sheet and broadcast
   * scoreboard in tennis has printed one for fifty years, and it is what makes
   * the column uniform for the ~5% the census could not find a face for.
   */
  it("uses the country flag when there is no photograph", () => {
    const data = withResult();
    data.result!.players[1].image = { url: null, flag_url: SUI_FLAG };
    swrAnswer = { data };
    const html = face("home");
    expect(html).toContain('data-kind="flag"');
    expect(html).toContain(SUI_FLAG);
  });
});
