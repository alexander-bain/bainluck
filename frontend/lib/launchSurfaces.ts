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
// Restoring: flip this to `true`. Nothing else is needed.
export const CHALLENGE_SURFACES_ENABLED = false;
