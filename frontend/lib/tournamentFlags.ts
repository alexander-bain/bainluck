/**
 * Tournament surface feature flags.
 *
 * INT-131 (Alex product call, 2026-08-26). The US Open board stack shipped the
 * night of main-draw Sunday with the props section OFF.
 *
 * WHY the flag exists rather than the section: CERT-411 returned **BLOCK** on
 * `program/ux-117 @ 8f702f17`, verified unchanged at `program/ux-118 @
 * 6ce45251`, and its finding is scoped entirely to
 * `components/tournament/TournamentProps.tsx` — the component derives a field
 * card's live state from only the answer/top outcome, so a specimen with a
 * fresh leader and a stale runner renders `data-live=true` beside a server
 * `data-price-state=dark`, with no stale age shown. That is the one thing the
 * boards must never do: claim a price is live when the server says it is dark.
 * The boards themselves passed their half of the review.
 *
 * So the section is not rendered. With it unrendered the finding is
 * unreachable by a user, and everything the cert cleared ships tonight.
 *
 * TO RE-ENABLE: this is deliberately an env read, not a constant, so the
 * section can come back without a code change once the props fix carries its
 * own GREEN — set `NEXT_PUBLIC_TOURNAMENT_PROPS=1` and redeploy. The lane's
 * fix should delete this module and its call site rather than flip the
 * default: a flag that is on everywhere is a flag nobody reads.
 *
 * Default is OFF. An unset, empty, or any non-`"1"` value is OFF — a flag that
 * fails open is not a flag (gotcha #53: an absent value is a value).
 */
export const TOURNAMENT_PROPS_ENABLED =
  process.env.NEXT_PUBLIC_TOURNAMENT_PROPS === "1";
