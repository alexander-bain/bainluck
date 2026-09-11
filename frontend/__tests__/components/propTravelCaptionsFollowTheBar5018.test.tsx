/**
 * ux/1189 (#5018) — THE CAPTIONS NAME THE END THEY SIT UNDER.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Live SF@LAR event page (`/events/14632820`), "What's moving", 2026-09-10
 * 6:32pm PT, 390px:
 *
 *     Stribling's 15+ receiving yards opened at 69% — it's 7% now.
 *     [======= red bar drawn from 7% to 69% =======]
 *     opened 69%                                    now 7%
 *
 * The bar's LEFT end is 7% and its RIGHT end is 69%. The caption on the left
 * said "opened 69%" and the caption on the right said "now 7%". Each label sat
 * under the opposite end of the thing it names.
 *
 * ═══ WHY IT SURVIVED ═══
 *
 * The track is drawn unordered — `from = min(pregameMark, current)`,
 * `to = max(...)` — while the captions were a fixed `justify-between` pair with
 * "opened" written first and therefore always on the left. For an UP move the
 * geometry happens to agree with that fixed order, so risers read correctly and
 * only fallers transpose. In the reported three-row frame two rows were wrong
 * and one was right, which is exactly the ratio that lets a bug like this sit
 * on a page nobody suspects.
 *
 * The tick marks inside the track were always positioned correctly, but at
 * phone width they are a 1px hairline and a 3px block with no labels of their
 * own. These two captions are the only thing a reader can actually read.
 *
 * `aria-label` was correct and direction-independent throughout, so a
 * screen-reader test could not have caught this either — it is visual only, and
 * it needs the rendered ORDER to be asserted.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropTravelBar from "@/components/PropTravelBar";
import type { DivergenceRow } from "@/lib/propDivergence";

function row(partial: Partial<DivergenceRow>): DivergenceRow {
  return {
    // Deliberately terse, and please leave it that way. Spelling the player
    // and market out here makes this field a long hyphenated string on an
    // identifier gitleaks treats as a keyword, and its default
    // `generic-api-key` rule then fires on entropy alone — which is exactly
    // how the first cut of this file failed CI (3.896, no secret involved).
    // The field is only a React key; `label` below carries the meaning.
    key: "row-1",
    label: "De'Zhaun Stribling: 15+ receiving yards",
    player: "De'Zhaun Stribling",
    stat: "receiving yards",
    threshold: 15,
    pregameMark: 0.69,
    current: 0.07,
    travel: 0.62,
    direction: "under",
    surprising: true,
    sentence: null,
    settled: false,
    pregame: false,
    conviction: 0.19,
    ...partial,
  } as unknown as DivergenceRow;
}

/**
 * Index of each VISIBLE caption in the rendered markup — order is the whole
 * assertion.
 *
 * The `aria-label` is stripped first, and that is not a detail: it reads
 * "…: opened at 69%, now 7%" and therefore contains both words, earlier in the
 * markup than the captions themselves. Measuring the raw string measures the
 * accessible sentence — which was never the bug and never moves — and reports
 * a fixed order no matter what the captions do.
 */
function captionOrder(r: DivergenceRow): { opened: number; now: number } {
  const html = renderToStaticMarkup(<PropTravelBar row={r} />).replace(
    /aria-label="[^"]*"/g,
    "",
  );
  const opened = html.indexOf("opened ");
  const now = html.indexOf("now ");
  // A missing caption would make every ordering assertion below vacuously
  // comparable against -1, so refuse that reading up front.
  expect(opened).toBeGreaterThan(-1);
  expect(now).toBeGreaterThan(-1);
  return { opened, now };
}

describe("#5018 a faller's captions are not transposed", () => {
  test("THE BUG: on a downward mover, 'now' is rendered before 'opened'", () => {
    // The reported specimen: opened 69%, now 7%, so the bar runs 7% -> 69% and
    // the LEFT end is `current`. This is the assertion that fails before the
    // fix, where "opened" was unconditionally first.
    const { opened, now } = captionOrder(row({ pregameMark: 0.69, current: 0.07 }));
    expect(now).toBeGreaterThan(-1);
    expect(opened).toBeGreaterThan(-1);
    expect(now).toBeLessThan(opened);
  });

  test("the second reported faller reads the same way", () => {
    const { opened, now } = captionOrder(row({ pregameMark: 0.57, current: 0.07 }));
    expect(now).toBeLessThan(opened);
  });

  test("both values still print, and print correctly", () => {
    // Reordering must not silently drop or swap the NUMBERS — the labels move,
    // the values they carry do not.
    const html = renderToStaticMarkup(
      <PropTravelBar row={row({ pregameMark: 0.69, current: 0.07 })} />,
    );
    expect(html).toContain("opened 69%");
    expect(html).toContain("now 7%");
  });
});

describe("#5018 a riser keeps the reading it already had", () => {
  test("on an upward mover, 'opened' stays first", () => {
    // Corum's 50+ rushing yards, the row in the same frame that was correct.
    // A fix that flipped everything would break this, and the frame would look
    // just as wrong to Alex as before.
    const { opened, now } = captionOrder(
      row({ pregameMark: 0.4, current: 0.82, direction: "over" }),
    );
    expect(opened).toBeLessThan(now);
  });

  test("a flat row is left alone", () => {
    // No travel to mis-describe; strict `<` keeps the natural reading order
    // rather than flipping on an equality.
    const { opened, now } = captionOrder(
      row({ pregameMark: 0.5, current: 0.5, direction: "flat", travel: 0 }),
    );
    expect(opened).toBeLessThan(now);
  });
});

describe("#5018 the caption order tracks the geometry it is captioning", () => {
  test("across a sweep, the left caption always names the left end of the bar", () => {
    // The property, rather than three examples of it: whichever value is
    // smaller is drawn at the left of the track, so its caption must come
    // first. This is what stops the next edit from re-introducing a fixed
    // order that happens to satisfy the cases above.
    const marks = [0.03, 0.2, 0.5, 0.77, 0.96];
    for (const pregameMark of marks) {
      for (const current of marks) {
        const { opened, now } = captionOrder(row({ pregameMark, current }));
        if (current < pregameMark) {
          expect(now).toBeLessThan(opened);
        } else {
          expect(opened).toBeLessThan(now);
        }
      }
    }
  });

  test("the accessible label stays direction-independent", () => {
    // It was already right and must not be 'fixed' into following the geometry:
    // a screen reader is read a sentence, not a track, and "opened at X, now Y"
    // is the correct sentence in both directions.
    const faller = renderToStaticMarkup(
      <PropTravelBar row={row({ pregameMark: 0.69, current: 0.07 })} />,
    );
    expect(faller).toContain("opened at 69%, now 7%");
  });
});
