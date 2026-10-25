// #2311 — the team page's Prop Races say when they did not search the whole roster.
//
// `GET /api/teams/{team}/prop-families` finds player props by searching for
// roster names, and searches at most 40 of them (`_MAX_ROSTER_PATTERNS`). The
// Seahawks page served 2026-10-24 12:08:56Z searched 40 of 82. Any race whose
// only members are among the 42 unsearched names is absent, and until now the
// page gave no sign of it, so a capped answer read as a complete one.
//
// The backend has declared the cap since #2311's first half:
// `roster_search: {searched, total, truncated}`, omitted for rosterless teams.
// This module is the one reading of that field. It returns:
//
//   null         say nothing: the search covered every roster name, or the field
//                is absent (rosterless team, legacy payload) or not `truncated:
//                true`. Silence here is the page's existing state and claims
//                nothing either way; inventing a cap from a malformed field would.
//   "uncounted"  the search was capped, but the counts cannot be quoted: they are
//                malformed (searched >= total, non-integers, zero), or the build
//                is not `full`. A partial build can carry `searched: 40` while
//                the roster branch itself ran out of time, so "we checked 40"
//                would overstate what was searched. Absent `cache` is the build
//                that lost every branch, the same case.
//   "counted"    the search was capped and the counts are this build's own.
//
// `cache.quality: "full"` is used ONLY to trust the counts. It never means the
// whole roster was searched: a full build is still capped at 40 names.
//
// The caption names how many PLAYERS were checked, never how many rows or races
// exist: 40 checked names is not 40 players with markets.

import type { TeamPropFamiliesResponse } from "@/lib/api";

export type PropRosterCoverage =
  | { kind: "counted"; searched: number; total: number }
  | { kind: "uncounted" }
  | null;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function propRosterCoverage(
  response: Pick<TeamPropFamiliesResponse, "roster_search" | "cache"> | null | undefined,
): PropRosterCoverage {
  if (!isPlainObject(response)) return null;
  const search: unknown = response.roster_search;
  if (!isPlainObject(search) || search.truncated !== true) return null;

  const { searched, total } = search;
  const countsValid =
    typeof searched === "number" &&
    typeof total === "number" &&
    Number.isSafeInteger(searched) &&
    Number.isSafeInteger(total) &&
    searched > 0 &&
    searched < total;
  const cache: unknown = response.cache;
  const buildFull = isPlainObject(cache) && cache.quality === "full";

  if (countsValid && buildFull) {
    return { kind: "counted", searched: searched as number, total: total as number };
  }
  return { kind: "uncounted" };
}

// One short sentence, in the voice the tournament page's incomplete comparison
// already uses ("We have no number for …, so this comparison is not complete"):
// a fact about what we did, then what it means for the reader.
export function propRosterCoverageNote(coverage: PropRosterCoverage): string | null {
  if (coverage === null) return null;
  if (coverage.kind === "counted") {
    return `We checked ${coverage.searched} of the ${coverage.total} players on this roster, so some races may be missing.`;
  }
  return "We did not check every player on this roster, so some races may be missing.";
}
