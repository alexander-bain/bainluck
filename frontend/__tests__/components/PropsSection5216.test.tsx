// #5216 — a still-open window told the reader the words "script pending".
//
// WHAT A READER SAW, on a LIVE event page, mid-game:
//
//     Over 0.5 runs in the 6th        script pending   40%
//
// "Script pending" is our vocabulary for a hole in our own data. Standing notice
// 34 bans exactly that class of string from a reader's screen — "method notes…
// any sentence written to satisfy a reviewer or the bus" — and D102 sent the
// pregame-mark-missing rows behind a fold (#4530) for the same reason.
//
// NEWLY REACHABLE, which is why it is fixed now. Measured on
// `/api/events/15308050/game-markets`: ALL 64 window rows carry
// `pregame_mark: null`, so every window row is in this class. Until live/148's
// #5088, #1735 surfaced those rows only after full time — by which point the
// section state is `graded` and `DivergenceValue` never runs. #5088 put them on
// a LIVE page beside their settled siblings, in `divergence`, where it does.
// #5088's own guard file PINNED the string as expected ("exactly once, not
// twice"); this ship flips that count to 0, as #5216 asked it to.
//
// WHY NOT #4530's ANSWER (fold the row away): an open window mid-game has a live
// price a reader wants. Folding it hides real information. The right reading of
// notice 34 here is the other one — "if a number cannot be shown honestly, leave
// the space empty; do not explain the emptiness" — so the chip goes and the
// price stays.
//
// RED-FIRST, measured: against the parent commit this file scores 3 failed,
// 5 passed of 8. The five that pass there are the CONTROLs — the live price, the
// settled sibling's verdict, the row itself surviving, a marked row keeping its
// arrow, and a `pending_label` row keeping its sentence. That last one is the
// one that matters: `pending_label` is a DELIBERATE, plain-English, family-level
// answer (L2-123 / #199), not a hole, and this diff must not take it.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

/** An OPEN window mid-game: no pregame mark, a real live price. */
const OPEN_SIXTH: PropMark = {
  key: "Tampa Bay vs Atlanta: 6th Inning Total|Over 0.5 runs in the 6th inning",
  label: "Over 0.5 runs in the 6th inning",
  pregame_mark: null,
  current: 0.4,
};

/** Its settled sibling, the row #5088 exists to show. */
const CLOSED_FIRST_FIVE: PropMark = {
  key: "Tampa Bay vs Atlanta: First 5 Innings Total|Over 0.5 runs in the first 5 innings",
  label: "Over 0.5 runs in the first 5 innings",
  pregame_mark: null,
  current: null,
  graded_result: "hit",
  graded_label: "6–1 — hit",
  settled: true,
};

/** A row that DOES have a baseline — its arrow must survive untouched. */
const MARKED: PropMark = {
  key: "Tampa Bay vs Atlanta: 7th Inning Total|Over 0.5 runs in the 7th inning",
  label: "Over 0.5 runs in the 7th inning",
  pregame_mark: 0.62,
  current: 0.71,
};

const live = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);

describe("#5216 an open window explains nothing and shows its price", () => {
  test("THE FILED DEFECT: the words are gone", () => {
    expect(live([OPEN_SIXTH])).not.toContain("script pending");
  });

  test("CONTROL: the price a reader came for is still there", () => {
    expect(live([OPEN_SIXTH])).toContain("40%");
  });

  test("CONTROL: the row itself survives — this is not a fold and not a drop", () => {
    expect(live([OPEN_SIXTH])).toContain("Over 0.5");
  });

  test("no chip and no arrow — the slot is EMPTY, not filled with something else", () => {
    const html = live([OPEN_SIXTH]);
    expect(html).not.toContain("script pending");
    expect(html).not.toContain("pending");
    // The arrow belongs to a row that HAS a baseline to point away from.
    expect(html).not.toContain("→");
  });

  test("CONTROL: a marked row keeps its baseline and its arrow", () => {
    const html = live([MARKED]);
    expect(html).toContain("62%");
    expect(html).toContain("→");
    expect(html).toContain("71%");
  });

  test("CONTROL: a `pending_label` row keeps its sentence — that is an ANSWER", () => {
    // L2-123 / #199. A deliberate, plain-English, family-level line is not the
    // string this issue is about, and the two live one branch apart.
    const opensLater: PropMark = {
      ...OPEN_SIXTH,
      key: "Tampa Bay vs Atlanta: 6th Inning Total|Later",
      label: "Later",
      current: null,
      pending_label: "Opens after the 5th",
    };
    expect(live([opensLater])).toContain("Opens after the 5th");
  });

  test("the open and the settled row read correctly IN ONE SECTION", () => {
    const html = live([CLOSED_FIRST_FIVE, OPEN_SIXTH]);
    expect(html).toContain("6–1 — hit");
    expect(html).toContain("40%");
    expect(html).not.toContain("script pending");
  });

  test("CONTROL: the settled sibling still prints its verdict", () => {
    expect(live([CLOSED_FIRST_FIVE])).toContain("6–1 — hit");
  });
});
