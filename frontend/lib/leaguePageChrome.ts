/**
 * leaguePageChrome — the league page's page-level decisions, as pure functions.
 *
 * UX-P062 (#1743), epic #1741, spec `docs/entity-page-templates.md` §3/§4/§6.
 *
 * ── WHY THIS IS A MODULE AND NOT JSX CONDITIONS ──
 *
 * Jest runs `testEnvironment: 'node'` here and neither jest-environment-jsdom nor
 * react-test-renderer is installed (the npm registry is unreachable in this
 * sandbox), so a decision expressed only as a JSX condition cannot be tested at
 * all. The lane's precedent is `lib/playerPropsGrouping.ts`: move the judgement out
 * of the component, and the component keeps only the rendering.
 *
 * These three decisions are exactly the ones that go wrong quietly — a page that
 * counts its own containers wrong grows a header over nothing, and a page that
 * conflates "degraded" with "empty" tells a reader the season is over when the
 * request failed.
 */

import type { EntityAvailability, EntityTier } from "./entityPageChrome";

/**
 * The grid slug for a league.
 *
 * Register E5: this logic used to be a `GRID_SLUG_MAP` literal inside the page.
 * The map now lives in `SPORT_HIERARCHY` and rides the hierarchy payload, so the
 * only client-side logic left is the fallback for leagues the register has no
 * grid for — derived from the sport key the way it always was.
 */
export function resolveGridSlug(
  registeredGridSlug: string | null | undefined,
  sportKey: string,
): string {
  if (registeredGridSlug) return registeredGridSlug;
  return sportKey.split("_").slice(1).join("_") || sportKey;
}

/**
 * How many CONTAINERS the page is actually rendering.
 *
 * This is the denominator for `earnsSectionHeader` (spec §4): a header needs
 * something to distinguish itself FROM, and "am I the only thing on this page?" is
 * a page-level question that no individual section can answer about itself.
 *
 * The grid and the two games rails count, because Alex's 2026-08-11 amendment
 * makes them first-class league content — the grid is the centerpiece, not an
 * extra.
 */
export function countRenderedSections(input: {
  marketSectionCount: number;
  upcomingGameCount: number;
  recentResultCount: number;
  gridTeamCount: number;
}): number {
  return (
    input.marketSectionCount +
    (input.upcomingGameCount > 0 ? 1 : 0) +
    (input.recentResultCount > 0 ? 1 : 0) +
    (input.gridTeamCount > 0 ? 1 : 0)
  );
}

/**
 * Which terminal state the page should render, if any.
 *
 * `degraded` and `present` are DIFFERENT STATES and the distinction is the whole
 * point (ruling 025 clause 4, register E6): an enrichment failure that renders as
 * an off-season is a plausible substitute served without declaration. One says
 * "nothing is happening", the other says "we failed to look".
 *
 * Returns null when the page has content to show — the terminal states are for
 * pages with nothing, never a footer under a full page.
 */
export function resolveLeagueTerminalState(input: {
  loaded: boolean;
  tier: EntityTier | null | undefined;
  availability: EntityAvailability | null | undefined;
  marketSectionCount: number;
  upcomingGameCount: number;
}): "degraded" | "present" | null {
  if (!input.loaded) return null;
  // Degraded wins over everything: we do not know what this league has.
  if (input.availability === "degraded") return "degraded";
  if (
    input.tier === "present" &&
    input.marketSectionCount === 0 &&
    input.upcomingGameCount === 0
  ) {
    return "present";
  }
  return null;
}
