/**
 * "WHERE EVERY NUMBER COMES FROM" (#12102).
 *
 * Each entry names the sections that read it, and the list renders only
 * entries a section on the page uses, so a source arrives with the section
 * that needs it and never ahead of it (ruling 142). Two of the documents are
 * still open pull requests; until they merge, the page links the pull request,
 * as the plan on #11951 says.
 */

export type EvalsSectionId =
  | "exam"
  | "confusion"
  | "timeline"
  | "forward-record"
  | "test-library"
  | "tests-for-tests"
  | "watchers"
  | "gaps";

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
    label: "Matcher exam, second run results",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6674874973`,
    usedBy: ["timeline"],
  },
  {
    id: "exam-receipt",
    label: "Matcher exam results",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6673312127`,
    usedBy: ["exam", "confusion", "timeline"],
  },
  {
    id: "exam-record",
    label: "Matcher exam record, from the scoring script",
    date: "2026-11-05",
    href: `${REPO}/blob/1a600e1b17/frontend/lib/evals/data/twin-exam-2026-11-05.json`,
    usedBy: ["exam", "confusion"],
  },
  {
    id: "ruling-24a",
    label: "The written decision that set the exam's pass marks",
    date: "2026-11-04",
    href: `${REPO}/pull/11951#issuecomment-6650890360`,
    usedBy: ["exam"],
  },
  {
    id: "exam-brief",
    label: "Matcher exam brief, the first run's cost",
    date: "2026-11-04",
    href: `${REPO}/pull/11951#issuecomment-6650478138`,
    usedBy: ["timeline"],
  },
  {
    id: "calibration-exit-exam",
    label: "The accuracy page's final exam",
    date: "2026-08-13",
    href: `${REPO}/blob/91ae8c8e1c/docs/CALIBRATION-EXIT-EXAM.md`,
    usedBy: ["timeline"],
  },
  {
    id: "discover-exit-exam",
    label: "Discover's final exam, the first interest measure",
    date: "2026-08-10",
    href: `${REPO}/blob/3ae6db4fed/docs/DISCOVER-EXIT-EXAM.md`,
    usedBy: ["timeline"],
  },
  {
    id: "scoreboard-record",
    label: "The test library's scoreboard record",
    date: "2026-11-03",
    href: `${REPO}/blob/82b61ab815/backend/scripts/evals/scoreboard_record.json`,
    usedBy: ["test-library"],
  },
  {
    id: "golden-baseline",
    label: "The answer key's recorded count",
    date: "2026-11-03",
    href: `${REPO}/blob/54470c89fd/backend/tests/fixtures/matching_golden_baseline.json`,
    usedBy: ["test-library"],
  },
  {
    id: "bite-audit",
    label: "The planted-change audit's test",
    date: "2026-11-03",
    href: `${REPO}/blob/54470c89fd/backend/tests/evals/test_eval_bite_rate_audit.py`,
    usedBy: ["test-library"],
  },
  {
    id: "reviewer-study",
    label: "Reviewer study receipt",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6673378524`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "reviewer-pilot",
    label: "Reviewer pilot, before its first review",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6674832482`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "reviewer-full-study",
    label: "Reviewer study, the full study's first result",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6679966474`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "reviewer-study-plan",
    label: "Reviewer study, the plan: every case, three tries",
    date: "2026-11-06",
    href: `${REPO}/pull/11951#issuecomment-6687948343`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "reviewer-study-count",
    label: "Reviewer study, the latest count",
    date: "2026-11-06",
    href: `${REPO}/pull/11951#issuecomment-6692550759`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "reviewer-dropped",
    label: "Why one planted bug was left out",
    date: "2026-11-05",
    href: `${REPO}/pull/11951#issuecomment-6673535640`,
    usedBy: ["tests-for-tests"],
  },
  {
    id: "beat-schedule",
    label: "The production schedule",
    date: "2026-11-05",
    href: `${REPO}/blob/80b7a1605c/backend/app/tasks/__init__.py`,
    usedBy: ["watchers"],
  },
  {
    id: "quiet-evals-audit",
    label: "Audit of checks that went quiet",
    date: "2026-11-03",
    href: `${REPO}/blob/82b61ab815/docs/evals/QUIET-EVALS-2026-11.md`,
    usedBy: ["watchers"],
  },
  // Each watcher's newest run on the public record (S5): its first post on GitHub.
  {
    id: "data-quality-watchdog-newest-run",
    label: "Data-quality watchdog, newest run on GitHub",
    date: "2026-11-06",
    href: `${REPO}/issues/4057#issuecomment-6685169500`,
    usedBy: ["watchers"],
  },
  {
    id: "matching-reconciliation-newest-run",
    label: "Matching check, newest run on GitHub",
    date: "2026-11-06",
    href: `${REPO}/issues/12144#issuecomment-6686664159`,
    usedBy: ["watchers"],
  },
  {
    id: "anchor-schedule-sentinel-daily-newest-run",
    label: "Kickoff-time check, newest run on GitHub",
    date: "2026-11-05",
    href: `${REPO}/issues/2978#issuecomment-6678966061`,
    usedBy: ["watchers"],
  },
  {
    id: "flow-sentinel-daily-newest-run",
    label: "Reader-flow check, newest run on GitHub",
    date: "2026-11-05",
    href: `${REPO}/issues/12071#issuecomment-6679506737`,
    usedBy: ["watchers"],
  },
  {
    id: "grid-sentinel-daily-newest-run",
    label: "Championship-grid check, newest run on GitHub",
    date: "2026-11-05",
    href: `${REPO}/issues/12074#issuecomment-6679867488`,
    usedBy: ["watchers"],
  },
  {
    id: "tournament-register-sentinel-daily-newest-run",
    label: "Tournament list check, newest run on GitHub",
    date: "2026-11-05",
    href: `${REPO}/issues/4231#issuecomment-6680051792`,
    usedBy: ["watchers"],
  },
  {
    id: "horizon-sentinel-daily-newest-run",
    label: "Big-event check, newest run on GitHub",
    date: "2026-11-05",
    href: `${REPO}/issues/12135`,
    usedBy: ["watchers"],
  },
  {
    id: "board-sentinel-daily-newest-run",
    label: "Work-list check, newest run on GitHub",
    date: "2026-11-06",
    href: `${REPO}/issues/1449#issuecomment-6680233836`,
    usedBy: ["watchers"],
  },
  {
    id: "schedule-sentinel-daily-newest-run",
    label: "Schedule check, newest run on GitHub",
    date: "2026-11-06",
    href: `${REPO}/issues/10783#issuecomment-6680257276`,
    usedBy: ["watchers"],
  },
  // End of the watchers' newest runs.
  {
    id: "flow-reporting-again",
    label: "Reader-flow check, reporting again",
    date: "2026-11-05",
    href: `${REPO}/issues/11960#issuecomment-6674619173`,
    usedBy: ["watchers"],
  },
  {
    id: "grid-reporting-again",
    label: "Championship-grid check, reporting again",
    date: "2026-11-05",
    href: `${REPO}/issues/11959#issuecomment-6674618887`,
    usedBy: ["watchers"],
  },
  {
    id: "matching-reporting-fix",
    label: "Matching check, why its reporting stopped",
    date: "2026-11-05",
    href: `${REPO}/issues/11958#issuecomment-6674619473`,
    usedBy: ["watchers"],
  },
  {
    id: "evals-story",
    label: "The plan for this page, its gaps section",
    date: "2026-11-03",
    href: `${REPO}/pull/11951`,
    usedBy: ["gaps"],
  },
  {
    id: "calibration-audit",
    label: "Accuracy audit",
    date: "2026-11-03",
    href: `${REPO}/pull/11956`,
    usedBy: ["timeline", "gaps"],
  },
];

/** The sources the sections on the page actually read, in list order. */
export function sourcesFor(sections: readonly EvalsSectionId[]): EvalsSource[] {
  return EVALS_SOURCES.filter((s) => s.usedBy.some((id) => sections.includes(id)));
}

/** One source's link, by id, for a figure or a chip. Throws on an unknown id, so a typo fails the build's tests. */
export function sourceLink(id: string): { label: string; href: string } {
  const source = EVALS_SOURCES.find((s) => s.id === id);
  if (!source) throw new Error(`no evals source "${id}"`);
  return { label: source.label, href: source.href };
}
