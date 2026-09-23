// #6445 — SURFACES HELD BACK FOR THE INITIAL RELEASE.
//
// Alex, 2026-09-15, from the phone build: hide Today's Challenge altogether
// until it is good, including Discover's resolved-predictions banner and My
// Stuff's Predictions summary. What he met on the phone was a promotion with
// nothing behind it — "Play" led to "No challenge cards right now" — and a
// summary whose words wrapped into fragments.
//
// ── HIDDEN, NOT DELETED ─────────────────────────────────────────────────────
//
// Every guess a reader has already made stays in the database and stays on
// their account. Nothing here deletes a prediction, a streak or a history row,
// and nothing here writes. The feature's code is untouched and reachable the
// moment this constant flips — that is the whole reason it is a constant and
// not a removal. Alex's instruction was "until good", so restoring it is a
// product decision, not an archaeology exercise.
//
// ── ONE SWITCH, BECAUSE THE SURFACES ARE ONE FEATURE ────────────────────────
//
// The three things Alex named are the three faces of one loop: the tracker
// counts the guesses, the inline quiz slots ask them, the resolved banner
// reports them. Hiding a subset is worse than hiding none — a reader who is
// still asked "higher or lower?" but can no longer see a tally or a result has
// been handed a game with its feedback removed. So all of it moves together,
// off one constant, and `areGamesUnlocked` reads this before it reads anything
// about the reader.
//
// ── A FOURTH SITE, AND WHY THE SENTENCE BELOW CHANGED (#8187) ───────────────
//
// 🔴 THIS COMMENT USED TO END "Restoring: flip this to `true`. Nothing else is
// needed." That was FALSE WHEN IT WAS WRITTEN, in the direction that matters:
// a fourth entry point never read the constant at all, so switching the feature
// OFF did not close it. The Discover header carried an unlabelled 18px icon to
// `/discover/stats` — the most reachable door of the four, on the default
// landing page — and it survived two sweeps (#6501, #6646) that were looking
// for exactly this. The shopper lane found it on the first pass that opened it.
//
// The same sentence was false on the phone for the same reason, twice (the iOS
// `ReleaseSurfaces` docstring records sites 4–5 and then 6–7). The pattern is
// worth naming: a docstring asserting that one flag covers a class is a CENSUS
// QUESTION about that class, not an answer to it, and the call sites it has not
// counted are precisely the bug it claims cannot exist.
//
// So the claim is no longer load-bearing on its own. It is true because
// `predictionDoorsAreGated8187.test.ts` SCANS `app/` and `components/` for any
// navigation into the predictions route family and fails on one that does not
// read this constant. A fifth door fails that scan; it cannot fail this comment.
//
// Restoring: flip this to `true`. The scan above is what makes that enough.
export const CHALLENGE_SURFACES_ENABLED = false;
