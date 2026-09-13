/**
 * #5852, the LINK half — we told a reader we had no football page for a team
 * whose football page we had.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, 390px, 2026-09-13 ~13:3xZ. Tap "Clemson Tigers" in an NCAAF event
 * hero, land on `/sport/football/ncaaf/team/clemson-tigers`:
 *
 *     We don't have a football page for Clemson Tigers.
 *     Clemson Tigers — Basketball        Back to NCAAF
 *
 * The football page existed the whole time, at
 * `/sport/football/ncaaf/team/clemson-tigers-ncaaf` — "Home / NCAAF / Clemson
 * Tigers", record 1-1, CHAMPIONSHIP 1%, "vs North Carolina Tar Heels … 63%".
 * The shipped guard was right that the WNCAAB team was the wrong answer; it
 * just had no way to go and get the right one.
 *
 * ═══ MECHANISM ═══
 *
 * `GET /api/teams/{slug}` resolves by slug alone and is never told the sport,
 * although the path says `football/ncaaf`. Measured on production:
 * `/api/teams/clemson-tigers` → team 72, `basketball_wncaab`;
 * `/api/teams/clemson-tigers-ncaaf` → team 10, `americanfootball_ncaaf`.
 *
 * ═══ REACH, MEASURED ON PRODUCTION ═══
 *
 * The ±48h reader window, 950 distinct teams on real events:
 *
 *   - 191 resolve to a team in ANOTHER SPORT FAMILY (today's off-route notice)
 *   -  17 of those have a league-qualified row this retry reaches — Clemson,
 *        LSU, Michigan, Ohio State, Notre Dame, Texas, Auburn, UCLA, Wisconsin,
 *        Baylor, TCU, SMU, Ole Miss, Houston, North Carolina, Cal, Texas Tech.
 *        The marquee slate the issue named.
 *   -   0 whose bare slug resolves to NOTHING have one — which is why a thrown
 *        first fetch is deliberately not retried, and why the test below that
 *        pins that is a real assertion and not a shrug.
 *
 * ═══ THE DIRECTIONS THIS SUITE ASSERTS (gotcha #43) ═══
 *
 * Not just "the broken case is fixed" but "the working cases are untouched":
 * an on-route first answer must never cost a second request, the tennis
 * same-family case the family test exists to protect must never reach the
 * retry, and a retry that comes back off-route must be discarded rather than
 * rendered.
 */

import {
  leagueQualifiedSlug,
  resolveTeamForRoute,
} from "@/lib/teamRouteResolve";

type Row = { team: { name: string; sport_key?: string | null } };

/** The two real production rows for Clemson, by the slug that returns them. */
const CLEMSON: Record<string, Row> = {
  "clemson-tigers": { team: { name: "Clemson Tigers", sport_key: "basketball_wncaab" } },
  "clemson-tigers-ncaaf": { team: { name: "Clemson Tigers", sport_key: "americanfootball_ncaaf" } },
};

/** A fetcher over a fixed table that records what was asked for. */
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

describe("#5852 link half — the league-qualified retry", () => {
  it("reaches the NCAAF Clemson page that the WNCAAB slug was hiding", async () => {
    const { fetchTeam, asked } = fetcherOver(CLEMSON);

    const out = await resolveTeamForRoute("clemson-tigers", "football", "ncaaf", fetchTeam);

    expect(out.slug).toBe("clemson-tigers-ncaaf");
    expect(out.data.team.sport_key).toBe("americanfootball_ncaaf");
    expect(asked).toEqual(["clemson-tigers", "clemson-tigers-ncaaf"]);
  });

  it("keeps the off-route notice for Hawai'i, which has no NCAAF row at all", async () => {
    // The real production pair: the WNCAAB row owns the bare slug and
    // `hawaii-rainbow-warriors-ncaaf` genuinely 404s.
    const { fetchTeam, asked } = fetcherOver({
      "hawaii-rainbow-warriors": {
        team: { name: "Hawai'i Rainbow Warriors", sport_key: "basketball_wncaab" },
      },
    });

    const out = await resolveTeamForRoute(
      "hawaii-rainbow-warriors",
      "football",
      "ncaaf",
      fetchTeam,
    );

    // First answer preserved, so the page still renders the honest notice.
    expect(out.slug).toBe("hawaii-rainbow-warriors");
    expect(out.data.team.sport_key).toBe("basketball_wncaab");
    expect(asked).toEqual(["hawaii-rainbow-warriors", "hawaii-rainbow-warriors-ncaaf"]);
  });

  it("costs an on-route team no second request", async () => {
    const { fetchTeam, asked } = fetcherOver({
      "boston-red-sox": { team: { name: "Boston Red Sox", sport_key: "baseball_mlb" } },
    });

    const out = await resolveTeamForRoute("boston-red-sox", "baseball", "mlb", fetchTeam);

    expect(out.slug).toBe("boston-red-sox");
    expect(asked).toEqual(["boston-red-sox"]);
  });

  it("never retries the tennis same-family case the family test protects", async () => {
    // A player's page filed under a different tournament is about the RIGHT
    // person; `describeTeamRoute` returns offRoute false, so no retry may fire.
    const { fetchTeam, asked } = fetcherOver({
      "jannik-sinner": { team: { name: "Jannik Sinner", sport_key: "tennis_wta_miami_open" } },
    });

    const out = await resolveTeamForRoute("jannik-sinner", "tennis", "atp_us_open", fetchTeam);

    expect(out.slug).toBe("jannik-sinner");
    expect(asked).toEqual(["jannik-sinner"]);
  });

  it("discards a retry that is ALSO off-route rather than rendering it", async () => {
    const { fetchTeam } = fetcherOver({
      "wrong-team": { team: { name: "Wrong Team", sport_key: "basketball_wncaab" } },
      "wrong-team-ncaaf": { team: { name: "Wrong Team", sport_key: "basketball_ncaab" } },
    });

    const out = await resolveTeamForRoute("wrong-team", "football", "ncaaf", fetchTeam);

    expect(out.slug).toBe("wrong-team");
    expect(out.data.team.sport_key).toBe("basketball_wncaab");
  });

  it("lets a thrown first fetch propagate, so a real 404 stays 'Team not found'", async () => {
    const { fetchTeam, asked } = fetcherOver({});

    await expect(
      resolveTeamForRoute("no-such-team", "football", "ncaaf", fetchTeam),
    ).rejects.toThrow();
    // Measured 0 teams in this class have a league-qualified row, so the retry
    // must not be bought here.
    expect(asked).toEqual(["no-such-team"]);
  });

  it("does not ask for clemson-tigers-ncaaf-ncaaf when already on the canonical slug", async () => {
    // An off-route answer for an already-suffixed slug has nothing left to try.
    const { fetchTeam, asked } = fetcherOver({
      "clemson-tigers-ncaaf": {
        team: { name: "Clemson Tigers", sport_key: "basketball_wncaab" },
      },
    });

    const out = await resolveTeamForRoute("clemson-tigers-ncaaf", "football", "ncaaf", fetchTeam);

    expect(out.slug).toBe("clemson-tigers-ncaaf");
    expect(asked).toEqual(["clemson-tigers-ncaaf"]);
  });
});

describe("#5852 — leagueQualifiedSlug composes the candidate, never guesses it", () => {
  it("appends the league segment the URL already carries", () => {
    // The three real production shapes of the suffix convention.
    expect(leagueQualifiedSlug("clemson-tigers", "ncaaf")).toBe("clemson-tigers-ncaaf");
    expect(leagueQualifiedSlug("boston-red-sox", "mlb")).toBe("boston-red-sox-mlb");
    expect(leagueQualifiedSlug("arsenal", "epl")).toBe("arsenal-epl");
  });

  it("returns null when there is nothing to try", () => {
    expect(leagueQualifiedSlug("clemson-tigers", "")).toBeNull();
    expect(leagueQualifiedSlug("clemson-tigers", "   ")).toBeNull();
    expect(leagueQualifiedSlug("", "ncaaf")).toBeNull();
    expect(leagueQualifiedSlug("clemson-tigers-ncaaf", "ncaaf")).toBeNull();
    expect(leagueQualifiedSlug("clemson-tigers-NCAAF", "ncaaf")).toBeNull();
  });

  it("does not mistake a league that merely appears inside the slug for the suffix", () => {
    // "mlb-classics" ends with neither "-mlb" nor anything else we append to.
    expect(leagueQualifiedSlug("mlb-classics", "mlb")).toBe("mlb-classics-mlb");
  });
});
