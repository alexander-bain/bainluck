/**
 * #9785 — A GRID COLUMN THAT NAMES BOTH LEAGUES, PRINTED ON ONE TEAM'S CARD.
 *
 * MLB's `pennant` column is labelled `AL / NL Champ` in `league_configs.py`,
 * which is right on the league grid: that column really holds both pennants.
 * `RelatedFutures` copies the same label onto each team's CHAMPIONSHIP PATH,
 * where it is wrong — the Yankees can only win the American League. Production
 * 2026-09-30, `/events/15319563` at 390px: both cards read `AL / NL Champ 31%`
 * and `AL / NL Champ 5%`.
 *
 * The team block already carries `conference: "American League"`, so the half
 * is read from the payload, not guessed. Only a label of the exact shape
 * `A / B rest` narrows, and only to a half the conference's initials name; any
 * other label or conference comes back verbatim, so a column this rule has not
 * seen is never rewritten.
 */
const SPLIT_LABEL = /^(\S+) \/ (\S+) (.+)$/;

function initials(conference: string): string {
  return conference
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export function teamScopedColumnLabel(
  label: string,
  conference: string | null | undefined,
): string {
  const m = SPLIT_LABEL.exec(label);
  if (!m || !conference) return label;
  const abbr = initials(conference);
  const half = [m[1], m[2]].find((h) => h === abbr);
  return half ? `${half} ${m[3]}` : label;
}
