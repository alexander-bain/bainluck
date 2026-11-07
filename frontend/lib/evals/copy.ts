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

/**
 * The top screen (Alex, Nov 6): one plain answer and three pictures, before any
 * detail. Two readers: a smart friend with no AI or engineering background who
 * asks "so how do you know your numbers are any good?", and an interviewer at an
 * AI company. Nothing here may need the glossary: `topScreen.test.tsx` fails on
 * a jargon word anywhere outside a "Show the details" fold.
 */
export const TOP_COPY = {
  // Decide 43-J1 (Alex, Nov 5): say plainly that AI agents write most of the code.
  answer:
    "AI agents write most of this site's code, so we don't take its numbers on trust.",
  truthTitle: "Do our probabilities come true?",
  truthSaid: "What we said",
  truthHappened: "How often it happened",
  truthExampleBefore: "When we said",
  truthExampleMiddle: ", it happened",
  truthExampleClose: "of the time: our dots sit close to the line.",
  truthExampleFar: "of the time: our dots sit off the line.",
  truthExamplePlain: "of the time. On the line means it happened exactly as often as we said.",
  truthPlain: "Each dot is a group of past markets; on the line means it happened exactly as often as we said.",
  truthLoading: "Reading the live record",
  truthUnavailable: "Unavailable right now",
  truthPointsAfter: "points off on average",
  truthChartLabel:
    "How often things happened against the probability we gave them, one dot per group of past markets, on a grey line where the two are equal.",
  reviewerTitle: "Does our AI reviewer spot mistakes?",
  // Counts tries, as the topic's legend does ("Every one gets 3 tries"), so a
  // mistake caught on all three of its tries reads 3 of 3 above one green bug.
  reviewerCaughtBefore: "Caught the hidden mistake in",
  reviewerCaughtMiddle: "of",
  reviewerCaughtAfter: "tries so far",
  reviewerNoneChecked: "It has not tried any yet",
  reviewerHidBefore: "We hid",
  reviewerHidMiddle: "mistakes in real code changes, plus",
  reviewerHidAfter: "harmless decoys, to see what it flags; grey ones are not checked yet.",
  reviewerChartLabel:
    "One bug per hidden mistake, green when it was caught, red when it was missed, grey when not checked yet; one page per harmless decoy.",
  watchersTitle: "Are our automatic checks working?",
  watchersOf: "of",
  watchersWorkingAfter: "working",
  watchersSentenceStart: "Each alarm is an automatic check on the live site",
  watchersProblems: "red found problems, now on our work list",
  watchersFixed: "green found its problem fixed",
  watchersStopped: "grey found problems it could not report",
  watchersUnknown: "? has no public record",
  watchersChartLabel: "One alarm per automatic check, marked by what its newest run found.",
  fold: "Show the details",
} as const;

/**
 * The story below the top screen (Alex, Nov 6, 2:04 PM: "tell our ENTIRE story
 * to an interested party in approachable language"). The whole stack, one
 * chapter per step: a few plain sentences each, and at most a picture. No word
 * that needs the glossary and none of our internal names (`topScreen.test.tsx`).
 * The records behind every number sit in one fold at the bottom.
 *
 * The combining chapter states the weighting in `backend/app/utils/aggregation.py`:
 * betting 3.0, ESPN 1.5, our model 1.0, prediction markets 0.8 before a game;
 * in live play the two real-time markets carry betting's weight (Alex, Oct 31,
 * #10090 D); recency decay and a per-source share cap on top. Change the words
 * if those change.
 */
export const STORY_COPY = {
  sources: {
    title: "Where the numbers come from",
    paragraphs: [
      "Bain Luck doesn't make up its own odds. It reads them from betting sites and prediction markets, where people back their views with real money, and from a few sports forecasters.",
      "Every site writes its view its own way, so we turn each one into a plain probability that anyone can read.",
    ],
  },
  matching: {
    title: "Spotting the same thing on different sites",
    paragraphs: [
      "The same game shows up on many sites, under slightly different names and start times. Before we can put the numbers together, we have to be sure two listings are the same thing.",
      "For games we match on the teams, the start time and each site's own ID. When we can't be sure, we keep the two listings apart rather than risk mixing up two different games.",
      "Prediction markets are written as free text, so we tested an AI to pair them up, on examples it had never seen:",
    ],
  },
  combining: {
    title: "One number instead of many",
    paragraphs: [
      "When several sources cover the same outcome, we combine them into one probability: the one you see on each card.",
      "Before a game, betting sites count most, then sports forecasters, then our own statistical model, then the prediction markets. During a game the prediction markets, which update fastest, count as much as the betting sites. A reading that has gone old counts for less, and no single source can decide the number on its own.",
      "We grade every source against what really happened, below. We don't yet grade the combined number itself; it's on our list of what we haven't tested.",
    ],
  },
  comingTrue: {
    title: "Do our probabilities come true?",
    paragraphs: [
      "Every market ends: the team wins or it doesn't, the bill passes or it fails. We keep every finished market and check whether the things we gave a one-in-three chance happened about one time in three, and so on up the scale. The first picture at the top of this page is that check.",
    ],
  },
  code: {
    title: "Checking the code before it reaches you",
    paragraphs: [
      // Decide 43-J1 (Alex, Nov 5): say plainly that AI agents write most of the code.
      "AI agents write most of this site's code, so nothing goes live on trust. A change has to pass automatic tests before it ships, most changes are also read by an AI reviewer, and other AI agents and Alex, who builds Bain Luck, check the work.",
      "We also test the testers. A test only helps if it fails when something breaks, so we break things on purpose and check that a test notices. And we hide real mistakes from the site's past in code changes, to see whether the AI reviewer spots them.",
    ],
  },
  liveChecks: {
    title: "Watching the live site",
    paragraphs: [
      "Some checks run on their own around the clock, like smoke alarms. One makes sure every game on each league's official schedule is on the site, another that every big event has its page before it starts, another that the main things a reader does, like search, still work. Whatever they find goes straight onto our work list.",
      "A check that goes quiet is as bad as no check, so we show what each one last reported, and count a check with no public record as unknown, not fine.",
    ],
  },
  exampleLabel: "For example",
  exampleBetting: "A betting site",
  exampleMarket: "A prediction market",
  exampleUs: "On Bain Luck",
  exampleAriaBefore: "For example, odds of",
  exampleAriaMiddle: "on a betting site and a share costing",
  exampleAriaCents: "cents",
  exampleAriaAfter: "on a prediction market both mean a chance of",
  recordLead:
    "Every number on this page says whether it is LIVE, from the LAST RUN of a test, or from a list we LAST REVIEWED by hand, and links to where it came from. Work we have not built yet says PLANNED and shows no number.",
  recordSummary: "The full record: every test, every run and every source",
} as const;

/** The story's pictures: their sentences and labels. Like the story, nothing here may need the glossary. */
export const TOPIC_COPY = {
  probabilities: {
    kindsBefore: "We check each kind of market on its own too: sports, politics, weather and the rest.",
    kindsOf: "of",
    kindsInsideBefore: "kinds come within",
    kindsInsideAfter: "points of what happened.",
    kindsLabel: "One square per kind of market: green when its probabilities come close to what happened, red when they do not.",
  },
  matching: {
    failed: "It failed, so a person still checks every pair it suggests.",
    passed: "It passed, so it may decide on its own.",
    /** "three" is `PASSES.length` in words; the story test fails if one moves without the other. */
    triesBefore: "We showed it the same",
    triesAfter: "pairs it had never seen in three separate tries. Each time, it:",
    foundBefore: "found",
    foundOf: "of the",
    foundAfter: "pairs that were the same market",
    wrongBefore: "joined",
    wrongAfter: "pairs it should have kept apart",
    /** Between the fewest and the most when the tries differ: "2 or 3". */
    or: "or",
    /** The rule the red bar counts (the record's wrong_merges), and why it has to be zero. */
    why: "To decide on its own it has to keep every one of those pairs apart, because joining two different markets mixes them into one wrong number.",
    label: "Two bars from the AI's test: the pairs it found that were the same market, and the pairs it joined that it should have kept apart.",
  },
  reviewer: {
    legendBefore:
      "Each bug is a hidden mistake and each page a harmless decoy. Green means it made the right call, red the wrong one, and grey means it has not looked yet. Every one gets",
    legendAfter: "tries.",
  },
  tests: {
    caughtBefore: "Caught",
    caughtOf: "of",
    caughtAfter: "breakages we planted on purpose",
    honest:
      "These tests check simplified copies of the site's decisions rather than the live code, so a catch shows a test can fail, not that the site is right.",
    realOf: "of the",
    realAfter: "run the site's own code.",
    label: "One block per planted breakage, green when a test caught it.",
  },
  checks: {
    of: "of",
    workingAfter: "checks are working: their latest run is on the record and they are still reporting",
    legend: {
      problems: "found problems, now on our work list",
      fixed: "re-checked a problem and found it fixed",
      stopped: "found problems it could not report",
      unknown: "with no public record, so unknown",
    },
  },
} as const;

export const EXAM_COPY = {
  title: "The matcher's exam, test by test",
  leadBefore: "Before the AI matcher may decide on its own, it has to pass every test below. Most are scored on pairs it has never seen. It passed",
  leadMiddle: "and failed",
  leadAfter: ", so a person still checks its work.",
  detail:
    "The pass marks were set in writing before the exam: one for each kind of pair, plus tests every kind must also pass. No wrong matches on pairs it has never seen, the same answer on every try, quotes copied word for word, and no replies cut off mid-answer.",
  noLicense: "It may not decide on its own yet, so a person still checks every match.",
  passedPrefix: "Passed:",
  failedPrefix: "Failed:",
  gateHeading: "Test",
  passHeadings: ["First try", "Second try", "Third try"],
  acrossPasses: "Across all three tries",
  heldOutScope: "Pairs it had never seen",
  allScope: "Every reply",
  barBefore: "Every pass mark was fixed before the exam, in",
  barLink: "a written decision",
  licensesTitle: "Allowed to decide on its own, kind by kind",
  licensesNote: "HELD: it met that kind's own pass mark, but still waits on the tests every kind must pass. NOT ELIGIBLE: too few never-seen examples of that kind to judge.",
} as const;

export const CONFUSION_COPY = {
  title: "Where the matcher goes wrong",
  lead: "It is very good at spotting the same market on two sites, and bad at saying when it cannot tell.",
  detail:
    "For each kind of pair: how many it found, and how often it was right when it gave that answer, each with a likely range that holds the true rate nineteen times in twenty. Rare kinds get wide ranges, and the page draws them.",
  views: { test: "Never seen", dev: "Used for tuning", all: "All pairs" },
  passes: ["First try", "Second try", "Third try"],
  viewLabel: "Which pairs",
  passLabel: "Which try",
  found: "Found",
  right: "Right when it said so",
  none: "—",
  noneMeans: "It never gave this answer, so there is nothing to grade.",
  heldOutNote: "The never-seen pairs stay sealed: we publish these counts, never the pairs, so the next exam is still fair.",
  lock: "Never seen",
} as const;

export const TIMELINE_COPY = {
  title: "Exams on the record",
  lead: "Each exam goes on this line with its date, what it cost and whether it passed.",
  detail:
    "Each AI run names the model, how many replies it took and what it cost, worked out from usage at the published rates; an exam done by hand says so. A run that broke down counts as a result too.",
  byHand: "By hand",
  replies: "replies",
  usageRated: "at published rates",
  includesPilot: "including the trial run",
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
  categoriesInside: "kinds of market come within",
  categoriesBar: "points of what happened.",
  stagedBefore: "That data was last updated",
  builtBefore: "These numbers were built",
  unavailable: "Unavailable right now.",
  loading: "Reading the live record.",
  chartLabel: "How often traded outcomes happened against the probability the sources gave them, from the live record",
  more: "See the full accuracy page",
} as const;

export const LIBRARY_COPY = {
  title: "The test library",
  lead: "We keep a library of small automatic tests. Each one feeds the site a tricky example and checks the answer.",
  detail:
    "Most of these tests check a simplified copy of a decision the site makes, not the site's own code. The answer key is the exception: it runs real markets through the real matcher.",
  recordedBefore: "Results as recorded on",
  recordedAt: "on code version",
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
  goldenTitle: "Answer key",
  goldenGets: "The real matcher gets",
  goldenOf: "of",
  goldenAfter: "real markets right, sending each to its correct event or to none.",
  floorBefore: "It may not drop below",
  floorAfter: ": a change that lowers the count fails unless it names each market that stopped matching.",
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

export const WATCHERS_COPY = {
  title: "Checks that run on their own",
  lead:
    "Some checks run by themselves, like smoke detectors. Each one looks for one kind of problem on the live site and files it on our work list when it finds one.",
  detail:
    "An audit found a third state between working and stopped: a check that finds problems but cannot report them. We mark that “found problems, not reported”, and show it wherever the record says so.",
  timesNote: "Times are Pacific, worked out in your browser from the schedule's UTC times.",
  dayGroup: "Through the day",
  nightGroup: "Every night",
  every: "Every",
  minutes: "minutes",
  hours: "hours",
  everyDayAt: "Every day at",
  utc: "UTC",
  lastResult: "Last result",
  stateRedReporting: "Found problems, reported",
  stateRedStopped: "Found problems, not reported",
  stateClosedFixed: "Found its problem fixed",
  runBefore: "Its last run on record, at",
  filedAfter: "found problems and reported them on our work list:",
  stoppedAfter: "found problems but could not report them. The broken reporting is tracked in",
  closedOneAfter: "re-checked the problem it had reported, found it fixed, and closed it:",
  closedManyAfter: "re-checked the problems it had reported, found them fixed, and closed them:",
  alsoClosedBefore: "It also found",
  alsoClosedOneAfter: "fixed, and closed it.",
  alsoClosedManyAfter: "fixed, and closed them.",
  earlierBefore: "Its reporting had been stopped before that run:",
  fixBefore: "A fix for its reporting has merged since:",
  unknown: "No public record of its last result.",
  alerts: "See every open alert",
  code: "The check's code",
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
    "Results come straight from the record and are never worked out again for display. A FAIL shows as FAIL, with what it did pass listed under it. Results on never-seen examples appear as counts only.",
  labelsHeading: "Labels",
  resultsHeading: "Results",
  termsHeading: "Technical words, in plain English",
} as const;

export const SOURCES_COPY = {
  title: "Where every number comes from",
  lead: "Every number links to where it came from.",
  detail:
    "Each link goes to a public record: a code change, a test run or a posted comment. The AI's raw replies and the never-seen answers stay private, so the next exam is fair.",
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
  pass: "Met the pass mark set before the run.",
  fail: "Missed its pass mark. A FAIL shows everywhere it applies, with anything it did pass under it, never instead of it.",
  held: "Met its own numbers, but waits on something else before it counts.",
  not_run: "The test exists and has no result yet.",
  not_eligible: "Too few examples to judge.",
  unknown: "The record does not say.",
} as const;

/**
 * The technical words behind the plain ones, in the order a reader meets them.
 * The page itself says the plain word (Alex, Nov 6: "What's a twin?"); these
 * are for a reader who evaluates systems for a living, and for anyone who
 * follows a link into our records, which use the shorter names.
 */
export const TERMS: readonly { term: string; meaning: string }[] = [
  {
    term: "Calibration",
    meaning:
      "How well probabilities match what happens: things given a one-in-three chance should happen about one time in three. This page asks whether our probabilities come true.",
  },
  {
    term: "Traded outcomes",
    meaning:
      "Resolved outcomes whose probability moved after the market opened. The accuracy page shows these by default and sets the others aside.",
  },
  {
    term: "LLM judge",
    meaning:
      "A language model asked to make a call, here whether two markets from different sites are the same market. This page calls ours the AI matcher.",
  },
  {
    term: "Twin",
    meaning:
      "Our records' name for two markets from different sites that are the same market, so their probabilities can be combined.",
  },
  {
    term: "Gate",
    meaning: "Our records' name for one test in an exam, with a pass mark set before the run.",
  },
  {
    term: "License",
    meaning:
      "Our records' name for permission to decide on its own: the AI matcher may make one kind of match without a person checking it. Each kind has its own pass mark, set before the exam.",
  },
  {
    term: "Held-out set",
    meaning:
      "Examples kept apart from the ones used to tune the AI matcher, so its score on them is a fair test. This page calls them never seen, and publishes results on them as counts only.",
  },
  {
    term: "Recall",
    meaning: "Of the pairs of one kind, the share it found. This page says “Found”.",
  },
  {
    term: "Precision",
    meaning:
      "Of the times it gave an answer, the share that was right. This page says “Right when it said so”.",
  },
  {
    term: "Wilson interval",
    meaning:
      "Where a rate probably sits when there are few examples. This page calls it the likely range: wide enough to hold the true rate nineteen times in twenty.",
  },
  {
    term: "Usage-rated",
    meaning:
      "Our records' name for a cost worked out from each reply's token usage at the provider's published rates, rather than from an invoice.",
  },
  {
    term: "Mutation testing",
    meaning:
      "Changing something on purpose to check that a test or a reviewer notices. This page calls these planted changes and planted bugs.",
  },
  {
    term: "Case",
    meaning: "One example a test feeds in, with the answer the test expects.",
  },
  {
    term: "Golden set",
    meaning:
      "A fixed set of real markets, each with the event it belongs to or with none, that we run through the real matcher to check it. This page calls it the answer key.",
  },
  {
    term: "Sentinel",
    meaning:
      "Our records' name for an automatic check that runs on a schedule against the live site and puts what it finds on our work list.",
  },
  {
    term: "Running red, reporting stopped",
    meaning:
      "Our records' name for a check that keeps finding problems but cannot report them, so nobody sees them until someone looks. This page says “found problems, not reported”.",
  },
  {
    term: "Receipt",
    meaning: "The public record a number comes from: a pull request, a test run or a posted comment.",
  },
];
