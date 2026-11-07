/**
 * /evals' own copy rules, on top of the site-wide bans in `lib/copyBans.ts`.
 *
 * Test-only: the tests import this, the page never does, so these reasons —
 * which name the words they ban — stay out of the client bundle.
 */

import type { CopyBan } from "@/lib/copyBans";

/**
 * Narrower than a site-wide rule could be, because every string /evals renders
 * from `copy.ts` is ours: no venue writes it, so there is no market title for a
 * broad pattern to misfire on (the reason `FUTURE_PROMISE_BANS` cannot ban the
 * bare word).
 */
export const EVALS_COPY_RULES: CopyBan[] = [
  {
    id: "evals-question",
    pattern: /\bquestions?\b/i,
    why: 'the product\'s noun is "market"; "question" is reserved for an actual interrogative sentence',
  },
  {
    id: "evals-will",
    pattern: /\bwill\b/i,
    why: "no future tense in our voice: a section states what it is, not what it will be (ruling 142)",
  },
  {
    id: "evals-soon",
    pattern: /\b(soon|upcoming|later)\b/i,
    why: "a promise about later, not a statement about now (ruling 142)",
  },
];
