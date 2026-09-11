// #5245 — two defects on the shared finished-card family, photographed together
// on page one of Discover at 390px on production `63107abb`, 2026-09-11 07:56 PT.
//
// The card read, verbatim:
//
//     [ R  Final  NYY ]
//     [ 3          10 ]
//     Colorado Rockies New York Yankees
//     Yankees won   [FINAL]   Yesterday 4:05 PM
//     27%          Pre-match          73%
//     Final
//
// (a) the two team names ran together with no separator, because the heading
//     emptied it on `isDone`; (b) the last line is the CONTEXT slot — the card's
//     explanation — falling back to the derived word "Final", a third telling of
//     a state the crest label and the chip had already said.
//
// Neither is a #5100 regression. #5100 is what put a finished marquee card in
// front of a reader on page one, which is how they were seen.
//
// Guards run BOTH directions per gotcha #43: the defect is gone, AND the strings
// the card is still supposed to say are asserted present.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";
import { SUSPENDED_LABEL } from "@/lib/eventState";

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

import { EventCard } from "../../components/discover/EventCard";

const NOW = Date.parse("2026-09-11T14:56:00Z");

/** The photographed card: Rockies @ Yankees, final, and NO caption on the wire.
 *
 * `context_summary`, `headline` and `reason` are all empty on purpose — that is
 * the exact state that made the context slot speak the word "Final", and a
 * fixture that carried any one of them would never reach the fallback at all. */
function finishedItem(
  overrides: Partial<FeedItem> = {},
  dataOverrides: Partial<FeedEventData> = {},
): FeedItem {
  return {
    type: "event",
    headline: null,
    reason: null,
    context_summary: null,
    score: 50,
    data: {
      id: 15293206,
      status: "completed",
      commence_time: "2026-09-10T20:05:00Z",
      away_team: "Colorado Rockies",
      home_team: "New York Yankees",
      away_score: 3,
      home_score: 10,
      sport: "baseball_mlb",
      ...dataOverrides,
    } as unknown as FeedEventData,
    ...overrides,
  } as unknown as FeedItem;
}

function render(item: FeedItem) {
  return renderToStaticMarkup(
    <EventCard
      item={item}
      data={item.data as FeedEventData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

/** The visible matchup heading — its leading text node, whitespace-normalised.
 *
 * Deliberately NOT a regex that deletes every angle-bracket run: that shape is an
 * incomplete HTML sanitizer (CodeQL js/incomplete-multi-character-sanitization,
 * high severity), and standing notice 32 refuses the sha for it — correctly even
 * in a test, because the shape is what gets copied somewhere that matters. */
function headingText(html: string): string {
  const m = html.match(/<h3[^>]*>([\s\S]*?)<\/h3>/);
  return m ? leadingText(m[1]) : "";
}

/** The card's context paragraph, or null when the card renders no caption.
 *
 * `ExpandableContextText` paints a bare `<p>` with the className the card hands
 * it, so the slot is addressable without adding a test-only attribute. */
function contextParagraph(html: string): string | null {
  const m = html.match(/<p class="text-sm text-text-secondary mt-2">([\s\S]*?)<\/p>/);
  return m ? leadingText(m[1]) : null;
}

/** The text before the first tag, whitespace-normalised.
 *
 * Everything these guards assert on is a leading text node: the heading is pure
 * text, and the caption's only possible sibling is the trailing "See more"
 * button, which is not part of the sentence a reader reads. */
function leadingText(fragment: string): string {
  return fragment.split("<")[0].replace(/\s+/g, " ").trim();
}

/** Occurrences of the word as its own rendered text node, e.g. `>Final<`.
 *
 * Counted this way on purpose: the raw HTML also carries "Final" inside the
 * article's aria-label, which is correct and must not be counted as one of the
 * visible tellings. */
function renderedWordCount(html: string, word: string): number {
  return html.split(`>${word}<`).length - 1;
}

describe("#5245(a) a finished card's two team names stay separable", () => {
  beforeAll(() => jest.useFakeTimers().setSystemTime(NOW));
  afterAll(() => jest.useRealTimers());

  test("the finished heading separates the names with @", () => {
    const html = render(finishedItem());
    expect(headingText(html)).toBe("Colorado Rockies @ New York Yankees");
  });

  test("the photographed run-on string is gone", () => {
    // The defect exactly as a reader met it: "Rockies New York" scans as one
    // phrase, so there is no way to tell where the away team ends.
    expect(render(finishedItem())).not.toContain("Colorado Rockies New York Yankees");
  });

  test("BOTH DIRECTIONS — the separator does not branch on state", () => {
    // The bug was a state branch, so the guard is that every state agrees. A
    // mutant that re-empties the separator for any ONE of these fails here.
    const states = [
      finishedItem(),
      finishedItem({}, { status: "scheduled", commence_time: "2026-09-12T20:05:00Z" } as Partial<FeedEventData>),
      finishedItem({}, { status: "live" } as Partial<FeedEventData>),
      finishedItem({}, { status: "suspended" } as Partial<FeedEventData>),
    ];
    const headings = states.map((s) => headingText(render(s)));
    expect(headings).toEqual([
      "Colorado Rockies @ New York Yankees",
      "Colorado Rockies @ New York Yankees",
      "Colorado Rockies @ New York Yankees",
      "Colorado Rockies @ New York Yankees",
    ]);
  });
});

describe("#5245(b) the context slot never speaks the card's state", () => {
  beforeAll(() => jest.useFakeTimers().setSystemTime(NOW));
  afterAll(() => jest.useRealTimers());

  test("a finished card with no wire caption renders no caption at all", () => {
    // Standing notice 34: leave the space empty rather than fill it with a
    // sentence written for something other than the reader.
    expect(contextParagraph(render(finishedItem()))).toBeNull();
  });

  test("the state is still said — twice, in the two places that own it", () => {
    // Non-vacuity for the test above: the fix must remove the THIRD telling
    // only. The crest label and the FINAL chip both survive; before the fix
    // this count was 3.
    expect(renderedWordCount(render(finishedItem()), "Final")).toBe(2);
  });

  test("BOTH DIRECTIONS — the backend's own sentence still renders", () => {
    // Proves the slot was not simply deleted.
    const html = render(finishedItem({ reason: "Rockies odds shifted 49% during the game" }));
    expect(contextParagraph(html)).toBe("Rockies odds shifted 49% during the game");
  });

  test("BOTH DIRECTIONS — a wire headline still renders when reason is empty", () => {
    // Only the DERIVED string left the chain; every backend-authored one stays.
    const html = render(finishedItem({ reason: "", headline: "Line moving" }));
    expect(contextParagraph(html)).toBe("Line moving");
  });

  test("BOTH DIRECTIONS — context_summary still outranks both", () => {
    const html = render(
      finishedItem({ context_summary: "A curated line.", reason: "r", headline: "h" }),
    );
    expect(contextParagraph(html)).toBe("A curated line.");
  });

  test("BOTH DIRECTIONS — an unfinished card's caption is untouched", () => {
    // isLive/isSuspended keep their derived fallbacks by design (CERT-786 guards
    // the suspended string); this asserts #5245 did not quietly take them. Note
    // `status: "live"` and not "in_progress" — `isLive` is an exact match, and a
    // fixture with the wrong verb renders no caption for a reason that has
    // nothing to do with this ship.
    const live = render(finishedItem({}, { status: "live" } as Partial<FeedEventData>));
    expect(contextParagraph(live)).toBe("Live now");

    const suspended = render(finishedItem({}, { status: "suspended" } as Partial<FeedEventData>));
    expect(contextParagraph(suspended)).toBe(SUSPENDED_LABEL);
  });
});
