/**
 * "WHERE EVERY NUMBER COMES FROM" (#12102, S1).
 *
 * Each entry names the sections that read it, and the list renders only
 * entries a section on the page uses, so a source arrives with the section
 * that needs it and never ahead of it (ruling 142). Two of the documents are
 * still open pull requests; until they merge, the page links the pull request,
 * as the plan on #11951 says.
 */

export type EvalsSectionId = "gaps";

const REPO = "https://github.com/alexander-bain/bainluck";

export interface EvalsSource {
  id: string;
  /** What the reader clicks, in our own words. */
  label: string;
  /** Pacific calendar date of the document, rendered as a `<time>`. */
  date: string;
  href: string;
  usedBy: readonly EvalsSectionId[];
}

export const EVALS_SOURCES: readonly EvalsSource[] = [
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
    usedBy: ["gaps"],
  },
];

/** The sources the sections on the page actually read, in list order. */
export function sourcesFor(sections: readonly EvalsSectionId[]): EvalsSource[] {
  return EVALS_SOURCES.filter((s) => s.usedBy.some((id) => sections.includes(id)));
}
