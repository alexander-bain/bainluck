/**
 * #8147 — THE SCRIPT TOLD A READER THE EVENT WAS OVER ON A PAGE BADGED
 * "STARTS IN 1 DAY".
 *
 * Production LOOK of `/event/golf/presidents-cup` at 390px on 2026-09-22,
 * during a notice-42 walk of the cup that starts the following day:
 *
 *   > GOLF   UPCOMING   STARTS IN 1 DAY
 *   > Presidents Cup
 *   > Sep 24 – Sep 27 · Medinah Country Club (No. 3) · Medinah, IL
 *   > …
 *   > THE SCRIPT  Props
 *   > What the market expected before the event.
 *
 * Both halves of that sentence are past tense, four rows under the page's own
 * badge saying the event has not started.
 *
 * ── WHY IT WAS NEVER TRUE, NOT MERELY WRONG HERE ─────────────────────────────
 *
 * `deriveState` sends "completed"/"closed"/"settled"/"final" to `graded` and
 * "live"/"in_progress"/"inprogress" to `divergence`. Everything else — which is
 * to say every event that has not started — falls through to `script`. Both
 * production callers pass the real status and no explicit `state`:
 *
 *   app/event/[domain]/[slug]/page.tsx:497   eventStatus={event.status}
 *   app/events/[id]/page.tsx:2723            eventStatus={event.status}
 *
 * So a live event gets THE DIVERGENCE and a settled one gets WHAT HIT, and the
 * past-tense sentence was shown to readers of upcoming events and to nobody
 * else. It could not be true in any render that produced it.
 *
 * ── WHAT THIS FILE GUARDS ────────────────────────────────────────────────────
 *
 * The tests below drive the component the way the pages do — by STATUS, never
 * by passing `state="script"` — so a future change that rewires `deriveState`
 * is caught here too, not just a change to the string. A test that hands the
 * component the state it is asserting about would be testing the branch it
 * chose rather than the branch production reaches (the fixture-is-an-input-the-
 * pipeline-cannot-produce class).
 *
 * The sibling states are asserted positively in the same pass, because the
 * failure this rules out in the other direction is a fix that "corrects" the
 * tense everywhere and leaves WHAT HIT describing a graded event in the
 * present.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

/** The production family from the Presidents Cup walk: a named field mark. */
const ROSTER_FIELD: PropMark[] = [
  {
    key: 58728412,
    label: "Golfers to compete in the Presidents Cup this year: Scottie Scheffler",
    question: "Golfers to compete in the Presidents Cup this year",
    kind: "field",
    outcomes: [
      { name: "Scottie Scheffler", probability: 0.995, opening_probability: 0.745 },
      { name: "Cameron Young", probability: 0.995, opening_probability: 0.805 },
      { name: "Sam Burns", probability: 0.995, opening_probability: 0.995 },
    ],
    pregame_mark: 0.745,
    current: 0.995,
    graded_result: null,
    settled: false,
  },
];

/** A plain binary list, so the rule is not read off one archetype. */
const BINARY: PropMark[] = [
  { key: 1, label: "Najee Harris: 10+", pregame_mark: 0.5, current: 0.52, graded_result: null },
  { key: 2, label: "Najee Harris: 15+", pregame_mark: 0.4, current: 0.44, graded_result: null },
];

function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function renderByStatus(items: PropMark[], eventStatus: string | null): string {
  return visibleText(renderToStaticMarkup(<PropsSection items={items} eventStatus={eventStatus} />));
}

describe("#8147 · THE SCRIPT speaks about an event that has not happened yet", () => {
  test("the Presidents Cup specimen: an upcoming event's props make no past-tense claim", () => {
    const text = renderByStatus(ROSTER_FIELD, "upcoming");

    expect(text).toContain("The script");
    expect(text).toContain("What the market expects before the event.");

    // The defect verbatim. Asserted as its own line so a regression names
    // itself rather than failing the positive assertion above ambiguously.
    expect(text).not.toContain("What the market expected before the event.");
    expect(text).not.toContain("expected before the event");
  });

  test("every status that reaches THE SCRIPT reaches the present tense", () => {
    // The statuses a not-yet-started event actually carries, plus the two
    // absent-value cases `deriveState` folds in. If a later change routes one
    // of these somewhere else, that is a different section and this fails.
    const upcomingish: (string | null)[] = ["upcoming", "scheduled", "pre", "", null];

    for (const status of upcomingish) {
      const text = renderByStatus(BINARY, status);
      expect(text).toContain("What the market expects before the event.");
      expect(text).not.toContain("expected before the event");
    }
  });

  test("CONTROL: the two states that describe a real past keep their own tense", () => {
    // A live event: the movement has happened, so the perfect tense is correct.
    const live = renderByStatus(BINARY, "live");
    expect(live).toContain("The divergence");
    expect(live).toContain("How far the live number has moved from the pregame script.");
    expect(live).not.toContain("What the market expects");

    // A settled one: the script is genuinely in the past and genuinely graded.
    const settled = renderByStatus(
      [{ ...BINARY[0], graded_result: "hit" }, { ...BINARY[1], graded_result: "miss" }],
      "settled",
    );
    expect(settled).toContain("What hit");
    expect(settled).toContain("The pregame script, graded.");
    expect(settled).not.toContain("What the market expects");
  });

  test("CONTROL: the fix is the blurb only — the section still renders its props", () => {
    const text = renderByStatus(ROSTER_FIELD, "upcoming");
    expect(text).toContain("Golfers to compete in the Presidents Cup this year");
    expect(text).toContain("Scottie Scheffler");
    expect(text).toContain("Cameron Young");
    expect(text).toContain("Sam Burns");
  });
});
