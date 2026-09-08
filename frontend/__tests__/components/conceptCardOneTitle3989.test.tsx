/**
 * #3989 — A DISCOVER CONCEPT CARD PRINTS ITS TITLE ONCE, AND ITS SUBTITLE IS A
 * SENTENCE.
 *
 * Found on a LOOK pass (ux/1130) on production `/` at 390px. Said aloud, the
 * card read:
 *
 *     "Cycling. Live. Vuelta a España 2026. Tadej Pogacar 75% of 30.
 *      Vuelta a España 2026. Like. Share."
 *
 * Two defects, one card:
 *
 *  1. THE TITLE TWICE. `ConceptCard`'s hero printed `data.name` and the body
 *     <h3> printed it again ~100px lower — two distinct leaf nodes, both
 *     reading exactly `Vuelta a España 2026`, read out of the production DOM.
 *     This was not a data accident: it is structural, so it hit EVERY unsettled
 *     concept the feed can admit. The sibling `TournamentCard` that
 *     `ConceptCard` was explicitly modeled on never does it — its hero carries
 *     the NUMBER and its body carries the name, once. ConceptCard had drifted
 *     from the grammar it claimed to follow.
 *
 *  2. "of 30" IS NOT A SUBTITLE. The qualifier rendered as a bare `of 30`
 *     directly after the `75%` pill, so the line read "seventy-five percent of
 *     thirty" — an arithmetic claim (22.5) rather than the field size it means.
 *     Confirmed against the live payload before changing anything (ux/1134's
 *     rule): `/api/feed` serves `leader.field_size: 30` on
 *     `event:cycling:vuelta-2026`. The issue guessed this; the payload settled
 *     it.
 *
 * WHY THE COUNT IS OF LEAF NODES. Counting the name in raw HTML over-counts —
 * `data.name` also travels in the share URL, `shareTitle` and `shareText`
 * attributes. Counting leaves reproduces the issue's own evidence method. A
 * leaf filter is unsafe in general (it drops any paragraph containing a
 * `<strong>`), but both title nodes here are plain text, and the `<a>` wrapping
 * the body <h3> is skipped as a non-leaf while the <h3> itself is counted.
 *
 * CONTROLS. The settled-with-a-winner arm was already correct (hero = winner,
 * body = name) and the two-way bout already omits the qualifier. Both are
 * asserted here so the fix cannot widen into branches it had no business
 * touching.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedConceptData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";
import { ConceptCard } from "../../components/discover/ConceptCard";

const VUELTA = "Vuelta a España 2026";

function conceptCard(data: Partial<FeedConceptData>): FeedItem {
  return {
    type: "concept",
    data: {
      key: "event:cycling:vuelta-2026",
      name: VUELTA,
      domain: "cycling",
      status: "live",
      marquee_whathit: false,
      ...data,
    } as FeedConceptData,
  } as FeedItem;
}

function renderConcept(data: Partial<FeedConceptData>): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item: conceptCard(data) }} />,
  );
}

/**
 * How many times `text` is the ENTIRE text of an element — i.e. it sits between
 * a `>` and a `<` with nothing else. `jest-environment-jsdom` is not installed
 * in this repo and this guard is not worth a new dependency, so the count is
 * taken off the markup string; it is the same measurement the issue made with
 * `textContent` on the production DOM.
 *
 * Matching `>text<` rather than `text` is what keeps the count honest:
 * `data.name` also travels in this card's share URL, `shareTitle` and
 * `shareText`, and those are attribute values, never between two tags.
 */
function leafCount(html: string, text: string): number {
  const needle = `>${text}<`;
  let n = 0;
  let i = html.indexOf(needle);
  while (i !== -1) {
    n += 1;
    i = html.indexOf(needle, i + 1);
  }
  return n;
}

/** The exact production row: Pogačar 0.751 of a 30-rider field. */
const LIVE_LEADER = {
  leader: { name: "Tadej Pogacar", probability: 0.751, field_size: 30 },
};

describe("#3989 — the concept card names itself once", () => {
  it("prints the title EXACTLY once on the unsettled leader card (the filed card)", () => {
    const html = renderConcept(LIVE_LEADER);

    // The card rendered at all — without this the count below is vacuously 1
    // for a card that fell through to some other branch entirely.
    expect(html).toContain("Tadej Pogacar");
    expect(leafCount(html, VUELTA)).toBe(1);
  });

  it("prints the title exactly once on an unsettled BOUT card", () => {
    const html = renderConcept({
      name: VUELTA,
      headline_bout: {
        competitors: [
          { name: "Pasley", probability: 0.415 },
          { name: "Berisha", probability: 0.585 },
        ],
      },
    });

    expect(html).toContain("Berisha");
    expect(leafCount(html, VUELTA)).toBe(1);
  });

  it("prints the title exactly once on a SETTLED card carrying only a summary", () => {
    // The winner-less settled arm. `feedItemSuppressionReason` admits this card
    // on the summary alone, so the summary is what the hero has to say.
    const html = renderConcept({
      marquee_whathit: true,
      result_summary: "Jonas Vingegaard won the general classification",
    });

    expect(html).toContain("Jonas Vingegaard won the general classification");
    expect(leafCount(html, VUELTA)).toBe(1);
  });

  it("CONTROL — the settled winner arm was already right and stays right", () => {
    // Hero = the champion, body = the concept. This branch never duplicated;
    // if this count moves, the fix has widened into a branch it did not own.
    const html = renderConcept({
      marquee_whathit: true,
      winner: "Jonas Vingegaard",
    });

    expect(html).toContain("Jonas Vingegaard");
    expect(html).toContain("Champion");
    expect(leafCount(html, VUELTA)).toBe(1);
  });

  it("BACKSTOP — a bout-less, leader-less card still names itself rather than render blank", () => {
    // Rendered through `ConceptCard` DIRECTLY, because the feed cannot deliver
    // this shape: `feedItemSuppressionReason` admits an unsettled concept ONLY
    // on a usable bout or leader, so `DiscoverCard` drops it as `empty_concept`
    // and renders nothing (asserted below, so this stays true if the gate ever
    // loosens). The backstop exists for the other direction — a renderer that
    // reads the payload MORE strictly than the gate that admitted the card must
    // never leave a blank 176px hero. Here the name may appear twice; a
    // duplicated title beats an empty card.
    expect(renderConcept({ name: VUELTA })).toBe("");

    const html = renderToStaticMarkup(
      <ConceptCard
        data={{ key: "event:cycling:vuelta-2026", name: VUELTA, domain: "cycling", status: "live" } as FeedConceptData}
        liked={false}
        setLiked={() => {}}
      />,
    );
    expect(leafCount(html, VUELTA)).toBeGreaterThanOrEqual(1);
  });
});

describe("#3989 — the field-size qualifier is a phrase, not arithmetic", () => {
  it("says 'field of 30', never a bare 'of 30'", () => {
    const html = renderConcept(LIVE_LEADER);

    expect(leafCount(html, "field of 30")).toBe(1);
    // The defect precisely: `of 30` standing alone as its own node, which is
    // what made the line read as 75% × 30. "field of 30" contains "of 30" as a
    // substring, so a `toContain` check here would pass on the broken build —
    // the leaf identity is the only assertion that actually goes red.
    expect(leafCount(html, "of 30")).toBe(0);
  });

  it("still prints the probability itself", () => {
    // The number was promoted to the hero when the redundant title left. It
    // must remain a plain, server-rendered reading: `AnimatedProbability`
    // prints an em-dash until an IntersectionObserver fires and splits the "%"
    // into a child span, so using it here would blank the number in SSR.
    const html = renderConcept(LIVE_LEADER);
    expect(leafCount(html, "75%")).toBe(1);
    expect(html).not.toContain("—");
  });

  it("CONTROL — a two-way field says nothing at all", () => {
    const html = renderConcept({
      leader: { name: "Joshua Van", probability: 0.5217, field_size: 2 },
    });

    expect(html).toContain("Joshua Van");
    expect(html).not.toContain("of 2");
    expect(html).not.toContain("field of");
  });
});
