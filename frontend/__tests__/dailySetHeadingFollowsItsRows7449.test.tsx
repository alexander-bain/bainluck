/**
 * #7449 — THE DAILY CHALLENGE HEADED FIVE QUESTIONS "Today's Answers".
 *
 * Production, 2026-09-20 ~02:30 PDT, `bainluck.com/daily` at 390px signed out,
 * having played nothing — score `0/5`, progress `0/5`, "QUESTION 1 OF 5" on
 * screen — with a card in the sidebar reading:
 *
 *     Today's Answers
 *     1  Pittsburgh Pirates to win      MLB
 *     2  Los Angeles Dodgers            MLB
 *     3  Getafe to win                  La Liga - Spain
 *     4  J.D. Vance                     Politics
 *     5  Arizona Diamondbacks to win    MLB
 *
 * The card contained zero answers. Those are the five questions' subjects,
 * numbered 1–5, with the current one outlined — and row 1 is the subject of the
 * question being asked directly above it. A first-time reader gets "the game
 * spoiled itself" or "Pirates to win IS the answer to Q1"; neither is true.
 *
 * ═══ WHAT MAKES THIS TESTABLE AT ALL ═══
 *
 * 🪤 Every assertion here would have been GREEN ON THE BUG a day ago, because
 * the card lived inside `app/daily/page.tsx`: a page module may not carry a
 * second named export, the page builds its questions in a `useEffect` that
 * server rendering never runs, and this suite's environment is `node`. Lifting
 * the card into `components/daily/TodaysSetCard.tsx` is part of the fix, not
 * tidying — exactly as `DailyThresholdBox` was for #7004.
 *
 * 🪤 And the MAPPING is where the bug actually lives, not the markup. A suite
 * that renders hand-built rows tests a component nobody's data reaches. So
 * `toTodaysSetRows` — the function `page.tsx` calls, with the page's own
 * arguments — is what every state below is built through.
 *
 * ═══ THE THREE HOLES, CLOSED EXPLICITLY ═══
 *
 * 1. THE CHEAPEST WRONG FIX IS A RENAME. One honest-sounding static heading
 *    passes every past-tense assertion while being just as wrong at 5/5. So the
 *    two headings must DIFFER, and the answered one must be absent mid-set.
 *
 * 2. ABSENCE IS VACUOUS ON A DELETED CARD. `not.toContain("Today's Answers")`
 *    passes on a component that renders nothing, so every absence assertion is
 *    paired with the card still rendering all five subjects and its badges.
 *
 * 3. `completed` IS A COUNT AND THE ROWS ARE THE FACT. The page's `completed`
 *    is `answers.length >= questions.length`. `curateQuestions` drops a stored
 *    question whose market has closed and backfills from the live feed, so five
 *    stored answers can sit against a list one of them does not match. The
 *    load-bearing test is that specimen: five answers, `completed: true`, and a
 *    row still numbered — the heading must stay in its questions form. Anyone
 *    re-keying the heading on `completed` reds exactly that arm.
 */

import React from "react";
import fs from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";

import {
  TODAYS_SET_HEADING,
  TODAYS_SET_HEADING_ANSWERED,
  TodaysSetCard,
  categoryLabel,
  toTodaysSetRows,
  todaysSetIsAnswered,
  type TodaysSetRow,
} from "@/components/daily/TodaysSetCard";

/* ─────────────────────── the production specimen, verbatim ─────────────────────── */

const QUESTIONS = [
  { id: "event-1", subject: "Pittsburgh Pirates to win", category: "mlb" },
  { id: "event-2", subject: "Los Angeles Dodgers", category: "mlb" },
  { id: "event-3", subject: "Getafe to win", category: "soccer_spain_la_liga" },
  { id: "futures-4", subject: "J.D. Vance", category: "politics" },
  { id: "event-5", subject: "Arizona Diamondbacks to win", category: "mlb" },
] as const;

function answersFor(count: number, correct = true) {
  return QUESTIONS.slice(0, count).map((question) => ({
    questionId: question.id,
    correct,
  }));
}

function render(rows: readonly TodaysSetRow[]): string {
  return renderToStaticMarkup(<TodaysSetCard rows={rows} />);
}

/** The reader's eye: text with the tags taken out, entities decoded. */
function readable(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many rows still show a bare row number instead of a result mark. */
function numberedBadges(html: string): number {
  return (html.match(/data-row-answered="false"/g) ?? []).length;
}

/* ──────────────────────────── the defect, pinned ──────────────────────────── */

describe("the state Alex read: five questions, nothing played", () => {
  const rows = toTodaysSetRows(QUESTIONS, [], 0, false);
  const html = render(rows);
  const text = readable(html);

  it("does not head a card of questions with the word Answers", () => {
    expect(text).not.toContain("Today's Answers");
    expect(text).not.toContain("Answers");
  });

  it("heads it as the questions it is", () => {
    expect(text).toContain(TODAYS_SET_HEADING);
  });

  it("still lists all five subjects — the absence above is not a deleted card", () => {
    for (const question of QUESTIONS) {
      expect(text).toContain(question.subject);
    }
    expect((html.match(/data-testid="todays-set-row"/g) ?? [])).toHaveLength(5);
  });

  it("every badge is a row number, which is what made the old heading false", () => {
    expect(numberedBadges(html)).toBe(5);
    expect(html).not.toContain("data-row-answered=\"true\"");
  });

  it("the badges are 1..5 in order — the reader counts their way down the list", () => {
    // Not just "not a result mark": the numbers Alex read, in the order he read
    // them. A badge rendering `0` five times satisfies every count above.
    const badges = [...html.matchAll(/text-xs font-bold">([^<]*)</g)].map((m) => m[1]);
    expect(badges).toEqual(["1", "2", "3", "4", "5"]);
  });

  it("outlines the question being asked, and only that one", () => {
    expect(rows.filter((row) => row.current)).toHaveLength(1);
    expect(rows[0].current).toBe(true);
  });
});

/* ───────────────────────────── the other states ───────────────────────────── */

describe("part-way through the set", () => {
  const rows = toTodaysSetRows(QUESTIONS, answersFor(3), 3, false);
  const html = render(rows);
  const text = readable(html);

  it("is still headed as questions — three results do not make a card of answers", () => {
    expect(text).toContain(TODAYS_SET_HEADING);
    expect(text).not.toContain(TODAYS_SET_HEADING_ANSWERED);
  });

  it("shows three results and two numbers, so the card is genuinely mixed", () => {
    expect(numberedBadges(html)).toBe(2);
    expect((html.match(/data-row-answered="true"/g) ?? [])).toHaveLength(3);
  });

  it("outlines the fourth question", () => {
    expect(rows[3].current).toBe(true);
    expect(rows.filter((row) => row.current)).toHaveLength(1);
  });
});

describe("the set finished", () => {
  const rows = toTodaysSetRows(QUESTIONS, answersFor(5), 4, true);
  const html = render(rows);
  const text = readable(html);

  it("heads it with what it now holds", () => {
    expect(text).toContain(TODAYS_SET_HEADING_ANSWERED);
    expect(text).not.toContain(TODAYS_SET_HEADING);
  });

  it("no row is still a number, and all five are still listed", () => {
    expect(numberedBadges(html)).toBe(0);
    expect((html.match(/data-row-answered="true"/g) ?? [])).toHaveLength(5);
    for (const question of QUESTIONS) {
      expect(text).toContain(question.subject);
    }
  });

  it("nothing is outlined as current once there is nothing left to ask", () => {
    expect(rows.filter((row) => row.current)).toHaveLength(0);
  });

  it("marks right and wrong apart rather than crowning everything", () => {
    const mixed = toTodaysSetRows(
      QUESTIONS,
      QUESTIONS.map((question, index) => ({ questionId: question.id, correct: index < 2 })),
      4,
      true
    );
    expect(mixed.filter((row) => row.correct)).toHaveLength(2);
    const mixedHtml = render(mixed);
    expect(mixedHtml).toContain("text-accent-live");
    expect(mixedHtml).toContain("text-accent-danger");
  });
});

/* ── the load-bearing arm: the count and the rows disagree, and the rows win ── */

describe("five stored answers against a list one of them does not match", () => {
  /**
   * The reader answers all five. Question 3's market closes, so
   * `curateQuestions` cannot restore it from the feed and backfills a sixth
   * question in its place. `answers.length (5) >= questions.length (5)`, so the
   * page's `completed` is TRUE — while the list holds a question the reader was
   * never asked.
   */
  const questions = [
    QUESTIONS[0],
    QUESTIONS[1],
    QUESTIONS[3],
    QUESTIONS[4],
    { id: "event-6", subject: "Seattle Mariners to win", category: "mlb" },
  ];
  const answers = QUESTIONS.map((question) => ({ questionId: question.id, correct: true }));
  const rows = toTodaysSetRows(questions, answers, 4, true);
  const html = render(rows);
  const text = readable(html);

  it("the specimen really is the divergence — completed by count, incomplete by row", () => {
    expect(answers.length).toBeGreaterThanOrEqual(questions.length);
    expect(rows.filter((row) => !row.answered)).toHaveLength(1);
  });

  it("stays headed as questions, because one row is still a question", () => {
    expect(text).toContain(TODAYS_SET_HEADING);
    expect(text).not.toContain(TODAYS_SET_HEADING_ANSWERED);
    expect(numberedBadges(html)).toBe(1);
  });

  it("the backfilled question is the unanswered one, not some other row", () => {
    expect(rows[4].subject).toBe("Seattle Mariners to win");
    expect(rows[4].answered).toBe(false);
  });

  it("outlines nothing — the page is showing the summary, so nothing is being asked", () => {
    // `activeIndex` lands on this row and it IS unanswered, so only the
    // `!completed` clause keeps it from being outlined as the live question on
    // a card the page has already finished.
    expect(rows.filter((row) => row.current)).toHaveLength(0);
    expect(html).not.toContain("border-accent-brand");
  });
});

describe("a question that was answered is never outlined as the one being asked", () => {
  /**
   * The same closed-market backfill, caught mid-set: the reader has answered
   * three, so `activeIndex` is 3 — but the list's row 3 is a question they
   * already answered, because the dropped one sat earlier in the order.
   */
  const questions = [QUESTIONS[0], QUESTIONS[1], { id: "event-6", subject: "Seattle Mariners to win", category: "mlb" }, QUESTIONS[3], QUESTIONS[4]];
  const answers = [QUESTIONS[0], QUESTIONS[1], QUESTIONS[3]].map((q) => ({
    questionId: q.id,
    correct: true,
  }));
  const rows = toTodaysSetRows(questions, answers, 3, false);

  it("the specimen puts an answered row at activeIndex", () => {
    expect(rows[3].answered).toBe(true);
  });

  it("so no answered row carries the outline", () => {
    expect(rows.filter((row) => row.current && row.answered)).toHaveLength(0);
    expect(rows[3].current).toBe(false);
  });
});

/* ───────────────────────────── negative controls ───────────────────────────── */

describe("the rename is not the fix", () => {
  it("the two headings actually differ, so one cannot be doing both jobs", () => {
    expect(TODAYS_SET_HEADING).not.toBe(TODAYS_SET_HEADING_ANSWERED);
  });

  it("neither heading is the sentence that was wrong", () => {
    expect(TODAYS_SET_HEADING).not.toBe("Today's Answers");
    expect(TODAYS_SET_HEADING_ANSWERED).not.toBe("Today's Answers");
  });

  it("the unanswered and answered renders are not the same bytes", () => {
    const before = render(toTodaysSetRows(QUESTIONS, [], 0, false));
    const after = render(toTodaysSetRows(QUESTIONS, answersFor(5), 4, true));
    expect(before).not.toBe(after);
  });

  it("the heading's own state attribute tracks the rows", () => {
    expect(render(toTodaysSetRows(QUESTIONS, [], 0, false))).toContain(
      'data-set-answered="false"'
    );
    expect(render(toTodaysSetRows(QUESTIONS, answersFor(5), 4, true))).toContain(
      'data-set-answered="true"'
    );
  });
});

/* ───────────────────────────────  the predicate  ─────────────────────────────── */

describe("todaysSetIsAnswered", () => {
  const row = (answered: boolean): TodaysSetRow => ({
    id: `r-${answered}-${Math.random()}`,
    subject: "s",
    categoryLabel: "c",
    answered,
    correct: true,
    current: false,
  });

  it("is false while any row is unanswered", () => {
    expect(todaysSetIsAnswered([row(true), row(true), row(false)])).toBe(false);
    expect(todaysSetIsAnswered([row(false)])).toBe(false);
  });

  it("is true only when every row carries a result", () => {
    expect(todaysSetIsAnswered([row(true)])).toBe(true);
    expect(todaysSetIsAnswered([row(true), row(true)])).toBe(true);
  });

  it("an empty card reports nothing — `every` on [] is true and that is the trap", () => {
    expect(todaysSetIsAnswered([])).toBe(false);
    expect(readable(render([]))).toContain(TODAYS_SET_HEADING);
    expect(readable(render([]))).not.toContain(TODAYS_SET_HEADING_ANSWERED);
  });
});

describe("categoryLabel, moved out of the page so both call sites share one", () => {
  it("reads the sub-labels Alex saw", () => {
    // #1930 — "Mlb" is what Alex saw, and it is the bug: the labeler was
    // acronym-blind. MLB is the issue's own neighbour example, so the
    // expectation is corrected, not the product weakened.
    expect(categoryLabel({ category: "mlb" })).toBe("MLB");
    expect(categoryLabel({ category: "politics" })).toBe("Politics");
    expect(categoryLabel({ category: "soccer_spain_la_liga" })).toBe("Soccer Spain La Liga");
  });

  it("is what the rows carry", () => {
    const rows = toTodaysSetRows(QUESTIONS, [], 0, false);
    expect(rows[3].categoryLabel).toBe("Politics");
    expect(readable(render(rows))).toContain("Politics");
  });
});

/* ───────────────  the jargon heading above it, in the shipped bytes  ─────────────── */

/**
 * "Habit Loop" (page.tsx:545) is behavioural-design vocabulary describing what
 * the card is FOR to us — notice 34 / D102. It is three `Metric` tiles in the
 * page module, so there is no component to render; the honest guard is the
 * artifact. `.next/static/chunks` is the exact byte stream Vercel uploads and
 * CI runs `npm run build` before this suite, so under CI a missing directory is
 * a hard failure rather than a silent pass — the layer-2 shape
 * `__tests__/components/shippedCopyBans.test.ts` established for UX-P150.
 */
describe("the built bundle — the bytes Vercel uploads", () => {
  const dir = path.join(__dirname, "..", ".next", "static", "chunks");
  const present = fs.existsSync(dir);

  function bundleText(): string {
    const parts: string[] = [];
    const walk = (current: string) => {
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".js")) parts.push(fs.readFileSync(full, "utf8"));
      }
    };
    walk(dir);
    return parts.join("\n");
  }

  it("the build output exists, or CI has skipped its own gate", () => {
    if (present) {
      expect(present).toBe(true);
      return;
    }
    const message =
      "No .next/static/chunks — the shipped-copy scan did NOT run.\n" +
      "  Run `npm run build` first. This is the only layer that can see copy in a page module.";
    if (process.env.CI) throw new Error(message);
    console.warn(`\n⚠️  ${message}\n`);
  });

  (present ? it : it.skip)("ships neither the jargon heading nor the false one", () => {
    const bundle = bundleText();
    expect(bundle).not.toContain("Habit Loop");
    expect(bundle).not.toContain("Today's Answers");
  });

  (present ? it : it.skip)("and the scan can see /daily's copy at all", () => {
    // Absence proves nothing if the scan is reading the wrong bytes. These are
    // strings from the same two cards that MUST be there.
    const bundle = bundleText();
    expect(bundle).toContain("Your record");
    expect(bundle).toContain(TODAYS_SET_HEADING);
    expect(bundle).toContain(TODAYS_SET_HEADING_ANSWERED);
    expect(bundle).toContain("Next set in");
  });
});
