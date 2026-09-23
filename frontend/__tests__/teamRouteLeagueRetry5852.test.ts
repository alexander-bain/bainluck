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
import { classifyTeamShare, fetchTeamShare } from "@/lib/teamShareMeta";

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

  /**
   * ⚠️ THIS ASSERTION WAS REVISED 2026-09-20, AND REVISED AGAIN 2026-09-23
   * (#7651), AND THE PROTECTION IT CARRIES WAS NOT DROPPED EITHER TIME. It
   * used to read `expect(asked).toEqual(["jannik-sinner"])` — "the tennis case
   * never reaches the retry at all" — because the trigger was the SPORT family
   * and a cross-tournament row is same-family. The competition half of #5852
   * widened the trigger, so the retry is now offered a tennis route too. What
   * that test was defending is that a reader is never moved off the right
   * PERSON, and that is asserted here directly (and again below, on the row
   * that does exist). The second revision drops the "never asked for" pin on
   * `jannik-sinner-atp_us_open`: its rationale — an underscore `slugify`
   * cannot emit — went stale when #7501 settled new rows on exactly that
   * shape, so the segment shape is now tried first and 404s here.
   */
  it("leaves a tennis player on the tournament row they already have when there is no better one", async () => {
    const { fetchTeam, asked } = fetcherOver({
      "jannik-sinner": { team: { name: "Jannik Sinner", sport_key: "tennis_wta_miami_open" } },
    });

    const out = await resolveTeamForRoute("jannik-sinner", "tennis", "atp_us_open", fetchTeam);

    expect(out.slug).toBe("jannik-sinner");
    expect(out.data.team.name).toBe("Jannik Sinner");
    expect(asked).toEqual(["jannik-sinner", "jannik-sinner-atp_us_open", "jannik-sinner-open"]);
  });

  it("gives a tennis player the tournament row the URL asked for when it exists", async () => {
    // 502 rows in this shape, measured 2026-09-20: the suffix is the sport
    // key's last token, so `tennis_atp_us_open` mints `-open`.
    const { fetchTeam } = fetcherOver({
      "jannik-sinner": { team: { name: "Jannik Sinner", sport_key: "tennis_wta_miami_open" } },
      "jannik-sinner-open": {
        team: { name: "Jannik Sinner", sport_key: "tennis_atp_us_open" },
      },
    });

    const out = await resolveTeamForRoute("jannik-sinner", "tennis", "atp_us_open", fetchTeam);

    expect(out.slug).toBe("jannik-sinner-open");
    expect(out.data.team.name).toBe("Jannik Sinner");
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

/**
 * The unfurl has to resolve the SAME way the page does, or the promise
 * `classifyTeamShare` makes in its own header — that the card and the page
 * "cannot disagree about whether this URL is a football page" — is broken by
 * the retry rather than kept by it. A reader who pastes a Clemson football link
 * must not be shown "we don't have a football page for Clemson Tigers" and then
 * disprove it by tapping the preview.
 */
describe("#5852 — the unfurl resolves the same way the page does", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  /** A `fetch` over a slug→row table; anything absent 404s, as the API does. */
  function mockApi(rows: Record<string, Row>) {
    const asked: string[] = [];
    global.fetch = jest.fn(async (url: string) => {
      const slug = decodeURIComponent(String(url).split("/api/teams/")[1] ?? "");
      asked.push(slug);
      const row = rows[slug];
      if (!row) return { status: 404, ok: false } as Response;
      return { status: 200, ok: true, json: async () => row } as unknown as Response;
    }) as unknown as typeof fetch;
    return asked;
  }

  it("unfurls the Clemson football team, not the refusal the page no longer shows", async () => {
    const asked = mockApi(CLEMSON);

    const verdict = classifyTeamShare(
      await fetchTeamShare("football", "ncaaf", "clemson-tigers"),
      "football",
    );

    expect(verdict.kind).toBe("team");
    expect(asked).toEqual(["clemson-tigers", "clemson-tigers-ncaaf"]);
  });

  it("still refuses Hawai'i, which has no NCAAF row to find", async () => {
    mockApi({
      "hawaii-rainbow-warriors": {
        team: { name: "Hawai'i Rainbow Warriors", sport_key: "basketball_wncaab" },
      },
    });

    const verdict = classifyTeamShare(
      await fetchTeamShare("football", "ncaaf", "hawaii-rainbow-warriors"),
      "football",
    );

    expect(verdict.kind).toBe("off-route");
  });

  it("keeps 404 and a bad minute apart through the retry (gotcha #53)", async () => {
    // Nothing at all: the FIRST fetch 404s, so the failure is "not-found" and
    // must not be laundered into "unavailable" by the retry machinery.
    mockApi({});
    const missing = await fetchTeamShare("football", "ncaaf", "no-such-team");
    expect(missing).toEqual({ ok: false, failure: "not-found" });

    global.fetch = jest.fn(async () => ({ status: 503, ok: false }) as Response) as unknown as typeof fetch;
    const down = await fetchTeamShare("football", "ncaaf", "clemson-tigers");
    expect(down).toEqual({ ok: false, failure: "unavailable" });
  });

  it("does not let a retry's 404 overwrite a first answer that succeeded", async () => {
    // Clemson resolves off-route, the retry 404s: the first answer stands and
    // the card refuses — it must NOT come back as `unresolved`.
    mockApi({
      "clemson-tigers": { team: { name: "Clemson Tigers", sport_key: "basketball_wncaab" } },
    });

    const lookup = await fetchTeamShare("football", "ncaaf", "clemson-tigers");

    expect(lookup.ok).toBe(true);
    expect(classifyTeamShare(lookup, "football").kind).toBe("off-route");
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
