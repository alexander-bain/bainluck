import { CheckCircle2, XCircle } from "lucide-react";

/**
 * The Daily Challenge's progress list: today's five questions, each with the
 * reader's result once they have answered it.
 *
 * ═══ #7449 — A HEADING THAT CLAIMED A FIELD EVERY ROW WAS MISSING ═══
 *
 * This card used to be headed **"Today's Answers"**, unconditionally. On
 * 2026-09-20, `/daily` at 390px signed out, having played nothing — score
 * `0/5`, "QUESTION 1 OF 5" on screen — it listed five rows under that heading
 * and **not one of them was an answer**. They are the five questions' subjects,
 * numbered 1–5. Row 1, "Pittsburgh Pirates to win", is the subject of the
 * question being asked directly above it ("Is the probability higher or lower
 * than this? 62%"), so the two readings available to a first-time reader were
 * "the game has spoiled itself" and "Pirates to win IS the answer to Q1".
 * Neither is right and nothing on screen said so.
 *
 * The tell was in the card's own markup: `answer ? ✓/✗ : index + 1`. The badge
 * already knew the field was absent and rendered a row number instead, while
 * the heading above it went on claiming otherwise.
 *
 * ═══ WHY THE HEADING READS THE ROWS AND NOT `completed` ═══
 *
 * The heading is a claim about what is in THIS list, so the list is what
 * decides it — `todaysSetIsAnswered` counts rows, exactly as the badges do.
 * That is not a stylistic preference; the page's own `completed` flag is a
 * COUNT (`answers.length >= questions.length`) and the two provably disagree:
 *
 *   `curateQuestions` restores the day's questions by id from the live feed and
 *   silently drops any whose market has since closed (`asDailyQuestion` returns
 *   null for `completed`/`closed`), then backfills from the feed to keep five.
 *   Answer a question, watch its market close, and the reader ends the day with
 *   five stored answers against a list containing a question none of them
 *   match: `completed === true` with a row still showing its number.
 *
 * Keyed on `completed`, the heading would say "How you did" over a question the
 * reader was never asked. Keyed on the rows, it cannot.
 *
 * 🔴 The rename alone is the cheapest wrong fix. A single honest-sounding
 * static heading passes every past-tense assertion while being just as wrong in
 * the state that actually matters — so the two headings must differ and the
 * mid-set render must not contain the answered one. Both are tests.
 *
 * 🔴 It lives in its own file for the reason `DailyThresholdBox` does: a card
 * defined inside `app/daily/page.tsx` cannot be rendered by a test (a page
 * module may not carry a second named export), the page loads its questions in
 * a `useEffect` that server rendering never runs, and the suite's environment
 * is `node`. Rows are primitives — no page-local types — so it renders
 * standalone, and `toTodaysSetRows` is exported beside it so the guard tests
 * the mapping the page actually calls rather than a hand-built fake.
 */

export interface TodaysSetRow {
  id: string;
  subject: string;
  categoryLabel: string;
  /** The reader has answered this question. Drives the badge AND the heading. */
  answered: boolean;
  /** Only meaningful when `answered`. */
  correct: boolean;
  /** The question being asked right now. */
  current: boolean;
}

export const TODAYS_SET_HEADING = "Today's Questions";
export const TODAYS_SET_HEADING_ANSWERED = "How you did";

/**
 * True only when every row in the list carries a result — the same condition
 * the badges render on, so the heading and the badges cannot contradict each
 * other. An empty list is never "answered": a card with nothing in it has
 * nothing to report.
 */
export function todaysSetIsAnswered(rows: readonly TodaysSetRow[]): boolean {
  return rows.length > 0 && rows.every((row) => row.answered);
}

export function categoryLabel(question: { category: string }): string {
  return question.category
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * The page's questions and stored answers, joined into rows. Structurally
 * typed so `app/daily/page.tsx` can pass its own `DailyQuestion[]` and
 * `DailyAnswer[]` straight in without exporting either type from a page module.
 */
export function toTodaysSetRows(
  questions: readonly { id: string; subject: string; category: string }[],
  answers: readonly { questionId: string; correct: boolean }[],
  activeIndex: number,
  completed: boolean
): TodaysSetRow[] {
  return questions.map((question, index) => {
    const answer = answers.find((entry) => entry.questionId === question.id);
    return {
      id: question.id,
      subject: question.subject,
      categoryLabel: categoryLabel(question),
      answered: answer !== undefined,
      correct: answer?.correct === true,
      current: answer === undefined && index === activeIndex && !completed,
    };
  });
}

export function TodaysSetCard({ rows }: { rows: readonly TodaysSetRow[] }) {
  const answered = todaysSetIsAnswered(rows);

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4 shadow-sm">
      <p
        data-testid="todays-set-heading"
        data-set-answered={answered ? "true" : "false"}
        className="text-sm font-semibold"
      >
        {answered ? TODAYS_SET_HEADING_ANSWERED : TODAYS_SET_HEADING}
      </p>
      <div className="mt-3 space-y-2">
        {rows.map((row, index) => (
          <div
            key={row.id}
            data-testid="todays-set-row"
            data-row-answered={row.answered ? "true" : "false"}
            className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
              row.current
                ? "border-accent-brand bg-accent-brand/5"
                : "border-surface-border bg-surface-card"
            }`}
          >
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-elevated text-xs font-bold">
              {row.answered ? (
                row.correct ? (
                  <CheckCircle2 className="h-4 w-4 text-accent-live" />
                ) : (
                  <XCircle className="h-4 w-4 text-accent-danger" />
                )
              ) : (
                index + 1
              )}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold">{row.subject}</p>
              <p className="truncate text-[11px] text-text-muted">{row.categoryLabel}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default TodaysSetCard;
