/**
 * #5852, the COMPETITION half — the guard that caught the wrong SPORT was blind
 * to the wrong COMPETITION.
 *
 * ═══ WHAT A READER SEES ═══
 *
 * Production, 390px, 2026-09-20. `/sport/soccer/epl/team/arsenal` — the URL
 * `buildTeamPageUrl` itself writes for an EPL Arsenal link, since the slug is
 * `slugify(name)`:
 *
 *   | | `/epl/team/arsenal` (the app's own link) | `/epl/team/arsenal-epl` |
 *   |---|---|---|
 *   | resolves to | 1826 `soccer_england_efl_cup` | 133 `soccer_epl` |
 *   | breadcrumb  | Home / EFL Cup / Arsenal      | Home / EPL / Arsenal    |
 *   | crest       | grey "A" placeholder          | Arsenal crest           |
 *   | record      | absent                        | 4-0-1                   |
 *
 * `describeTeamRoute` compared the SPORT segment, and both rows are soccer, so
 * `offRoute` was false, the shipped retry never fired and nothing noticed.
 *
 * ═══ THE POPULATION, MEASURED ON THE SERVED PAYLOAD ═══
 *
 * Not on `teams`: the table over-reports, because #2498 already swaps
 * season-variant rows at serve time. 145 probes against `/api/teams/{slug}`,
 * 2026-09-20 ~20:3xZ, one per club with a game in −14d…+30d:
 *
 *   - 98 of 136 are served ANOTHER COMPETITION'S row by the app's own link
 *   - 78 of those are SAME-FAMILY — invisible to the shipped guard
 *   - of the 73 unique ones, the qualified row is on-route in 47
 *   - identity fields on those pairs: richer 27, equal 18, POORER 2
 *
 * Six Bundesliga clubs are served their WOMEN's row (Leverkusen, Union Berlin,
 * Freiburg, Hoffenheim, RB Leipzig, Werder Bremen, and Köln); Chelsea, Fulham,
 * Brentford, Sunderland, Leeds and Crystal Palace are served an FA Cup stub
 * with no crest and no record.
 *
 * ═══ THE DIRECTIONS THIS SUITE ASSERTS (gotcha #43) ═══
 *
 * Both ways round, and the two poorer cases by name: the right row is reached,
 * the wrong-sport behaviour that already shipped is untouched, a candidate that
 * would EMPTY the page is refused, and the cost of the repair — how many extra
 * requests a render can buy — is pinned rather than left to drift.
 */

import {
  sportKeyQualifiedSlug,
  teamRouteCandidates,
  resolveTeamForRoute,
} from "@/lib/teamRouteResolve";
import { describeTeamRoute } from "@/lib/teamRouteSport";
import { sportKeyForRoute } from "@/lib/teamUrls";

type Team = {
  name: string;
  sport_key?: string | null;
  logo_small?: string | null;
  logo_large?: string | null;
  primary_color?: string | null;
  record?: string | null;
};
type Row = { team: Team };

/** A stub row: the crest-less, record-less shape a cup row actually serves. */
const stub = (name: string, sport_key: string): Row => ({
  team: { name, sport_key, logo_small: null, primary_color: null, record: null },
});

/** A full row: crest, colour and record, the way a league row serves them. */
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

describe("#5852 competition half — which row a route resolves to", () => {
  it("gives an EPL link the EPL Arsenal, not the EFL Cup stub", async () => {
    const { fetchTeam, asked } = fetcherOver({
      arsenal: stub("Arsenal", "soccer_england_efl_cup"),
      "arsenal-epl": full("Arsenal", "soccer_epl", "4-0-1"),
    });

    const out = await resolveTeamForRoute("arsenal", "soccer", "epl", fetchTeam);

    expect(out.slug).toBe("arsenal-epl");
    expect(out.data.team.sport_key).toBe("soccer_epl");
    expect(out.data.team.record).toBe("4-0-1");
    expect(asked).toEqual(["arsenal", "arsenal-epl"]);
  });

  it("gives a Bundesliga link the men's row, not Union Berlin women", async () => {
    const { fetchTeam } = fetcherOver({
      "union-berlin": stub("Union Berlin", "soccer_germany_bundesliga_women"),
      "union-berlin-bundesliga": full("Union Berlin", "soccer_germany_bundesliga", "0-1-3"),
    });

    const out = await resolveTeamForRoute("union-berlin", "soccer", "bundesliga", fetchTeam);

    expect(out.slug).toBe("union-berlin-bundesliga");
    expect(out.data.team.sport_key).toBe("soccer_germany_bundesliga");
  });

  it("reaches a row whose suffix is the sport key's last token, not the URL segment", async () => {
    // `/sport/soccer/ucl/…` is an ALIAS: the row is `real-madrid-league`,
    // minted from `soccer_uefa_champs_league`. `real-madrid-ucl` does not exist.
    const { fetchTeam, asked } = fetcherOver({
      "real-madrid": full("Real Madrid", "soccer_spain_la_liga", "5-0-2"),
      "real-madrid-league": full("Real Madrid", "soccer_uefa_champs_league", "0-0-1"),
    });

    const out = await resolveTeamForRoute("real-madrid", "soccer", "ucl", fetchTeam);

    expect(out.slug).toBe("real-madrid-league");
    expect(asked).not.toContain("real-madrid-ucl");
  });

  it("refuses a right-competition row that would cost the reader the crest and the record", async () => {
    // Galatasaray, measured: the UCL row it is served today carries crest,
    // colour and 0-0-1; the Süper Lig row carries none of the three. Fixing the
    // breadcrumb by emptying the page is not a fix.
    const { fetchTeam } = fetcherOver({
      galatasaray: full("Galatasaray", "soccer_uefa_champs_league", "0-0-1"),
      "galatasaray-league": stub("Galatasaray", "soccer_turkey_super_league"),
    });

    const out = await resolveTeamForRoute(
      "galatasaray",
      "soccer",
      "turkey_super_league",
      fetchTeam,
    );

    expect(out.slug).toBe("galatasaray");
    expect(out.data.team.sport_key).toBe("soccer_uefa_champs_league");
  });

  it("refuses a row that loses ONLY the crest", async () => {
    // The per-field rule stated as a class, not as a specimen: the crest is
    // what the lane1 shop SAW ("grey 'A' placeholder"), so a candidate that
    // arrives without one is refused even holding colour and record.
    const { fetchTeam } = fetcherOver({
      chelsea: full("Chelsea", "soccer_fa_cup", "3-2-0"),
      "chelsea-epl": {
        team: {
          name: "Chelsea",
          sport_key: "soccer_epl",
          logo_small: null,
          logo_large: null,
          primary_color: "034694",
          record: "3-2-0",
        },
      },
    });

    const out = await resolveTeamForRoute("chelsea", "soccer", "epl", fetchTeam);

    expect(out.slug).toBe("chelsea");
    expect(out.data.team.sport_key).toBe("soccer_fa_cup");
  });

  it("refuses a row that loses ONLY the record, and does not trade it for a crest", async () => {
    // Newcastle: the EPL row it is served has crest, colour and 2-2-1; the UCL
    // row has crest and colour but no record. Per-field, not a total.
    const { fetchTeam } = fetcherOver({
      "newcastle-united": full("Newcastle United", "soccer_epl", "2-2-1"),
      "newcastle-united-league": {
        team: {
          name: "Newcastle United",
          sport_key: "soccer_uefa_champs_league",
          logo_small: "https://a.espncdn.com/i/teamlogos/soccer/500/361.png",
          primary_color: "241f20",
          record: null,
        },
      },
    });

    const out = await resolveTeamForRoute("newcastle-united", "soccer", "ucl", fetchTeam);

    expect(out.slug).toBe("newcastle-united");
    expect(out.data.team.record).toBe("2-2-1");
  });

  it("takes a right-competition row that only ADDS identity", async () => {
    const { fetchTeam } = fetcherOver({
      brentford: stub("Brentford", "soccer_fa_cup"),
      "brentford-epl": full("Brentford", "soccer_epl", "2-3-0"),
    });

    const out = await resolveTeamForRoute("brentford", "soccer", "epl", fetchTeam);

    expect(out.slug).toBe("brentford-epl");
    expect(out.data.team.record).toBe("2-3-0");
  });

  it("refuses a candidate that is on-sport but still the wrong competition", async () => {
    const { fetchTeam } = fetcherOver({
      lazio: stub("Lazio", "soccer_italy_coppa_italia"),
      // The suffix row exists but is a THIRD competition — not what was asked.
      "lazio-a": full("Lazio", "soccer_uefa_europa_league", "1-0-0"),
    });

    const out = await resolveTeamForRoute("lazio", "soccer", "italy_serie_a", fetchTeam);

    expect(out.slug).toBe("lazio");
    expect(out.data.team.sport_key).toBe("soccer_italy_coppa_italia");
  });

  it("still fires for a wrong-SPORT row whose league segment happens to match", async () => {
    // `soccer_sweden_allsvenskan` and `icehockey_sweden_allsvenskan` are both
    // real sports, and AIK is a real club in both — measured on production
    // 2026-09-20, `/sport/soccer/sweden_allsvenskan/team/aik` is served the ICE
    // HOCKEY row. The league segments are identical, so `offLeague` is false
    // here and only `offRoute` can see it: the trigger needs both, not either.
    const { fetchTeam } = fetcherOver({
      aik: stub("AIK", "icehockey_sweden_allsvenskan"),
      "aik-allsvenskan": full("AIK", "soccer_sweden_allsvenskan", "8-4-2"),
    });

    expect(
      describeTeamRoute(
        { name: "AIK", sport_key: "icehockey_sweden_allsvenskan" },
        "soccer",
        "sweden_allsvenskan",
      ),
    ).toMatchObject({ offRoute: true, offLeague: false });

    const out = await resolveTeamForRoute("aik", "soccer", "sweden_allsvenskan", fetchTeam);

    expect(out.slug).toBe("aik-allsvenskan");
    expect(out.data.team.sport_key).toBe("soccer_sweden_allsvenskan");
  });

  it("costs an on-competition page no extra request at all", async () => {
    const { fetchTeam, asked } = fetcherOver({
      "arsenal-epl": full("Arsenal", "soccer_epl", "4-0-1"),
    });

    const out = await resolveTeamForRoute("arsenal-epl", "soccer", "epl", fetchTeam);

    expect(out.slug).toBe("arsenal-epl");
    expect(asked).toEqual(["arsenal-epl"]);
  });

  it("buys exactly one extra request, whatever shape the route segment is", () => {
    // The segment IS the key's last token.
    expect(teamRouteCandidates("arsenal", "soccer", "epl")).toEqual(["arsenal-epl"]);
    // Multi-token: `-cup` from the key; `-fa_cup` is unaskable and not tried.
    expect(teamRouteCandidates("arsenal", "soccer", "fa_cup")).toEqual(["arsenal-cup"]);
    // An ALIAS: the row is `-league`, and the table holds no `-ucl` row to try.
    expect(teamRouteCandidates("arsenal", "soccer", "ucl")).toEqual(["arsenal-league"]);
  });

  it("suffixes with ONE token of the sport key, so a candidate is always slug-shaped", () => {
    // All 5,748 team slugs and all 74 legacy slugs match ^[a-z0-9-]+$, and the
    // suffix is a single key token — never the multi-token URL segment, which
    // would put an underscore in a slug no row can have.
    for (const [slug, sport, league] of [
      ["jannik-sinner", "tennis", "atp_us_open"],
      ["lazio", "soccer", "italy_serie_a"],
      ["stade-de-reims", "soccer", "france_ligue_two"],
    ] as const) {
      const [candidate] = teamRouteCandidates(slug, sport, league);
      expect(candidate).toMatch(/^[a-z0-9-]+$/);
    }
    expect(teamRouteCandidates("jannik-sinner", "tennis", "atp_us_open")).toEqual([
      "jannik-sinner-open",
    ]);
    expect(teamRouteCandidates("lazio", "soccer", "italy_serie_a")).toEqual(["lazio-a"]);
  });

  it("refuses a row that loses ONLY the colour", async () => {
    // The third field of the per-field rule, asserted on its own: a club's
    // colour is what the hero and every chip on the page are painted from.
    const { fetchTeam } = fetcherOver({
      fulham: full("Fulham", "soccer_fa_cup", "0-2-3"),
      "fulham-epl": {
        team: {
          name: "Fulham",
          sport_key: "soccer_epl",
          logo_small: "https://a.espncdn.com/i/teamlogos/soccer/500/370.png",
          primary_color: null,
          record: "0-2-3",
        },
      },
    });

    const out = await resolveTeamForRoute("fulham", "soccer", "epl", fetchTeam);

    expect(out.slug).toBe("fulham");
    expect(out.data.team.sport_key).toBe("soccer_fa_cup");
  });

  it("has nothing to try for a slug already carrying the suffix", () => {
    expect(teamRouteCandidates("arsenal-epl", "soccer", "epl")).toEqual([]);
    expect(sportKeyQualifiedSlug("arsenal-cup", "soccer", "fa_cup")).toBeNull();
  });
});

describe("#5852 — offLeague is measured, and offRoute is not widened", () => {
  it("reads the EFL Cup row as off-league on an EPL route, and NOT off-route", () => {
    const verdict = describeTeamRoute(
      { name: "Arsenal", sport_key: "soccer_england_efl_cup" },
      "soccer",
      "epl",
    );

    expect(verdict.offLeague).toBe(true);
    // The reader-facing notice is keyed on this one, and both rows are soccer.
    expect(verdict.offRoute).toBe(false);
  });

  it("stays silent when no league is supplied, so the share card's verdict is unchanged", () => {
    const verdict = describeTeamRoute(
      { name: "Arsenal", sport_key: "soccer_england_efl_cup" },
      "soccer",
    );

    expect(verdict.offLeague).toBe(false);
  });

  it("does not call an absent measurement off-league", () => {
    expect(describeTeamRoute({ name: "Arsenal" }, "soccer", "epl").offLeague).toBe(false);
    expect(describeTeamRoute(undefined, "soccer", "epl").offLeague).toBe(false);
    expect(
      describeTeamRoute({ name: "Arsenal", sport_key: "soccer_epl" }, "soccer", "  ").offLeague,
    ).toBe(false);
  });

  it("reads an alias route the way the link-builder wrote it", () => {
    expect(sportKeyForRoute("soccer", "ucl")).toBe("soccer_uefa_champs_league");
    expect(sportKeyForRoute("soccer", "fa_cup")).toBe("soccer_fa_cup");
    expect(sportKeyForRoute("football", "ncaaf")).toBe("americanfootball_ncaaf");
    expect(sportKeyForRoute("soccer", "")).toBeNull();
    // The UCL row on a UCL route is on-league, via that same alias.
    expect(
      describeTeamRoute(
        { name: "Arsenal", sport_key: "soccer_uefa_champs_league" },
        "soccer",
        "ucl",
      ).offLeague,
    ).toBe(false);
  });
});
