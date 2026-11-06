/**
 * EVERY WORD /evals SAYS TO A READER (#12102).
 *
 * One file so one test can hold all of it to the bans: `ALL_COPY_BANS` plus
 * `SUPPLIER_PROSE_BANS` from `lib/copyBans.ts`, plus the page's own rules in
 * `EVALS_COPY_RULES` below. The built bundle is scanned again by
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
    "AI agents write most of the code and most of the tests on this site, and other AI agents and Alex, who builds Bain Luck, check their work. That is why the tests matter. Every number here is marked LIVE, LAST RUN with its date, or PLANNED, and links to where it came from.",
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
];

/**
 * The page's own rules, on top of the site-wide bans.
 *
 * Narrower than a site-wide rule could be, because every string here is ours:
 * no venue writes /evals copy, so there is no market title for a broad pattern
 * to misfire on (the reason `FUTURE_PROMISE_BANS` cannot ban the bare word).
 */
export const EVALS_COPY_RULES: { id: string; pattern: RegExp; why: string }[] = [
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
