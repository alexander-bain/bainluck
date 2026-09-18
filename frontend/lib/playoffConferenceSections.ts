/**
 * #6999 — where a conference grid's conference name is allowed to be printed.
 *
 * `/playoffs/[sport]` draws a grouped grid as one section per conference, and
 * there are two places a name can land: the section `<h2>` above the card, and
 * the card's own `<h3>` (`ProgressionResponse.tournament_name`, rendered by
 * `TournamentProgressionTable`). The page used to hand `conf` to BOTH, so the
 * default view of the four biggest US grids printed e.g. "American Football
 * Conference" twice, 49px apart, at the same size and weight — eight duplicated
 * headings across /playoffs/nfl, /nba, /mlb and /nhl.
 *
 * It hid because it disappears on interaction: the `<h2>` is drawn only when
 * there is more than one section, so tapping a conference chip collapsed the
 * page to one section and left the card title alone, which reads correctly.
 * The duplicate lived exactly on the landing view.
 *
 * The rule is one decision, not two, and it lives here rather than at either
 * render site so the two can never drift into printing the name twice (or, the
 * failure on the other side, zero times):
 *
 *   more than one section -> the `<h2>` carries the conference; card title empty
 *   exactly one section   -> no `<h2>` is drawn; the card title carries it
 *
 * Either way the reader sees the conference named exactly once.
 *
 * Deliberately NOT the grid's own name (`"NFL Playoffs 2026-27"`) for the
 * multi-section case: that string restates the page's `<h1>` ("NFL Championship
 * Grid") and the season line directly beneath it, on every card — which trades
 * one adjacent duplicate for two distant ones rather than removing anything.
 */

/** One section's heading decision. */
export interface ConferenceSectionHeading {
  /** The conference key from `grouped_teams`. */
  conf: string;
  /**
   * The section `<h2>` text, or `null` when no section heading is drawn.
   * Null is the whole gate — render sites test this and nothing else.
   */
  label: string | null;
  /**
   * `ProgressionResponse.tournament_name` for this section's card. Empty string
   * suppresses the card's `<h3>` (the component guards on truthiness).
   */
  tournamentName: string;
}

/**
 * Resolve, for one grouped championship grid, which conference names get
 * printed and where.
 *
 * @param conferences conference keys, in the order `grouped_teams` serves them
 * @param conferenceFilter the active conference chip, or null for "All"
 */
export function conferenceSectionHeadings(
  conferences: readonly string[],
  conferenceFilter: string | null,
): ConferenceSectionHeading[] {
  const visible = conferences.filter(
    (conf) => !conferenceFilter || conf === conferenceFilter,
  );

  // The one decision. Both fields below are derived from it, in one expression
  // each, so a reader can see that the two render sites are complementary.
  const headingCarriesConference = visible.length > 1;

  return visible.map((conf) => ({
    conf,
    label: headingCarriesConference ? conf : null,
    tournamentName: headingCarriesConference ? "" : conf,
  }));
}
