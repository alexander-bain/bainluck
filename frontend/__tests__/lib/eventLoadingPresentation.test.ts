import { EVENT_BOOT_CLAIM_TIMEOUT_MS } from "@/lib/event/detailBoot";
import {
  EVENT_FETCH_FIRST_POSSIBLE_FAILURE_MS,
  EVENT_SLOW_LOAD_NOTICE_MS,
  eventLoadingView,
} from "@/lib/event/loadingPresentation";

/**
 * #5607 — the Event page replaced itself with a terminal "Loading timed out"
 * card at 12s, while `fetchEvent`'s first stage (the 20s boot-claim race) was
 * still running and had not failed.
 *
 * These guards are aimed at the INVERSION, not at the new wording. A test that
 * only asserted the new sentence would pass the day someone reintroduced a
 * terminal deadline with a politer name.
 */
describe("#5607 — a slow event load is never rendered as a failure", () => {
  describe("the deadline inversion that caused it", () => {
    it("cannot claim a failure before one is possible: the notice lands inside stage 1", () => {
      // The direction is the whole point. The OLD constant was wrong because it
      // fired a FAILURE before this mark; the new one is right because it fires
      // REASSURANCE before it. Same inequality, opposite meanings — so this
      // asserts the mark is strictly inside the window, and the presentation
      // tests below assert what is shown there is not a failure.
      expect(EVENT_SLOW_LOAD_NOTICE_MS).toBeLessThan(
        EVENT_FETCH_FIRST_POSSIBLE_FAILURE_MS,
      );
    });

    it("measures 'first possible failure' against the real stage-1 budget", () => {
      // If `claimEventBooted` stops being the first stage, or its budget moves,
      // this is the line that has to be reconsidered rather than silently
      // inherited. The shipped defect was exactly this number going unread.
      expect(EVENT_FETCH_FIRST_POSSIBLE_FAILURE_MS).toBe(
        EVENT_BOOT_CLAIM_TIMEOUT_MS,
      );
    });
  });

  describe("every loading view is a loading view", () => {
    it.each([
      ["before the slow mark", false],
      ["after the slow mark", true],
    ])("%s, the presentation is a spinner", (_label, pastSlowMark) => {
      const view = eventLoadingView(pastSlowMark as boolean);
      expect(["spinner", "spinner-with-retry"]).toContain(view.presentation);
    });

    it.each([
      ["before the slow mark", false],
      ["after the slow mark", true],
    ])("%s, the text does not assert an outcome", (_label, pastSlowMark) => {
      const { text } = eventLoadingView(pastSlowMark as boolean);
      // The exact sentence that shipped, plus the family it belongs to. A fetch
      // still inside stage 1 has not timed out, not failed, and is not taking
      // "too long" against any budget this page is entitled to speak for.
      expect(text).not.toMatch(
        /timed out|time-?out|too long|failed|failure|couldn't|could not|unavailable|error/i,
      );
      expect(text.trim()).not.toHaveLength(0);
    });
  });

  describe("what the mark is allowed to change", () => {
    it("says nothing extra, and offers no retry, before the mark", () => {
      expect(eventLoadingView(false)).toEqual({
        presentation: "spinner",
        text: "Loading event...",
        offersRetry: false,
      });
    });

    it("tells the reader we are still working, and keeps the retry", () => {
      const view = eventLoadingView(true);
      expect(view.presentation).toBe("spinner-with-retry");
      expect(view.offersRetry).toBe(true);
      // Capability check, not a style check: the card being replaced carried a
      // `Tap to retry`, and dropping it would trade one defect for a
      // regression. The reader keeps a way out — beside a live spinner now,
      // instead of being the only way off a dead page.
      expect(view.text).toMatch(/still loading/i);
    });

    it("changes only the sentence and the retry — the mark itself still exists", () => {
      const before = eventLoadingView(false);
      const after = eventLoadingView(true);
      expect(after.text).not.toBe(before.text);
      expect(after.offersRetry).not.toBe(before.offersRetry);
    });
  });
});
