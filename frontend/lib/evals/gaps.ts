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

import GAP_TARGETS_RAW from "@/lib/evals/data/gap-targets.json";
import { issueRef, pullRef, type RepoRef } from "@/lib/evals/truth";

export interface GapTargetEntry {
  issue: number;
  target: string | null;
}

export interface GapTargetsRecord {
  as_of: string;
  project_id: string;
  gaps: Record<string, GapTargetEntry>;
}

export const GAP_TARGETS: GapTargetsRecord = GAP_TARGETS_RAW;

export const GAPS_REVIEWED_AT = GAP_TARGETS.as_of;

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
  /** Target date (`YYYY-MM-DD`) on the owning issue's board item, or null when not scheduled yet. */
  target?: string | null;
  /** Present only when the fix is being built; names what it waits on. */
  planned?: { waitingOn: string; ref: RepoRef };
}

function targetFor(id: keyof typeof GAP_TARGETS_RAW.gaps): { ref: RepoRef; target: string | null } {
  const entry = GAP_TARGETS_RAW.gaps[id];
  return {
    ref: issueRef(entry.issue),
    target: entry.target,
  };
}

export const GAPS: readonly Gap[] = [
  {
    id: "combined-probability",
    text: "The combined probability on each card is not graded yet. We grade the sources it is made from, not the combined number itself.",
    ...targetFor("combined-probability"),
  },
  {
    id: "rare-pair-kinds",
    text: "For some kinds of matching pairs there are too few never-seen examples for the AI matcher to earn permission to decide on its own.",
    ...targetFor("rare-pair-kinds"),
  },
  {
    id: "code-reviewer",
    text: "The AI code reviewer's study is not finished, so how often it catches a hidden mistake is not known yet.",
    ...targetFor("code-reviewer"),
  },
  {
    id: "feed-reviewer",
    text: "The AI that looks over the top of the Discover feed each day has not been compared with people's judgments.",
    ...targetFor("feed-reviewer"),
  },
  {
    id: "ranking-grades",
    text: "No change to the order of the feed has been scored against people's grades.",
    ...targetFor("ranking-grades"),
    planned: { waitingOn: "the ranking scorer", ref: pullRef(12100) },
  },
  {
    id: "matching-audit",
    text: "Our full check of how markets are matched to events has no dated result since {since}.",
    dates: { since: "2026-07" },
    ...targetFor("matching-audit"),
  },
  {
    id: "time-before-result",
    text: "We do not yet show accuracy by how far ahead a forecast was made, such as a week or a day before the result.",
    ...targetFor("time-before-result"),
  },
  {
    id: "chance-failures",
    text: "Nothing measures how often a test fails by bad luck rather than a real problem.",
    ...targetFor("chance-failures"),
  },
];
