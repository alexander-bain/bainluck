// L2-238 Item 1 — the rendered unavailable state, both placements.
//
// Proves the state is an ALERT with an ACTIONABLE, NAMED retry, and that it
// reuses the Discover surface's existing words rather than inventing copy. The
// visual/overlap/VoiceOver proof at real widths comes from the browser rail;
// this is the always-on structural guard that survives a refactor.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FeedUnavailableNotice from "../../components/discover/FeedUnavailableNotice";

describe("FeedUnavailableNotice (L2-238)", () => {
  test("empty variant: alert role, existing copy, named retry control", () => {
    const html = renderToStaticMarkup(
      <FeedUnavailableNotice onRetry={() => {}} variant="empty" />,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain('data-testid="discover-feed-unavailable"');
    expect(html).toContain('data-variant="empty"');
    // The words the Discover page already uses for a failed load.
    expect(html).toContain("Failed to load feed");
    expect(html).toContain("Try again");
    expect(html).toContain("<button");
    // The bare verb phrase is not a sufficient accessible name (L2-237).
    expect(html).toContain('aria-label="Try again to load the feed"');
  });

  test("inline variant renders the same state below last-good cards", () => {
    const html = renderToStaticMarkup(
      <FeedUnavailableNotice onRetry={() => {}} variant="inline" />,
    );
    expect(html).toContain('data-variant="inline"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Try again");
    expect(html).toContain('aria-label="Try again to load the feed"');
  });

  test("never claims the feed ended", () => {
    for (const variant of ["empty", "inline"] as const) {
      const html = renderToStaticMarkup(
        <FeedUnavailableNotice onRetry={() => {}} variant={variant} />,
      );
      expect(html.toLowerCase()).not.toContain("caught up");
      expect(html.toLowerCase()).not.toContain("that's everything");
      expect(html.toLowerCase()).not.toContain("no more");
    }
  });

  test("the retry callback is the control's action", () => {
    // Structural: the button exists and is not disabled, so the page's
    // handleRetryUnavailable is reachable. (Behavioural click coverage lives in
    // the browser rail — this repo has no @testing-library/react.)
    const html = renderToStaticMarkup(
      <FeedUnavailableNotice onRetry={() => {}} variant="empty" />,
    );
    expect(html).not.toContain("disabled");
  });
});
