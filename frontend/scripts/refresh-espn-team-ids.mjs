#!/usr/bin/env node
/**
 * #4911 — regenerate the pinned ESPN team-id fixture that guards `lib/images.ts`.
 *
 * The crest map in `lib/images.ts` holds ESPN team ids, and a wrong id renders another
 * club's crest rather than failing. This script re-reads ESPN's own team lists so the
 * guard (`__tests__/lib/espnTeamIdMap4911.test.ts`) is checking against the venue rather
 * than against whatever was typed in.
 *
 * Run it when a club is renamed, relocated, or added:
 *   node frontend/scripts/refresh-espn-team-ids.mjs
 *   npx jest --testPathPatterns=espnTeamIdMap4911
 *
 * Network is used HERE and never in the test — the test reads the committed fixture, so
 * CI stays hermetic and an ESPN outage can never redden the suite.
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const SOURCES = {
  nba: "basketball/nba",
  nfl: "football/nfl",
  mlb: "baseball/mlb",
  nhl: "hockey/nhl",
};

const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(here, "../__tests__/fixtures/espn-team-ids.json");

const out = {
  _comment:
    "ESPN's authoritative team ids, captured from site.api.espn.com. Regenerate with frontend/scripts/refresh-espn-team-ids.mjs. Guard: __tests__/lib/espnTeamIdMap4911.test.ts",
  _captured_utc: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  _source: SOURCES,
  teams: {},
};

for (const [sport, path] of Object.entries(SOURCES)) {
  const url = `https://site.api.espn.com/apis/site/v2/sports/${path}/teams?limit=100`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${sport}: ESPN returned HTTP ${res.status} for ${url}`);
  const body = await res.json();
  const teams = body?.sports?.[0]?.leagues?.[0]?.teams;
  if (!Array.isArray(teams) || teams.length === 0) {
    // An empty 200 is a response shape, not an absence — refuse to overwrite a good
    // fixture with nothing.
    throw new Error(`${sport}: ESPN returned no teams (shape change?) — fixture NOT written`);
  }
  out.teams[sport] = teams
    .map(({ team: t }) => ({
      id: t.id,
      displayName: t.displayName,
      abbreviation: t.abbreviation ?? null,
      shortDisplayName: t.shortDisplayName ?? null,
    }))
    .sort((a, b) => a.displayName.toLowerCase().localeCompare(b.displayName.toLowerCase()));
  console.log(`${sport}: ${out.teams[sport].length} teams`);
}

writeFileSync(OUT, `${JSON.stringify(out, null, 2)}\n`);
console.log(`wrote ${OUT}`);
