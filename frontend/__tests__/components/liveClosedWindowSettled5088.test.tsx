// #5088 / T3-2 — a window that ENDED shows its verdict while the game is still
// being played.
//
// WHAT A READER GETS. Today, mid-game, the page says nothing at all about a
// window that has closed: #1588 strips the closed window's stale price while the
// game runs, and #1735 grades it only after full time. So the first five innings
// finish 6–1 and the page is silent about them for four more innings. live/148's
// backend sha puts `settled` on every `props_script` row; this is the last of the
// four gates — the game event page's mapping has to carry it.
//
// WHY THE MISSING LINE IS A REGRESSION AND NOT A MISSING FEATURE. `PropRow` does
// `rowState = item.settled ? "graded" : state`. Drop `settled` on the way in and
// a closed-window row falls to the SECTION state and draws `DivergenceValue`,
// which with `pregame_mark == null` renders `<Pending note="script pending" />`
// and then `pct(item.current)`. A closed window deliberately carries NO price —
// that is #1735's whole point — and MEASURED on the real payload all 64 window
// rows carry `pregame_mark: null` and `current: null` too, so the reader gets
// "script pending" and an em dash where the result belongs. That is CERT-2535's blank row, reintroduced by
// the very change that lifted CERT-2535's gate. CERT-2613 BLOCKed live/148's sha
// on exactly this.
//
// ── THE TWO LAYERS IN THIS FILE, AND WHICH ONE IS RED ─────────────────────────
//
// The defect lives in the page's MAPPING, not in PropsSection. PropsSection has
// branched on `settled` since The Open, and the golf concept page has threaded it
// all along (`app/event/[domain]/[slug]/page.tsx` maps `settled: p.settled ??
// false`). So:
//
//   · The BEHAVIOURAL tests below — the pair the cert asks for — are GREEN ON
//     BASE. They are worth having (they pin the contract the mapping depends on,
//     and they are the regression guard if anyone touches the row state machine)
//     but they cannot fail for the bug this diff fixes, and a file that did not
//     say so would be claiming a proof it does not have.
//   · The MAPPING test is the one that is RED on base. It reads source, because
//     the map is inline in a 2,000-line page component and jsdom cannot reach it
//     without mounting the whole page. It is a proxy and is labelled as one.
//
// That split is ux/1192's lesson applied deliberately rather than discovered
// afterwards: ask what layer the bug lives in, then ask what layer your test
// reads, and if they differ, say so in the file.
//
// Fixture props are the same pair as live/148's backend fixture,
// `backend/tests/test_midgame_window_results_5088.py::
//  test_the_first_five_are_graded_while_the_sixth_is_still_being_played`.
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

/** A closed first-five window beside an open sixth-inning market. */
const FIRST_FIVE: PropMark = {
  key: "Tampa Bay vs Atlanta: First 5 Innings|Tampa Bay wins first 5 innings",
  label: "Tampa Bay wins first 5 innings",
  // MEASURED on the real payload of /api/events/15308050/game-markets: all 64
  // window rows carry `pregame_mark: null` AND `current: null`. A closed window
  // has no price by design (#1735), and these markets never carried a pregame
  // mark either — which is precisely why the unfixed row falls to "script
  // pending" rather than merely showing a stale number.
  pregame_mark: null,
  current: null,
  settled: true,
  graded_result: "hit",
  graded_label: "6–1 — hit",
};

const SIXTH: PropMark = {
  key: "Tampa Bay vs Atlanta: 6th Inning Total|Over 0.5",
  label: "Over 0.5 runs in the 6th",
  pregame_mark: null,
  current: 0.4,
  settled: false,
};

// The section is LIVE — this is the whole point. At full time the section state
// is already "graded" and `settled` changes nothing, so a test run in the graded
// state could not tell the fix from its absence.
const live = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);

const countOf = (html: string, needle: string) =>
  html.split(needle).length - 1;

describe("#5088 a closed window shows its verdict while the game is live", () => {
  test("the closed window prints its RESULT", () => {
    expect(live([FIRST_FIVE, SIXTH])).toContain("6–1 — hit");
  });

  // Scoped to the closed row ALONE, deliberately. The section-wide version of
  // this assertion is WRONG and I wrote it first: the still-open sixth also
  // renders "script pending" (it has no pregame mark either), so asserting the
  // string is absent from the whole section fails on a correct fix, and
  // asserting it is PRESENT passes on a broken one. See the next test.
  test("the closed window alone prints no 'script pending' and no em dash", () => {
    const html = live([FIRST_FIVE]);
    expect(html).toContain("6–1 — hit");
    expect(html).not.toContain("script pending");
    expect(html).not.toContain("—</span>");
  });

  test("the still-open sixth keeps its LIVE price in the same section", () => {
    expect(live([FIRST_FIVE, SIXTH])).toContain("40%");
  });

  // One section, two row states — the pair is the ship, not either row alone.
  // Counted rather than matched: "script pending" belongs to the OPEN row and
  // must appear exactly once, not twice.
  test("both states render together: a verdict beside a live price", () => {
    const html = live([FIRST_FIVE, SIXTH]);
    expect(html).toContain("6–1 — hit");
    expect(html).toContain("40%");
    expect(countOf(html, "script pending")).toBe(1);
  });

  // CONTROL, and the one that proves these tests are about `settled` rather
  // than about the fixture. Same rows with `settled` dropped — exactly what the
  // unfixed mapping produces — and the closed window loses its verdict, gains a
  // second "script pending" and renders an em dash where the result belongs.
  test("CONTROL: without `settled` the closed window degrades to a blank row", () => {
    const html = live([{ ...FIRST_FIVE, settled: undefined }, SIXTH]);
    expect(html).not.toContain("6–1 — hit");
    expect(countOf(html, "script pending")).toBe(2);
    expect(html).toContain("—</span>");
  });
});

// ── The layer the bug actually lives in ───────────────────────────────────────
describe("#5088 the game event page's mapping carries `settled`", () => {
  const PAGE = join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx");
  const source = () => readFileSync(PAGE, "utf8");

  /**
   * The body of the `propsScript.map(...)` that builds the PropMark list.
   *
   * Anchored on both ends and asserted non-null by every caller first —
   * otherwise "the map carries settled" would pass with the map deleted, which
   * is the vacuous-guard failure where removing the feature turns the test
   * green.
   */
  function propsScriptMap(): string | null {
    const src = source();
    const at = src.indexOf("propsScript\n");
    const start = at === -1 ? src.indexOf("propsScript") : at;
    if (start === -1) return null;
    const end = src.indexOf("isChildTitleMark", start);
    return end === -1 ? null : src.slice(start, end);
  }

  test("the map still exists and still builds PropMarks", () => {
    const map = propsScriptMap();
    expect(map).not.toBeNull();
    expect(map).toMatch(/graded_label:/);
  });

  // RED ON BASE. This is the diff.
  test("the map threads `settled` from the payload", () => {
    expect(propsScriptMap()).toMatch(/settled:\s*p\.settled/);
  });

  // `?? false` would be wrong here in a way that is easy to write and hard to
  // see: PropMark's `settled` is `boolean | null | undefined`, and the row only
  // needs truthiness, but coercing an ABSENT flag to an explicit `false` asserts
  // "this row is known not to be settled" when the payload said nothing at all.
  // live/148's backend ships the field on every row; if it ever stops, null must
  // stay distinguishable from a real `false`.
  test("an absent flag stays absent rather than being coerced to false", () => {
    expect(propsScriptMap()).not.toMatch(/settled:\s*p\.settled\s*\?\?\s*false/);
  });

  test("the payload type declares `settled`, or the map could not compile", () => {
    const api = readFileSync(join(__dirname, "..", "..", "lib", "api.ts"), "utf8");
    const at = api.indexOf("props_script?:");
    expect(at).toBeGreaterThan(-1);
    expect(api.slice(at, api.indexOf("}[];", at))).toMatch(
      /settled\?:\s*boolean\s*\|\s*null/,
    );
  });
});
