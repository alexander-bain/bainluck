// My Stuff — the Awards & Players group (ux/1070 item 4).
//
// WHAT ALEX SAW (2026-09-04 7:00am shop): "Awards section: badly formatted, no
// player images."
//
// Both halves have one cause: the group renders the SAME row as "Other
// Markets" — a team crest, the outcome name, then the market name repeated
// underneath every single row. So the Red Sox block printed
//
//     [BOS] Trevor Story      AL MVP Winner? · 2026 · #22 of 30      1%
//     [BOS] Garrett Crochet   AL MVP Winner? · 2026 · #24 of 30      1%
//     [BOS] Jarren Duran      AL MVP Winner? · 2026 · #26 of 30      1%
//
// — three nominees for one award, each carrying a copy of the award's name and
// none carrying its own face. The card contract (#2910) says a row is the
// nominee, the number and the movement; the thing they have in common belongs
// in a heading above them, said once.
//
// This module is the pure half: it takes flat merged rows and returns them
// grouped by award, nominees ordered, with the face decision made once. The
// page renders it.

import { isLikelyPersonName } from "./eventConceptDisplay";

/** One merged award row as the page already has it. */
export interface AwardRowInput {
  key: string;
  marketId: number;
  marketName: string;
  outcomeName: string;
  teamName: string;
  seasonLabel?: string;
  probability: number | null;
  change: number | null;
  rank: number | null;
  totalOutcomes: number | null;
  sources: { source: string; probability: number | null }[];
}

export interface AwardNominee extends AwardRowInput {
  /** Whether this row names a PERSON and should wear a face. */
  showsFace: boolean;
}

export interface AwardGroup {
  /** The market the nominees are competing in — the row above them. */
  title: string;
  seasonLabel?: string;
  /** Stable react key + the link target for the heading. */
  marketId: number;
  nominees: AwardNominee[];
}

/**
 * Is this row a PERSON, or the team itself?
 *
 * A team-linked outcome on an award market is usually a player ("Trevor
 * Story"), but not always — "Pro Baseball Best Record" has an outcome called
 * "Boston", and pointing a Wikipedia headshot lookup at a team's short name
 * fetches a city.
 *
 * `isLikelyPersonName` warns against being used on award nominees, because a
 * film title's digits and colons are ordinary there and it rejects them. That
 * warning is about a MISSED face, and a missed face here is the crest the row
 * already wears — the same thing it showed before this change, never a wrong
 * one. Rejecting is the safe direction and it is the direction we take.
 */
export function nomineeShowsFace(
  outcomeName: string | null | undefined,
  teamName: string | null | undefined,
): boolean {
  const name = (outcomeName ?? "").trim();
  if (!name) return false;
  const team = (teamName ?? "").trim().toLowerCase();
  const lower = name.toLowerCase();
  // The team under its own name, or under the short form the books use
  // ("Boston" for "Boston Red Sox") — a crest, not a face.
  if (team && (lower === team || team.startsWith(lower + " ") || team.endsWith(" " + lower))) {
    return false;
  }
  return isLikelyPersonName(name);
}

/** Trim the season and the "Winner"/"?" chrome off an award's name. */
export function awardTitle(marketName: string | null | undefined): string {
  return (marketName ?? "")
    .replace(/\s*20\d{2}(-\d{2})?\s*/g, " ")
    .replace(/\s*Winner\s*\??\s*$/i, "")
    .replace(/\s*\?\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/**
 * Group flat award rows by the award they belong to.
 *
 * Groups keep the order of their FIRST row, which is the probability order the
 * page sorted them into — so the award a followed team is most likely to win
 * leads the section, exactly as the flat list did. Nominees inside a group are
 * ordered by probability, highest first, with unpriced rows last.
 */
export function groupAwardRows(rows: AwardRowInput[]): AwardGroup[] {
  const groups = new Map<number, AwardGroup>();
  for (const row of rows) {
    let group = groups.get(row.marketId);
    if (!group) {
      group = {
        title: awardTitle(row.marketName) || row.marketName,
        seasonLabel: row.seasonLabel,
        marketId: row.marketId,
        nominees: [],
      };
      groups.set(row.marketId, group);
    }
    group.seasonLabel = group.seasonLabel ?? row.seasonLabel;
    group.nominees.push({
      ...row,
      showsFace: nomineeShowsFace(row.outcomeName, row.teamName),
    });
  }
  for (const group of Array.from(groups.values())) {
    group.nominees.sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
  }
  return Array.from(groups.values());
}
