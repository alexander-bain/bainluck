/**
 * EVERY WORD /evals SAYS TO A READER (#12102).
 *
 * One file so one test can hold all of it to the bans: `ALL_COPY_BANS` plus
 * `SUPPLIER_PROSE_BANS` from `lib/copyBans.ts`, plus the page's own rules in
 * `lib/evals/copyRules.ts` (kept out of this module, because their reasons
 * name the very words they ban and this module ships to the browser). The built bundle is scanned again by
 * `shippedCopyBans.test.ts`, which is the check that proves what shipped.
 *
 * The voice follows `docs/design-system.md`: declarative, "we", sentence case,
 * US spelling ("license"). Each section has two lines, after the plan on #11951:
 * one a curious 13-year-old can follow (`lead`) and one for a reader who
 * evaluates systems for a living (`detail`).
 *
 * ═══ WHAT THIS FILE MAY NOT CONTAIN ═══
 *
 *   • A measured figure. Every number on the page renders through `Figure`
 *     from a committed record or a live payload; copy carries words only, and
 *     the page test fails on a digit outside a figure, a chip, a date or an
 *     issue link.
 *   • A sentence about a section that is not on the page yet. A section that
 *     is not built is absent, and its copy arrives with it (ruling 142).
 */

export const EVALS_PATH = "/evals";

export const EVALS_PAGE_TITLE = "How Bain Luck tests itself";

/** The browser tab reads "How we test | Bain Luck" through the root template. */
export const EVALS_TAB_TITLE = "How we test";

/** Share title, in the form `/calibration` uses ("Accuracy — Bain Luck"). */
export const EVALS_SHARE_TITLE = "How we test — Bain Luck";

export const EVALS_DESCRIPTION =
  "How Bain Luck tests the probabilities it shows, where each result comes from, and what we have not tested yet.";

export const HERO_COPY = {
  lead:
    "Every probability on this site has to pass tests. Some tests run by themselves every few hours, some are done by people, and some are exams for the site's AI helpers.",
  // Decide 43-J1 (Alex, Nov 5): say plainly that AI agents write most of the code.
  detail:
    "AI agents write most of the code and most of the tests on this site, and other AI agents and Alex, who builds Bain Luck, check their work. That is why the tests matter. Every number here is marked LIVE, LAST RUN with its date, or PLANNED, and links to where it came from; a list we keep by hand is marked LAST REVIEWED with its date.",
} as const;

/** The hero's tiles: each jumps to its section and carries its own label. */
export const HERO_TILE_COPY = {
  forwardTitle: "Forward record",
  forwardPointsAfter: "points off on average, across",
  forwardOutcomesAfter: "traded outcomes",
  unavailable: "Unavailable right now",
  loading: "Reading the live record",
  examTitle: "AI exam",
  examFoundBefore: "Found",
  examOf: "of",
  examFoundAfter: "twins it had never seen, but wrongly combined",
  examTo: "to",
  examCombinedAfter: "held-out pairs.",
  testsTitle: "Tests for the tests",
  testsOf: "of",
  testsCaughtAfter: "planted changes caught;",
  testsRealAfter: "built on the site's own code",
} as const;

export const EXAM_COPY = {
  title: "The twin exam and its gates",
  leadBefore: "Before the AI judge may file matches on its own, it has to pass every gate. Most are scored on pairs it has never seen. It passed",
  leadMiddle: "and failed",
  leadAfter: ", so a person still checks its work.",
  detail:
    "The bars were set before the run, in a ruling: a license for each kind of pair, plus gates every license shares. No wrong combining on held-out pairs, the same label in every pass, word-for-word quotes and no cut-off replies.",
  noLicense: "No license was granted, so a person still checks the judge's work.",
  passedPrefix: "Passed:",
  failedPrefix: "Failed:",
  gateHeading: "Gate",
  passHeadings: ["First pass", "Second pass", "Third pass"],
  acrossPasses: "Across all three passes",
  heldOutScope: "Held-out pairs",
  allScope: "Every reply",
  barBefore: "The bar for each gate was set before the run, in",
  barLink: "the ruling that set them",
  licensesTitle: "Licenses, by kind of pair",
  licensesNote: "HELD met its own numbers but waits on the shared gates and other checks; NOT ELIGIBLE has too few held-out examples to judge.",
} as const;

export const CONFUSION_COPY = {
  title: "Where the judge gets confused",
  lead: "It is very good at spotting twins and bad at saying when it cannot tell.",
  detail:
    "For each kind of pair: how many of them it found, and how often it was right when it used that label, each with its likely range, which holds the true rate nineteen times in twenty. Rare kinds get wide ranges, and the page draws them.",
  views: { test: "Held-out", dev: "Development", all: "All pairs" },
  passes: ["First pass", "Second pass", "Third pass"],
  viewLabel: "Which pairs",
  passLabel: "Which pass",
  found: "Found",
  right: "Right when it said so",
  none: "—",
  noneMeans: "It never used this label, so there is nothing to grade.",
  heldOutNote: "Held-out pairs stay sealed: only these counts are published, never the pairs.",
  lock: "Held-out",
} as const;

export const TIMELINE_COPY = {
  title: "Exams on the record",
  lead: "Each exam goes on this line with its date, what it cost and whether it passed.",
  detail:
    "AI runs name the model, the number of replies and the usage-rated cost; an exam done by hand says so. A mechanical failure is a result too.",
  byHand: "By hand",
  replies: "replies",
  usageRated: "usage-rated",
  includesPilot: "including the pilot",
  receipt: "Receipt",
} as const;

export const FORWARD_COPY = {
  title: "Do market probabilities come true?",
  lead:
    "When a market gives something a one-in-three chance, does it happen about one time in three? We check every source's probabilities against what actually happened.",
  detail:
    "This is the public record of each source's probabilities, graded against outcomes. It grades the sources each card's number is made from; the combined probability itself is not graded.",
  proofBefore: "Across",
  proofMiddle: "traded outcomes, the sources' probabilities land an average of",
  proofAfter: "points from what actually happened.",
  categoriesOf: "of",
  categoriesInside: "categories are inside the",
  categoriesBar: "point bar.",
  stagedBefore: "That data was last updated",
  builtBefore: "These numbers were built",
  unavailable: "Unavailable right now.",
  loading: "Reading the live record.",
  chartLabel: "Calibration curve for traded outcomes, from the live record",
  more: "See the full accuracy page",
} as const;

export const LIBRARY_COPY = {
  title: "The test library",
  lead: "We keep a library of small automatic tests. Each one feeds the site a tricky example and checks the answer.",
  detail:
    "Most of these tests check a simplified model of a decision the site makes, not the site's own code. The golden set is the exception: it runs real markets through the real matcher.",
  recordedBefore: "Results as recorded on",
  recordedAt: "at commit",
  checksIn: "checks in",
  families: "families.",
  olderAfter: "older test files came before the list of checks and are not counted in these families.",
  cases: "cases",
  casesAtLeast: "or more cases",
  checks: "checks",
  recordedRun: "Recorded run:",
  passed: "passed",
  failed: "failed",
  skipped: "skipped",
  unrecordedOf: "of its",
  unrecordedAfter: "checks have no recorded run.",
  unrecordedAfterOne: "checks has no recorded run.",
  goldenTitle: "Golden set",
  goldenGets: "The real matcher gets",
  goldenOf: "of",
  goldenAfter: "real markets right, sending each to its correct event or to none.",
  floorBefore: "The floor is",
  floorAfter: ": a change that lowers the count fails its check unless it names each market that stopped matching.",
} as const;

export const TESTS_FOR_TESTS_COPY = {
  title: "Tests for the tests",
  lead: "How do we know a test works? We plant a bug on purpose and see whether the test catches it.",
  detail:
    "A test that misses a planted bug is broken. We plant bugs two ways: small changes to the library's own cases, and real bugs from the site's past, planted again for the AI code reviewer.",
  biteTitle: "Planted changes",
  biteOf: "of",
  biteCaught: "caught",
  biteReal: "built on the site's own code",
  biteExplain: "We changed one thing in each case and checked that its test noticed.",
  biteNoneReal:
    "None of these cases runs the site's own code: each checks a simplified model of a decision. So a catch shows the test can fail, not that the site is right.",
  reviewerTitle: "The AI code reviewer, tested",
  reviewerLeadBefore: "We planted",
  reviewerLeadMiddle: "real bugs from the site's past again, with",
  reviewerLeadAfter: "healthy changes mixed in, to see whether the AI code reviewer can tell them apart.",
  reviewerOursAll:
    "Our own tests catch every planted bug and pass every healthy change. When these squares were recorded, the AI reviewer had not reviewed any of them, so each reads NOT RUN.",
  fullStudyBefore: "The reviews started after these squares were recorded. The full study's first result came in at",
  fullStudyAfter: ", and each new result follows it on the same thread:",
  fullStudyLink: "results so far",
  droppedBefore:
    "One more planted bug was left out: it was never fixed, so there is no healthy version of the code to plant it into. It is filed as",
  pickHint: "Tap a square to read what changed.",
  bug: "Planted bug",
  healthy: "Healthy change",
  bugsHeading: "Planted bugs",
  healthyHeading: "Healthy changes",
  ourTests: "Our tests",
  caught: "caught it",
  passedIt: "passed it",
  reviewer: "AI reviewer",
} as const;

export const GAPS_COPY = {
  title: "What we have not tested yet",
  lead: "This is what we have not checked.",
  detail: "Known gaps, each linked to its issue: the ones an outside reviewer would ask about first.",
} as const;

export const READING_COPY = {
  title: "How to read this page",
  lead: "LIVE means fresh right now. A date means the last time we ran it. PLANNED means not built yet, so there is no number.",
  detail:
    "Verdicts come from the record and are never recomputed for display. A FAIL shows as FAIL, with its partial passes under it. Held-out results appear as counts only.",
  labelsHeading: "Labels",
  resultsHeading: "Results",
  termsHeading: "Terms",
} as const;

export const SOURCES_COPY = {
  title: "Where every number comes from",
  lead: "Every number links to where it came from.",
  detail:
    "Receipts are public pull requests, runs and comments. Raw model replies and held-out answers stay private so the next exam is fair.",
  usedByPrefix: "Used in",
} as const;

/** The small words beside a chip and inside a link's accessible name. */
export const CHIP_COPY = {
  asOf: "as of",
  waitingOn: "waiting on",
  /** The legend shows the chip's shape with this word where a run's date goes. */
  sampleDate: "date",
  /** What prints where a date cannot be read — never a wrong date. */
  dateUnreadable: "date unreadable",
  /** A live source has no document date; this is when it is read. */
  readOnOpen: "live, read when the page opens",
  issue: "issue",
  pull: "pull request",
} as const;

/**
 * One line per truth chip, for the legend. "two weeks" is `AGE_AMBER_DAYS` in
 * words; `truth.test.ts` fails if the constant moves and this does not.
 */
export const TRUTH_CHIP_MEANING = {
  live: "Read from the site's live data when you opened this page. The time shown is the data's own, not your visit's. If the read fails, it says so instead of showing an old number.",
  last_run:
    "Read from a saved record of the last run. It shows the run's date and how long ago that was; after two weeks the age turns amber.",
  reviewed: "A list we keep by hand. The date is the last time we went through it.",
  planned: "Not built yet, so it shows no number. It names what it is waiting on.",
} as const;

export const RESULT_CHIP_MEANING = {
  pass: "Met the bar that was set before the run.",
  fail: "Missed the bar. A FAIL shows everywhere it applies, with any partial passes under it, never instead of it.",
  held: "Met its own numbers, but waits on something else before it counts.",
  not_run: "The test exists and has no result yet.",
  not_eligible: "Too few examples to judge.",
  unknown: "The record does not say.",
} as const;

/** Terms the page uses, in the order a reader meets them. */
export const TERMS: readonly { term: string; meaning: string }[] = [
  {
    term: "Combined probability",
    meaning:
      "The single probability a card shows for each outcome, made from the sources that have a number for it.",
  },
  {
    term: "Forward record",
    meaning:
      "Our public record of each source's probabilities, checked against what actually happened.",
  },
  {
    term: "AI judge",
    meaning:
      "A language model we ask whether two markets from different sources are the same market, so that their probabilities can be combined.",
  },
  {
    term: "License",
    meaning:
      "Permission for the AI judge to file one kind of match on its own, without a person checking it. Each kind has its own bar, set before the exam.",
  },
  {
    term: "Held-out",
    meaning:
      "Examples kept apart from the ones used to tune the AI judge, so its score on them is a fair test. We publish results on them as counts only.",
  },
  {
    term: "Receipt",
    meaning: "The public record a number comes from: a pull request, a test run or a posted comment.",
  },
  {
    term: "Traded outcomes",
    meaning:
      "Resolved outcomes whose probability moved after the market opened. The accuracy page shows these by default and sets the others aside.",
  },
  {
    term: "Usage-rated",
    meaning:
      "A model run's cost, computed from each reply's token usage at the provider's published rate rather than from an invoice.",
  },
  {
    term: "Case",
    meaning: "One example a test feeds in, with the answer the test expects.",
  },
  {
    term: "Golden set",
    meaning:
      "A fixed set of real markets, each with the event it belongs to or with none, that we run through the real matcher to check it.",
  },
  {
    term: "Twin",
    meaning: "Two markets from different sources that are the same market, so their probabilities can be combined.",
  },
  {
    term: "Likely range",
    meaning:
      "Where the true rate probably sits, given how few examples there were: a range wide enough to hold it in nineteen exams out of twenty.",
  },
  {
    term: "Planted bug",
    meaning: "A change made on purpose to break something, to check that a test or a reviewer notices.",
  },
];
