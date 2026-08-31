/**
 * UX-P209 — the hub card stops asserting a phase nobody established.
 *
 * CERT-519 blocked UX-P208 for replacing one false claim with its opposite: the
 * backend stopped saying a tournament was LIVE, started saying it could not
 * tell, and `StatusPill`'s catch-all rendered that as a confident **Upcoming**
 * — on a US Open that was in its third day with two matches in progress.
 *
 * The backend half is proved in `backend/tests/test_event_tennis.py` and
 * `backend/tests/test_event_tennis_identity.py`, which pin the emitted value at
 * `unknown`. This file proves the only thing a RENDER can: that the value the
 * rail actually emits reaches a reader as no claim at all, and that the three
 * statuses we DO stand behind still print exactly what they always printed.
 *
 * The component is the shipped `StatusPill`; nothing here is drawn by hand.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AFFIRMATIVE_HUB_STATUSES, StatusPill } from "@/components/hub/HubStatusPill";

/** Visible words, with markup and attributes stripped the way a reader sees it. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(status: string): string {
  return renderToStaticMarkup(<StatusPill status={status} />);
}

describe("the statuses the pill stands behind", () => {
  it("prints Live, with the pulsing dot, for an asserted live card", () => {
    const markup = render("live");
    expect(visibleText(markup)).toBe("Live");
    expect(markup).toContain("animate-pulse");
  });

  it("prints Final for a settled card", () => {
    expect(visibleText(render("settled"))).toBe("Final");
  });

  it("prints Upcoming for a card asserted not to have started", () => {
    expect(visibleText(render("upcoming"))).toBe("Upcoming");
  });
});

describe("the status the pill must not translate into a claim", () => {
  it("says nothing at all for `unknown` — the value the tennis rail emits", () => {
    const markup = render("unknown");
    expect(visibleText(markup)).toBe("");
    // Named individually so a failure reads as the defect rather than as a
    // diff of two blobs: the blocked build printed exactly the second one.
    expect(markup).not.toContain("Live");
    expect(markup).not.toContain("Upcoming");
    expect(markup).not.toContain("Final");
    // Not merely label-less: the dot is the loudest half of the false LIVE.
    expect(markup).not.toContain("animate-pulse");
  });

  it("says nothing for a status it has never been taught", () => {
    /**
     * THE CLASS, not the instance. `unknown` is one value; the defect was a
     * DEFAULT ARM that turned every unrecognised value into "Upcoming". A guard
     * that only pinned `unknown` would go green again the day a lister emits
     * `in_progress`, `postponed` or a typo.
     */
    for (const status of ["in_progress", "postponed", "tbd", "", "upcomming"]) {
      const markup = render(status);
      expect(visibleText(markup)).toBe("");
      expect(markup).not.toContain("Upcoming");
    }
  });

  it("keeps the affirmative set closed and named", () => {
    /**
     * The exported list is what the single-home tripwire and the reader of this
     * file both rely on. If a fourth affirmative label is added, this fails and
     * the author has to decide deliberately that the backend can establish it.
     */
    expect([...AFFIRMATIVE_HUB_STATUSES]).toEqual(["live", "settled", "upcoming"]);
    for (const status of AFFIRMATIVE_HUB_STATUSES) {
      expect(visibleText(render(status))).not.toBe("");
    }
  });
});

describe("the guard can tell the two states apart", () => {
  it("would fail if the withheld state printed the affirmative label", () => {
    /**
     * Non-vacuity, run against the real defect rather than described. This is
     * the blocked component's exact final line; the assertions above must
     * reject what it produces, or they are asserting nothing.
     */
    const BlockedPill = ({ status }: { status: string }) =>
      status === "live" || status === "settled" ? (
        <StatusPill status={status} />
      ) : (
        <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-brand">
          Upcoming
        </span>
      );

    const blocked = renderToStaticMarkup(<BlockedPill status="unknown" />);
    expect(visibleText(blocked)).toBe("Upcoming");
    expect(visibleText(render("unknown"))).toBe("");
  });
});
