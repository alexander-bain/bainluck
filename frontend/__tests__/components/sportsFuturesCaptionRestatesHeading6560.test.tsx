/**
 * #6560 — a /sports futures card does not print its own heading back to itself.
 *
 * Found on the D48 mystery-shop of production `/sports` at 390px (authority/386,
 * 2026-09-16 13:55Z; re-measured by ux at 15:10Z on the payload the specimens
 * below are copied from). `generate_futures_reason` writes a sentence that stands
 * alone, so it ends in the market name — and this card prints that same name one
 * line ABOVE it as the heading:
 *
 *     English Premier League Champion                        <- heading
 *     Arsenal (49%) leads English Premier League Champion     <- caption
 *
 * 27 of 27 futures cards on `GET /api/feed?mode=sports&limit=60`, across six
 * templates. `headline` and `context_summary` restate the name 0 of 27 times.
 *
 * It costs more than the pixels: the caption is `line-clamp-2`, and measured in
 * the live DOM at 390px two of those cards overflowed a third line
 * (`scrollHeight` 48 vs `clientHeight` 32) — the Hole-in-One card's caption was
 * cut at "…1+ holes-in-one leads …", losing the `48%` the clause exists to
 * deliver, because 44 characters had gone on restating the heading.
 *
 * The fix mints no copy: `FuturesFeedCard` now resolves its caption through
 * `feedContextSnippet`, the chain Discover and iOS already use for a futures card
 * — whose own comment is this defect almost word for word. These tests pin the
 * pair of claims that makes that a fix rather than a swap:
 *   - the caption no longer contains the heading, on every live template; and
 *   - a card whose `headline` says something the reason does not keeps that copy.
 */
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import { feedContextSnippet } from "@/components/discover/utils";
import type { FeedItem } from "@/lib/types";

/**
 * Verbatim from `GET /api/feed?mode=sports&limit=60`, production, 2026-09-16
 * 15:08Z. Six specimens covering all six reason templates the issue measured,
 * plus the two cards whose caption was clipped in the live DOM.
 */
const SERVED: {
  label: string;
  name: string;
  headline: string;
  reason: string;
  context_summary: string;
}[] = [
  {
    label: "leads-template",
    name: "English Premier League Champion",
    headline: "Arsenal leads at 49%",
    reason: "Arsenal (49%) leads English Premier League Champion",
    context_summary: "Arsenal leads at 49%",
  },
  {
    label: "in-template",
    name: "NCAAF Championship Winner",
    headline: "Ohio State Buckeyes at 11%",
    reason: "Ohio State Buckeyes (11%) in NCAAF Championship Winner",
    context_summary: "Ohio State Buckeyes at 11%",
  },
  {
    label: "movement-template",
    name: "Pro Baseball Champion",
    headline: "Los Angeles D leads at 29%, Milwaukee up 13.2 points since Feb 3",
    reason: "Milwaukee is up 13.2 points since Feb 3 in Pro Baseball Champion",
    context_summary:
      "Los Angeles D leads at 29%, Milwaukee up 13.2 points since Feb 3",
  },
  {
    label: "resolving-soon-template",
    name: "BMW PGA Championship Winner",
    headline: "Resolving soon: Rory McIlroy leads at 7%",
    reason: "BMW PGA Championship Winner resolving soon, Rory McIlroy leads at 7%",
    context_summary: "Rory McIlroy leads at 7%; resolves within a week",
  },
  {
    // CLIPPED in the live DOM: scrollHeight 48 > clientHeight 32 at 390px.
    label: "resolves-within-template",
    name: "Biltmore Championship Asheville: Hole-in-One",
    headline: "1+ holes-in-one leads; resolves within a month",
    reason:
      "Biltmore Championship Asheville: Hole-in-One resolves within a month, 1+ holes-in-one leads at 48%",
    context_summary: "1+ holes-in-one leads; resolves within a month",
  },
  {
    label: "chance-template",
    name: "Biltmore Championship Asheville: Playoff",
    headline: "Resolving within a month",
    reason:
      "Biltmore Championship Asheville: Playoff: 25% chance, resolves within a month",
    context_summary: "25% chance, resolves within a month",
  },
];

function futuresItem(served: (typeof SERVED)[number]): FeedItem {
  return {
    type: "futures",
    score: 80,
    headline: served.headline,
    reason: served.reason,
    context_summary: served.context_summary,
    data: {
      id: 6560,
      name: served.name,
      llm_sport_category: "football",
      resolution_date: "2027-02-08T00:00:00Z",
      source_count: 2,
      resolved: false,
      top_outcomes: [
        { name: "Leader", probability: 0.49 },
        { name: "Contender", probability: 0.2 },
      ],
    },
  } as unknown as FeedItem;
}

const render = (served: (typeof SERVED)[number]) =>
  renderToStaticMarkup(<FeedCard item={futuresItem(served)} />);

function captionText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-caption"[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

function pillText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-headline-pill"[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

/** The heading's own words, so "restates" is not decided by a bare substring:
 *  the two strings differ in punctuation and case on the golf specimens. */
function words(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => w.length > 2);
}

function captionRestatesHeading(caption: string, name: string): boolean {
  const capWords = new Set(words(caption));
  const nameWords = words(name);
  return nameWords.length > 0 && nameWords.every((w) => capWords.has(w));
}

describe("#6560 — the caption under the heading does not restate it", () => {
  test.each(SERVED)(
    "$label — the served reason restates the heading and the rendered caption does not",
    (served) => {
      // The BEFORE state, asserted on the wire so this test cannot quietly become
      // vacuous the day the backend stops appending the name: if the reason ever
      // stops restating, this line fails and the guard is retired deliberately.
      expect(captionRestatesHeading(served.reason, served.name)).toBe(true);

      const caption = captionText(render(served));
      expect(caption).toBeTruthy();
      expect(captionRestatesHeading(caption!, served.name)).toBe(false);
    },
  );

  test("the clipped card's caption is short enough to finish its sentence", () => {
    // The Hole-in-One caption overflowed `line-clamp-2` at 390px (scrollHeight 48
    // vs clientHeight 32) and was cut before its claim landed. The fix is not "a
    // shorter string" in the abstract — it is this string, which is 53 characters
    // shorter than the one that did not fit.
    const holeInOne = SERVED.find((s) => s.label === "resolves-within-template")!;
    const caption = captionText(render(holeInOne))!;
    expect(caption.length).toBeLessThan(holeInOne.reason.length - 40);
    expect(caption).toBe("1+ holes-in-one leads; resolves within a month");
  });

  test("NEGATIVE CONTROL — a headline that says something new is not dropped", () => {
    // The `movement-template` card is one of the 3 of 27 whose headline is NOT a
    // token-subset of its reason: it names the leader and the percent the reason
    // never mentions. That copy must survive the change — on this card the served
    // reason is the string that says LESS.
    const movement = SERVED.find((s) => s.label === "movement-template")!;
    const html = render(movement);
    expect(captionText(html)).toBe(
      "Los Angeles D leads at 29%, Milwaukee up 13.2 points since Feb 3",
    );
    // Nothing the reason said alone is lost: the movement clause is still there.
    expect(captionText(html)).toContain("Milwaukee up 13.2 points since Feb 3");
  });

  test("CONTROL — with nothing served but a reason, the reason is still the caption", () => {
    // The chain's last rung. A payload with no `context_summary` and no `headline`
    // must not lose its only sentence, restatement or not — a rule that only ever
    // removes copy is indistinguishable from deleting the line.
    const bare = {
      ...SERVED[0],
      headline: "",
      context_summary: "",
    };
    expect(captionText(render(bare))).toBe(
      "Arsenal (49%) leads English Premier League Champion",
    );
  });
});

describe("#6560 — /sports resolves the caption the way Discover does (notice 35)", () => {
  test.each(SERVED)("$label — the rendered caption IS the shared chain's answer", (served) => {
    // Not "the same rule" — the same function. A second copy of the preference
    // order is how the two surfaces drifted apart in the first place.
    expect(captionText(render(served))).toBe(feedContextSnippet(futuresItem(served)));
  });
});

describe("#6560 — the pill still yields to the sentence beneath it (#4403 held)", () => {
  test.each(SERVED.filter((s) => s.headline === s.context_summary))(
    "$label — a pill that would duplicate the caption verbatim is dropped",
    (served) => {
      expect(pillText(render(served))).toBeNull();
    },
  );

  test("a pill whose words the caption lacks still renders — the live Playoff card", () => {
    // The one live specimen where `context_summary` and `headline` differ enough
    // to clear the echo test in both directions. It is the reachable half of the
    // rule: the pill is suppressed far more often than before, never more rarely,
    // and it is not dead.
    const playoff = SERVED.find((s) => s.label === "chance-template")!;
    expect(pillText(render(playoff))).toBe("Resolving within a month");
  });

  test("the pill can never come BACK on a card where #4403 suppressed it", () => {
    // The `reason` half of the test is kept precisely so this holds: the caption
    // changed, so an echo measured against the caption alone could re-admit a pill
    // #4403 had cleared. `resolving-soon` is that card — "Resolving soon: Rory
    // McIlroy leads at 7%" shares no stem with "…resolves within a week".
    const soon = SERVED.find((s) => s.label === "resolving-soon-template")!;
    const html = render(soon);
    expect(pillText(html)).toBeNull();
    expect(captionText(html)).toBe("Rory McIlroy leads at 7%; resolves within a week");
  });
});
