/**
 * #7651 — a club whose league segment is more than one token still lands on
 * the wrong page.
 *
 * Follow-on to #7501. The backend half is done and its shape is SETTLED: rung 2
 * of the slug ladder is `{base}-{url_league_segment(key)}`, where the segment
 * mirrors `buildTeamPageUrl` (`nhl_preseason`, `uefa_champs_league_women`,
 * `ucl` for the aliased keys). Guard-tested by
 * `backend/tests/test_team_slug_url_map_matches_the_frontend_7501.py`, which
 * parses the frontend map. This suite is the frontend half, and both cases are
 * reader-visible today at the URLs `buildTeamPageUrl` itself writes:
 *
 *   - `/sport/icehockey/nhl_preseason/team/new-jersey-devils` renders "We don't
 *     have a icehockey page for New Jersey Devils", while
 *     `GET /api/teams/new-jersey-devils-nhl_preseason` serves the row.
 *   - `/sport/soccer/uefa_champs_league_women/team/benfica` renders the MEN's
 *     Benfica (breadcrumb "Primeira Liga - Portugal"); the women's-UCL row is
 *     at `benfica-uefa_champs_league_women`.
 *
 * WHAT THIS SUITE PINS. `teamRouteCandidates` must try the URL-segment shape
 * the backend mints — FIRST, because every row minted from here on carries it
 * — and keep the sport-key-last-token shape second, because the frozen legacy
 * population (`real-madrid-league`, the `-open` tennis rows) still resolves
 * through it. Single-token leagues are unaffected: the two shapes are the same
 * string there and dedup to one candidate.
 *
 * WHAT THIS SUITE ALSO SETTLES. The issue names two causes; at this SHA only
 * one reproduces. Cause 2 ("the off-route test compares sport only, so the
 * qualified candidate is never tried") is already answered by the `offLeague`
 * trigger the competition half of #5852 shipped: the men's Benfica row reads
 * off-LEAGUE on the UWCL route, the retry fires, and the failure is that the
 * one candidate it tries (`benfica-women`) 404s. That verdict is asserted
 * below so a future reader does not re-litigate it.
 */

import {
  teamRouteCandidates,
  resolveTeamForRoute,
} from "@/lib/teamRouteResolve";
import { describeTeamRoute } from "@/lib/teamRouteSport";

type Team = {
  name: string;
  sport_key?: string | null;
  logo_small?: string | null;
  logo_large?: string | null;
  primary_color?: string | null;
  record?: string | null;
};
type Row = { team: Team };

const full = (name: string, sport_key: string, record: string): Row => ({
  team: {
    name,
    sport_key,
    logo_small: "https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
    primary_color: "ef0107",
    record,
  },
});

function fetcherOver(rows: Record<string, Row>) {
  const asked: string[] = [];
  const fetchTeam = async (slug: string): Promise<Row> => {
    asked.push(slug);
    const row = rows[slug];
    if (!row) throw new Error(`404 ${slug}`);
    return row;
  };
  return { fetchTeam, asked };
}

describe("#7651 — the resolver asks for the segment shape the column holds", () => {
  it("gives a preseason link the Devils' preseason row, not the refusal", async () => {
    const { fetchTeam, asked } = fetcherOver({
      "new-jersey-devils": full("New Jersey Devils", "icehockey_nhl", "0-0-0"),
      "new-jersey-devils-nhl_preseason": full(
        "New Jersey Devils",
        "icehockey_nhl_preseason",
        "2-1-0",
      ),
    });

    const out = await resolveTeamForRoute(
      "new-jersey-devils",
      "icehockey",
      "nhl_preseason",
      fetchTeam,
    );

    expect(out.slug).toBe("new-jersey-devils-nhl_preseason");
    expect(out.data.team.sport_key).toBe("icehockey_nhl_preseason");
    expect(asked).toContain("new-jersey-devils-nhl_preseason");
  });

  it("gives a UWCL link the women's Benfica, not the men's club", async () => {
    const { fetchTeam, asked } = fetcherOver({
      benfica: full("Benfica", "soccer_portugal_primeira_liga", "4-1-0"),
      "benfica-uefa_champs_league_women": full(
        "Benfica",
        "soccer_uefa_champs_league_women",
        "1-0-0",
      ),
    });

    const out = await resolveTeamForRoute(
      "benfica",
      "soccer",
      "uefa_champs_league_women",
      fetchTeam,
    );

    expect(out.slug).toBe("benfica-uefa_champs_league_women");
    expect(out.data.team.sport_key).toBe("soccer_uefa_champs_league_women");
    expect(asked).toContain("benfica-uefa_champs_league_women");
  });

  it("still reaches a legacy last-token row when the segment shape 404s", async () => {
    // `real-madrid-league` is the frozen #7501 population: never re-slugged,
    // still served. The segment shape is tried first and misses; the legacy
    // shape is second and hits.
    const { fetchTeam, asked } = fetcherOver({
      "real-madrid": full("Real Madrid", "soccer_spain_la_liga", "5-0-2"),
      "real-madrid-league": full("Real Madrid", "soccer_uefa_champs_league", "0-0-1"),
    });

    const out = await resolveTeamForRoute("real-madrid", "soccer", "ucl", fetchTeam);

    expect(out.slug).toBe("real-madrid-league");
    expect(asked).toEqual(["real-madrid", "real-madrid-ucl", "real-madrid-league"]);
  });

  it("tries the segment shape first and the legacy shape second, deduped", () => {
    expect(teamRouteCandidates("new-jersey-devils", "icehockey", "nhl_preseason")).toEqual([
      "new-jersey-devils-nhl_preseason",
      "new-jersey-devils-preseason",
    ]);
    expect(teamRouteCandidates("benfica", "soccer", "uefa_champs_league_women")).toEqual([
      "benfica-uefa_champs_league_women",
      "benfica-women",
    ]);
    expect(teamRouteCandidates("real-madrid", "soccer", "ucl")).toEqual([
      "real-madrid-ucl",
      "real-madrid-league",
    ]);
    // Single-token leagues: the two shapes are one string, so one candidate.
    expect(teamRouteCandidates("arsenal", "soccer", "epl")).toEqual(["arsenal-epl"]);
    expect(teamRouteCandidates("clemson-tigers", "football", "ncaaf")).toEqual([
      "clemson-tigers-ncaaf",
    ]);
  });

  it("gives the Devils their preseason row with the rows SHAPED AS PRODUCTION SERVES THEM", async () => {
    // The case above uses furnished rows on both sides, and it passes on a
    // resolver that is inert on production. Read 2026-09-23 from
    // `/api/teams/…`: the NHL row carries crest + colour and no record; the
    // preseason row carries none of the three. The richness test then judges
    // the candidate "poorer" than the NHL row — a row the page never draws,
    // because it is off-SPORT and renders "We don't have a icehockey page".
    // The reader's alternative is the refusal, so the candidate must win.
    const { fetchTeam, asked } = fetcherOver({
      "new-jersey-devils": {
        team: {
          name: "New Jersey Devils",
          sport_key: "icehockey_nhl",
          logo_small: "https://a.espncdn.com/i/teamlogos/nhl/500/nj.png",
          primary_color: "#e30b2b",
          record: null,
        },
      },
      "new-jersey-devils-nhl_preseason": {
        team: {
          name: "New Jersey Devils",
          sport_key: "icehockey_nhl_preseason",
          logo_small: null,
          logo_large: null,
          primary_color: null,
          record: null,
        },
      },
    });

    const out = await resolveTeamForRoute(
      "new-jersey-devils",
      "icehockey",
      "nhl_preseason",
      fetchTeam,
    );

    expect(out.slug).toBe("new-jersey-devils-nhl_preseason");
    expect(describeTeamRoute(out.data.team, "icehockey", "nhl_preseason").offRoute).toBe(false);
    expect(asked).toEqual(["new-jersey-devils", "new-jersey-devils-nhl_preseason"]);
  });

  it("still refuses a poorer row when the first answer is on-sport, i.e. a page", async () => {
    // Control for the case above: the exemption is keyed on the first answer
    // being OFF-SPORT, not on the candidate shape. Same stub candidate, but the
    // first answer is the same sport and renders — so the richness rule binds
    // and the reader keeps the furnished page (the Galatasaray contract).
    const { fetchTeam } = fetcherOver({
      benfica: full("Benfica", "soccer_portugal_primeira_liga", "4-1-0"),
      "benfica-uefa_champs_league_women": {
        team: {
          name: "Benfica",
          sport_key: "soccer_uefa_champs_league_women",
          logo_small: null,
          logo_large: null,
          primary_color: null,
          record: null,
        },
      },
    });

    const out = await resolveTeamForRoute(
      "benfica",
      "soccer",
      "uefa_champs_league_women",
      fetchTeam,
    );

    expect(out.slug).toBe("benfica");
    expect(out.data.team.sport_key).toBe("soccer_portugal_primeira_liga");
  });

  it("stands the first answer back up when an already-qualified slug misses", async () => {
    // A canonical multi-token slug whose row is off-route is a data anomaly,
    // not a reader path — the sibling shape 404s and the off-route notice is
    // then the honest answer, exactly the Hawai'i contract.
    const { fetchTeam, asked } = fetcherOver({
      "new-jersey-devils-nhl_preseason": full(
        "New Jersey Devils",
        "icehockey_nhl",
        "0-0-0",
      ),
    });

    const out = await resolveTeamForRoute(
      "new-jersey-devils-nhl_preseason",
      "icehockey",
      "nhl_preseason",
      fetchTeam,
    );

    expect(out.slug).toBe("new-jersey-devils-nhl_preseason");
    expect(out.data.team.sport_key).toBe("icehockey_nhl");
    expect(asked[0]).toBe("new-jersey-devils-nhl_preseason");
  });
});

describe("#7651 — cause 2 does not reproduce: the trigger already fires", () => {
  it("reads the men's Benfica row as off-league on the UWCL route", () => {
    const verdict = describeTeamRoute(
      { name: "Benfica", sport_key: "soccer_portugal_primeira_liga" },
      "soccer",
      "uefa_champs_league_women",
    );

    expect(verdict.offLeague).toBe(true);
    expect(verdict.offRoute).toBe(false);
  });

  it("reads the NHL Devils row as off-route AND off-league on the preseason route", () => {
    const verdict = describeTeamRoute(
      { name: "New Jersey Devils", sport_key: "icehockey_nhl" },
      "icehockey",
      "nhl_preseason",
    );

    // `icehockey_nhl` maps to the `hockey` sport segment, so the family test
    // fires too — this is the page that prints the reader-facing sentence.
    expect(verdict.offRoute).toBe(true);
    expect(verdict.offLeague).toBe(true);
  });
});
