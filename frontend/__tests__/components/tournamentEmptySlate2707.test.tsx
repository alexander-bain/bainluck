/**
 * AN EMPTY MATCH LIST MAY NOT CLAIM AN EMPTY DAY (#2707, defect class D27).
 *
 * ═══ THE MEASURED DEFECT ═══
 *
 * 2026-09-03T17:27Z, `GET /api/tournaments/us-open`, and a 375-wide production
 * screenshot of `/tournaments/us-open` taken from the same minute:
 *
 *     slate.count               0
 *     slate.order_of_play_listed  625
 *     slate.dropped             {ALREADY_PLAYED: 28, DECIDED: 96}
 *     slate.in_progress         0
 *
 * and on the page, in bold, over the whole card:
 *
 *     No matches scheduled
 *     Nothing is on right now. This is where the day's matches sit.
 *
 * Auger-Aliassime–Khachanov (event 15299860) had been live since 15:08Z, with
 * four more live rows beside it. The card was not describing the tournament. It
 * was describing `build_slate`'s return value and putting the world's name on
 * it.
 *
 * ═══ WHAT THESE GUARDS PIN ═══
 *
 * The three-way split in `slateEmptyState`, and — the load-bearing half — that
 * NO reachable input makes the released-draw card print "No matches scheduled"
 * again. A guard that only proved the new sentence renders would be satisfied
 * by a component that prints both.
 *
 * ═══ RED-FIRST ═══
 *
 * Against the pre-fix tree (`emptyHint`, hard-coded headline) every test in the
 * first two describes fails: `slateEmptyState` does not exist, and the
 * component's headline is a string literal no prop can reach. The
 * `pre-draw` case is the CONTROL — it is the one empty state whose wording
 * survives the fix nearly intact, so a change that simply deleted the copy
 * would go red here rather than pass.
 */
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { slateEmptyState } from "@/lib/slate";

/** The forbidden sentence, exactly as it shipped. */
const THE_LIE = "No matches scheduled";

describe("slateEmptyState — what an empty list is allowed to claim", () => {
  it("CONTROL: before the draw, 'not scheduled yet' is true and is still said", () => {
    const state = slateEmptyState({
      drawReleased: false,
      mainDrawLabel: "Sunday 30 August",
      orderOfPlayListed: 0,
    });
    expect(state.cause).toBe("pre-draw");
    expect(state.headline).toBe("No matches scheduled yet");
    expect(state.detail).toContain("Sunday 30 August");
  });

  it("CONTROL: before the draw with no label, it does not invent a date", () => {
    const state = slateEmptyState({ drawReleased: false, mainDrawLabel: null });
    expect(state.cause).toBe("pre-draw");
    expect(state.detail).toContain("once the draw is made");
    expect(state.detail).not.toMatch(/\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b/);
  });

  it("THE DEFECT: 625 listed and nothing rendered is OURS, and says so", () => {
    // The exact production numbers from 17:27Z.
    const state = slateEmptyState({
      drawReleased: true,
      mainDrawLabel: "Sunday 30 August",
      orderOfPlayListed: 625,
    });
    expect(state.cause).toBe("unrendered");
    expect(state.headline).not.toContain(THE_LIE);
    // It must not tell a reader with a live match on TV that nothing is on.
    expect(`${state.headline} ${state.detail}`).not.toMatch(/nothing is on/i);
    // It must say a match may be missing, and that we know.
    expect(state.detail).toMatch(/missing/i);
    expect(state.detail).toMatch(/checking/i);
  });

  it("a listed count of 1 is already enough to make it ours", () => {
    // The boundary, not just the measured 625: any positive count means the
    // authority still has this tournament on today's board.
    expect(slateEmptyState({ drawReleased: true, orderOfPlayListed: 1 }).cause).toBe(
      "unrendered"
    );
  });

  it("nothing listed stays HEDGED — it may be a dead feed or a finished final", () => {
    const state = slateEmptyState({ drawReleased: true, orderOfPlayListed: 0 });
    expect(state.cause).toBe("unlisted");
    expect(state.headline).not.toContain(THE_LIE);
    // "listed" is a claim about the feed. "scheduled" would be a claim about
    // the world, which is the thing this whole file exists to stop.
    expect(state.headline).toMatch(/listed/i);
    expect(state.detail).toMatch(/we are not seeing it|we're checking/i);
  });

  it("a payload with no such field reads as hedged, never as confident", () => {
    // Pre-Q463 payloads carry no `order_of_play_listed`. Absent must not be
    // read as "the authority listed nothing, therefore nothing is on".
    for (const listed of [undefined, null, NaN]) {
      const state = slateEmptyState({
        drawReleased: true,
        orderOfPlayListed: listed as number | null | undefined,
      });
      expect(state.cause).toBe("unlisted");
      expect(state.headline).not.toContain(THE_LIE);
    }
  });

  it("NO input to this function produces the sentence that shipped", () => {
    for (const drawReleased of [true, false]) {
      for (const orderOfPlayListed of [undefined, null, NaN, -1, 0, 1, 625, 99999]) {
        for (const mainDrawLabel of [null, undefined, "Sunday 30 August", ""]) {
          const state = slateEmptyState({
            drawReleased,
            mainDrawLabel,
            orderOfPlayListed: orderOfPlayListed as number | null | undefined,
          });
          // "No matches scheduled yet" is the pre-draw case and is permitted;
          // the bare claim is not. Asserted on the exact string plus its
          // boundary so the `yet` variant does not smuggle it through.
          expect(state.headline === THE_LIE).toBe(false);
          if (state.headline.startsWith(THE_LIE)) {
            expect(state.cause).toBe("pre-draw");
            expect(drawReleased).toBe(false);
          }
        }
      }
    }
  });
});

describe("the rendered card — the markup a reader actually got", () => {
  it("prints the caller's headline, not one of its own", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={[]}
        empty={slateEmptyState({ drawReleased: true, orderOfPlayListed: 625 })}
      />
    );
    expect(html).toContain('data-testid="matches-empty"');
    expect(html).toContain('data-empty-cause="unrendered"');
    expect(html).toContain("We can&#x27;t show today&#x27;s schedule");
    expect(html).not.toContain(THE_LIE);
    expect(html).not.toMatch(/Nothing is on right now/i);
  });

  it("still renders the pre-draw wording when that is the truth", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={[]}
        empty={slateEmptyState({
          drawReleased: false,
          mainDrawLabel: "Sunday 30 August",
        })}
      />
    );
    expect(html).toContain('data-empty-cause="pre-draw"');
    expect(html).toContain("No matches scheduled yet");
    expect(html).toContain("Sunday 30 August");
  });

  it("a caller that says NOTHING gets the hedged card, not the confident one", () => {
    // The old default was the lie. A component told nothing about why the list
    // is empty must not answer the question anyway.
    const html = renderToStaticMarkup(<TournamentMatches entries={[]} />);
    expect(html).toContain('data-testid="matches-empty"');
    expect(html).toContain('data-empty-cause="unlisted"');
    expect(html).not.toContain(THE_LIE);
    expect(html).not.toMatch(/Nothing is on right now/i);
  });

  it("says its own emptiness rather than rendering nothing", () => {
    // Kept from the suite this replaces: the failure mode BEFORE the wording
    // defect was an empty list rendering no card at all.
    const html = renderToStaticMarkup(<TournamentMatches entries={[]} />);
    expect(html).toMatch(/<section[^>]*data-testid="matches-empty"/);
    expect(html.replace(/<[^>]+>/g, "").trim().length).toBeGreaterThan(20);
  });
});
