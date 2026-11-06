/**
 * "WHERE EVERY NUMBER COMES FROM" (#12102).
 *
 * Each entry names the sections that read it, and the list renders only
 * entries a section on the page uses, so a source arrives with the section
 * that needs it and never ahead of it (ruling 142). Two of the documents are
 * still open pull requests; until they merge, the page links the pull request,
 * as the plan on #11951 says.
 */

export type EvalsSectionId = "timeline" | "forward-record" | "gaps";

const REPO = "https://github.com/alexander-bain/bainluck";

export interface EvalsSource {
  id: string;
  /** What the reader clicks, in our own words. */
  label: string;
  /** Pacific calendar date of the document, rendered as a `<time>`; null for a live source. */
  date: string | null;
  /** Read when the page opens, not a dated document. */
  live?: boolean;
  href: string;
  usedBy: readonly EvalsSectionId[];
}

export const EVALS_SOURCES: readonly EvalsSource[] = [
  {
    id: "calibration-api",
    label: "The live calibration record",
    date: null,
    live: true,
    href: "https://api.bainluck.com/api/calibration",
    usedBy: ["forward-record"],
  },
  {
    id: "exam-run-2-receipt",
    label: "Twin exam, second run receipt",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6674874973`,
    usedBy: ["timeline"],
  },
  {
    id: "exam-receipt",
    label: "Twin exam receipt",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6673312127`,
    usedBy: ["timeline"],
  },
  {
    id: "exam-brief",
    label: "Twin exam brief, the first run's cost",
    date: "2026-11-04",
    href: `${REPO}/pull/11951#issuecomment-6650478138`,
    usedBy: ["timeline"],
  },
  {
    id: "calibration-exit-exam",
    label: "Calibration exit exam",
    date: "2026-08-13",
    href: `${REPO}/blob/91ae8c8e1c/docs/CALIBRATION-EXIT-EXAM.md`,
    usedBy: ["timeline"],
  },
  {
    id: "discover-exit-exam",
    label: "Discover exit exam, the interest baseline",
    date: "2026-08-10",
    href: `${REPO}/blob/3ae6db4fed/docs/DISCOVER-EXIT-EXAM.md`,
    usedBy: ["timeline"],
  },
  {
    id: "evals-story",
    label: "Evals story, the gaps section",
    date: "2026-11-03",
    href: `${REPO}/pull/11951`,
    usedBy: ["gaps"],
  },
  {
    id: "calibration-audit",
    label: "Calibration audit",
    date: "2026-11-03",
    href: `${REPO}/pull/11956`,
    usedBy: ["timeline", "gaps"],
  },
];

/** The sources the sections on the page actually read, in list order. */
export function sourcesFor(sections: readonly EvalsSectionId[]): EvalsSource[] {
  return EVALS_SOURCES.filter((s) => s.usedBy.some((id) => sections.includes(id)));
}
