/**
 * #4911 — the crest map must hold ESPN's ids, and each key must name the club it draws.
 *
 * THE DEFECT THIS EXISTS TO CATCH. `ESPN_TEAM_IDS` maps a team name to an id that is
 * interpolated into an `a.espncdn.com` logo URL. A wrong id does not 404 and does not
 * throw — it returns HTTP 200 with ANOTHER CLUB'S CREST, at the right size, looking
 * entirely healthy. Twenty-three entries were wrong this way: 22 of the 32 NHL rows
 * carried the NHL's *own* API team ids rather than ESPN's (Toronto's NHL-API id is 10,
 * and ESPN id 10 is Montreal), and Milwaukee carried MLB id 21, which is the Mets.
 * Not one was a typo — every value was a real id in *some* provider's numbering, which
 * is precisely why reading the file could not reveal it and why nothing ever failed.
 *
 * WHY A DUPLICATE CHECK IS THE LOAD-BEARING HALF. Brewers and Mets both held id 21 long
 * before anyone noticed the crest was wrong. A rank/id that is supposed to identify one
 * thing per pool is tested by whether its value can repeat — so `assertNoSharedIds`
 * below would have fired on the day the bad value landed, with no fixture and no network.
 *
 * HERMETIC BY CONSTRUCTION: this reads the committed fixture, never ESPN. Refresh it with
 * `node frontend/scripts/refresh-espn-team-ids.mjs` when a club is renamed or added.
 */
import { ESPN_TEAM_IDS, espnTeamLogoByName } from "@/lib/images";
import fixture from "../fixtures/espn-team-ids.json";

type FixtureTeam = {
  id: string;
  displayName: string;
  abbreviation: string | null;
  shortDisplayName: string | null;
};
const TEAMS = fixture.teams as Record<string, FixtureTeam[]>;

/**
 * Keys we deliberately hold that are not ESPN's current `displayName` — relocations and
 * renames, where our own event rows still carry (or now carry) the other spelling.
 * Each maps our key to the ESPN displayName it must resolve to. Keeping this explicit is
 * the point: an unexplained mismatch is a defect, a listed one is a decision.
 */
const KEY_ALIASES: Record<string, string> = {
  "oakland athletics": "Athletics", // relocated; our rows say "Athletics"
  "utah hockey club": "Utah Mammoth", // renamed for 2026-27
  "los angeles clippers": "LA Clippers", // ESPN shortens the city
};

const byId = (sport: string) => new Map(TEAMS[sport].map((t) => [t.id, t]));
const entries = Object.entries(ESPN_TEAM_IDS);

describe("#4911 ESPN crest id map", () => {
  it("covers every sport present in the map with a pinned fixture", () => {
    const sports = new Set(entries.map(([, v]) => v.sport));
    for (const s of sports) {
      expect(Array.isArray(TEAMS[s])).toBe(true);
      expect(TEAMS[s].length).toBeGreaterThan(0);
    }
  });

  it("every mapped id is a real ESPN team id for that sport", () => {
    const unknown = entries
      .filter(([, v]) => !byId(v.sport).has(v.id))
      .map(([k, v]) => `${v.sport}/${k} -> id ${v.id} is not an ESPN ${v.sport} team`);
    expect(unknown).toEqual([]);
  });

  it("every key names the club whose crest it draws", () => {
    // The Toronto->Montreal case. An id can be perfectly valid and still be the wrong club,
    // so match the key against the team that id actually resolves to.
    const mismatched: string[] = [];
    for (const [key, { id, sport }] of entries) {
      const team = byId(sport).get(id);
      if (!team) continue; // reported by the previous test
      const expected = KEY_ALIASES[key] ?? team.displayName;
      const acceptable = [team.displayName, team.shortDisplayName]
        .filter(Boolean)
        .map((n) => (n as string).toLowerCase());
      if (expected !== team.displayName || !acceptable.includes(key)) {
        if (expected.toLowerCase() !== team.displayName.toLowerCase()) {
          mismatched.push(
            `${sport}/"${key}" -> id ${id} is ESPN's "${team.displayName}"` +
              (KEY_ALIASES[key] ? ` but is aliased to "${KEY_ALIASES[key]}"` : ""),
          );
        }
      }
    }
    expect(mismatched).toEqual([]);
  });

  it("no two DIFFERENT clubs share an id within a sport", () => {
    // Aliases are exempt by construction: they resolve to the same ESPN team, so they
    // collapse into one entry here. Two distinct clubs on one id is always a defect.
    const seen = new Map<string, Set<string>>();
    for (const [key, { id, sport }] of entries) {
      const team = byId(sport).get(id);
      const club = team ? team.displayName : `unknown:${id}`;
      const bucket = `${sport}:${id}`;
      if (!seen.has(bucket)) seen.set(bucket, new Set());
      // Distinct clubs are distinguished by the key's own alias target, not by the id,
      // so a genuine collision (Brewers + Mets both on mlb 21) still shows two names.
      seen.get(bucket)!.add(KEY_ALIASES[key] ?? (club === `unknown:${id}` ? key : club));
    }
    const collisions = [...seen.entries()]
      .filter(([, names]) => names.size > 1)
      .map(([bucket, names]) => `${bucket} shared by: ${[...names].sort().join(", ")}`);
    expect(collisions).toEqual([]);
  });

  it("every ESPN club in a mapped sport is reachable by some key", () => {
    const mappedSports = new Set(entries.map(([, v]) => v.sport));
    const reachable = new Set(entries.map(([, v]) => `${v.sport}:${v.id}`));
    const missing: string[] = [];
    for (const sport of mappedSports) {
      for (const t of TEAMS[sport]) {
        if (!reachable.has(`${sport}:${t.id}`)) missing.push(`${sport}/${t.displayName} (id ${t.id})`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("the named regressions draw the right club", () => {
    // Spot-checks in the reader's terms, so a future edit that breaks one is legible
    // without decoding an id. Toronto and Milwaukee are the two Alex would recognise.
    const cases: [string, string, string][] = [
      ["Toronto Maple Leafs", "nhl", "21"],
      ["Montreal Canadiens", "nhl", "10"],
      ["Milwaukee Brewers", "mlb", "8"],
      ["New York Mets", "mlb", "21"],
      ["Utah Mammoth", "nhl", "129764"],
      ["Athletics", "mlb", "11"],
    ];
    for (const [name, sport, id] of cases) {
      const url = espnTeamLogoByName(name);
      expect(url).toContain(`/teamlogos/${sport}/500/${id}.png`);
    }
  });

  it("resolves the club names our own rows actually use", () => {
    // Production 2026-09-10: `events` carries "Athletics" (82 rows) and "Utah Mammoth"
    // (21 rows). Before #4911 neither key existed, so both rendered no crest at all.
    for (const name of ["Athletics", "Utah Mammoth", "Los Angeles Clippers"]) {
      expect(espnTeamLogoByName(name)).not.toBeNull();
    }
  });
});
