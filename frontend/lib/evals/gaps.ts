/**
 * "WHAT WE HAVE NOT TESTED YET" (#12102, S1) — the section an outside reviewer
 * trusts most, so it is the first one built.
 *
 * Sources, all public: the evals story's gaps (§4 of the doc on PR #11951), the
 * calibration audit (§5, §6 and §9 of the doc on PR #11956), the twin exam's
 * stated limits (#11951), and the license bars Alex set in Decide 24a-B.
 *
 * ═══ RULES FOR A ROW ═══
 *
 *   • Words only. A row that needs a measured figure gets it through `Figure`
 *     from the section whose record holds it, never typed here; a date is a
 *     `{placeholder}` that renders as a `<time>`.
 *   • Each row links the issue or pull request that owns the gap.
 *   • A row whose fix is being built carries a PLANNED chip that names what it
 *     waits on — present tense, no promise of a date (ruling 142).
 *   • `GAPS_REVIEWED_AT` moves only when someone has gone through every row
 *     again; it is the date the LAST REVIEWED chip prints.
 */

import { issueRef, pullRef, type RepoRef } from "@/lib/evals/truth";

export const GAPS_REVIEWED_AT = "2026-11-05";

export interface Gap {
  id: string;
  /**
   * Words only. A date goes in as `{name}` with its value in `dates`, so it
   * renders as a `<time>` the page test can tell from a typed number.
   */
  text: string;
  /** `YYYY-MM` or `YYYY-MM-DD` per `{name}` in `text`. */
  dates?: Record<string, string>;
  ref: RepoRef;
  /** Present only when the fix is being built; names what it waits on. */
  planned?: { waitingOn: string; ref: RepoRef };
}

export const GAPS: readonly Gap[] = [
  {
    id: "combined-probability",
    text: "The combined probability on each card is not graded. The forward record grades the sources it is made from, not the combined number.",
    ref: issueRef(11850),
  },
  {
    id: "rare-pair-kinds",
    text: "Some kinds of market pairs have too few held-out examples for the AI judge to earn a license on them.",
    ref: pullRef(11951),
  },
  {
    id: "code-reviewer",
    text: "The AI code reviewer's catch rate is not measured.",
    ref: pullRef(11951),
  },
  {
    id: "feed-reviewer",
    text: "The AI reviewer that looks at the top of the feed each day has not been checked against human labels.",
    ref: issueRef(587),
  },
  {
    id: "ranking-grades",
    text: "No change to the feed's ranking has been scored against human grades.",
    ref: issueRef(12095),
    planned: { waitingOn: "the ranking harness", ref: pullRef(12100) },
  },
  {
    id: "matching-audit",
    text: "Our four-layer matching audit has no dated result since {since}.",
    dates: { since: "2026-07" },
    ref: issueRef(2693),
  },
  {
    id: "time-before-result",
    text: "Accuracy by time before the result, such as a week or a day out, is not served.",
    ref: pullRef(11956),
  },
  {
    id: "chance-failures",
    text: "Nothing measures how often a test fails by chance.",
    ref: issueRef(11939),
  },
];
