/**
 * #7872 — a futures card does not print its resolution twice, once exactly and
 * once vaguely.
 *
 * Found on the hourly Discover mystery-shop of production at 390px (discover/390,
 * 2026-09-21 20:49Z; re-measured on the payload below at 23:15Z). The eyebrow and
 * the caption are two renderings of ONE field, `resolution_date`:
 *
 *     🎬 ENTERTAINMENT · Resolves Oct 10, 2026 · ▮▮▯          <- eyebrow
 *     Nobel Peace Prize Winner 2026                           <- heading
 *     Sudan's Emergency Response Rooms leads; resolves within a month
 *
 * 31 of 91 served futures cards on `GET /api/feed?limit=200` carry the shape,
 * across all four `resolving_soon_*` windows and both tenses the backend writes.
 * The vague half is never the better half — in every shape the eyebrow is
 * strictly more precise about the same field — and it costs the caption's second
 * clause, the one line the card has for a why-now.
 *
 * WHAT MAKES A CARD ONE OF THE 31 IS THE CAPTION, NOT THE DATE, and the two
 * controls here are the whole reason the fix is shaped the way it is:
 *
 *   - `MLB World Series Winner` carries NO eyebrow (`resolution_date: null`), so
 *     there is nothing to duplicate and nothing may be removed.
 *   - `FuturesCompactRow` — the group/bundle member row — renders this caption
 *     and no eyebrow AT ALL, so on that surface the clause is the reader's only
 *     statement of when. A strip that read `resolution_date` and inferred the
 *     eyebrow would silently delete it; the caller passes the string it renders.
 *
 * The clock is pinned to the capture instant so the specimens' real dates render
 * their real eyebrows forever (gotcha #44): `resolvesLabel` is a function of
 * `Date.now()`, and on a live clock these cards would drift branch by branch —
 * "Closes in 5h" today, silence in October — and take the assertions with them.
 */
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import { FuturesCompactRow } from "@/components/discover/FuturesCard";
import {
  feedContextSnippet,
  resolvesLabel,
  stripResolutionWindowClause,
} from "@/components/discover/utils";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

/** The instant the payload below was captured from production. */
const CAPTURED_AT = new Date("2026-09-21T23:15:00Z");

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["nextTick"] });
  jest.setSystemTime(CAPTURED_AT);
});
afterAll(() => {
  jest.useRealTimers();
});

type Served = {
  label: string;
  name: string;
  resolution_date: string | null;
  headline: string;
  reason: string;
  context_summary: string;
  /** What the eyebrow prints at `CAPTURED_AT`, from the live page. */
  eyebrow: string;
};

/** Verbatim from `GET /api/feed?limit=200`, production, 2026-09-21 23:15Z. */
const SERVED: Served[] = [
  {
    // The specimen in the issue, and the vaguest pairing: an exact calendar date
    // over a 30-day window.
    label: "tail-clause-month",
    name: "Nobel Peace Prize Winner 2026",
    resolution_date: "2026-10-10T00:00:00+00:00",
    headline: "Sudan's Emergency Response Rooms leads; resolves within a month",
    reason:
      "Nobel Peace Prize Winner 2026 resolves within a month, Sudan's Emergency Response Rooms leads at 13%",
    context_summary:
      "Sudan's Emergency Response Rooms leads; resolves within a month",
    eyebrow: "Resolves Oct 10, 2026",
  },
  {
    // The tightest pairing, and the one that shows the clause is never the better
    // half: the eyebrow is counting HOURS while the caption says "within a day".
    label: "tail-clause-day",
    name: "Top Global Netflix Movie this week?",
    resolution_date: "2026-09-22T03:59:00+00:00",
    headline: "Why Did I Get Married Again? leads at 90%",
    reason:
      "Top Global Netflix Movie this week? resolving within a day, Why Did I Get Married Again? leads at 90%",
    context_summary:
      "Why Did I Get Married Again? leads at 90%; resolves within a day",
    eyebrow: "Closes in 5h",
  },
  {
    // The pill specimen — see the dedicated test below.
    label: "tail-clause-with-live-pill",
    name: "Argentina Monthly Inflation - September",
    resolution_date: "2026-10-13T15:59:00+00:00",
    headline: "1.9 to 2.1% leads; resolves within a month",
    reason: "Big odds movement in Argentina Monthly Inflation - September",
    context_summary: "1.9 to 2.1% leads; resolves within a month",
    eyebrow: "Resolves Oct 13, 2026",
  },
  {
    // The WHOLE caption is the clause. This is the card the fix is worth the most
    // on: the chain falls through to a sentence the eyebrow cannot give.
    label: "whole-caption-is-the-clause",
    name: "S&P 500 (SPY) closes above ___ on September 22?",
    resolution_date: "2026-09-22T20:00:00+00:00",
    headline: "Big odds movement",
    reason: "Big odds movement in S&P 500 (SPY) closes above ___ on September 22?",
    context_summary: "Resolves within a day",
    eyebrow: "Closes in 21h",
  },
];

/** The control: no `resolution_date`, so no eyebrow, so nothing to subtract. */
const NO_EYEBROW: Served = {
  label: "no-eyebrow-control",
  name: "MLB World Series Winner",
  resolution_date: null,
  headline:
    "Los Angeles Dodgers lead at 28%, Milwaukee Brewers up 10.2 points since Feb 2",
  reason:
    "Milwaukee Brewers is up 10.2 points since Feb 2 in MLB World Series Winner",
  context_summary:
    "Los Angeles Dodgers lead at 28%, Milwaukee Brewers up 10.2 points since Feb 2",
  eyebrow: "",
};

const WINDOW_CLAUSE = /resolv(?:es|ing) within (?:a day|two days|a week|a month)/i;

function futuresData(served: Served): FeedFuturesData {
  return {
    id: 7872,
    name: served.name,
    llm_sport_category: "economics",
    resolution_date: served.resolution_date,
    source_count: 2,
    resolved: false,
    top_outcomes: [
      { id: 1, name: "Leader", probability: 0.56 },
      { id: 2, name: "Runner-up", probability: 0.29 },
    ],
  } as unknown as FeedFuturesData;
}

function futuresItem(served: Served): FeedItem {
  return {
    type: "futures",
    score: 80,
    headline: served.headline,
    reason: served.reason,
    context_summary: served.context_summary,
    data: futuresData(served),
  } as unknown as FeedItem;
}

const render = (served: Served) =>
  renderToStaticMarkup(<FeedCard item={futuresItem(served)} />);

/** `renderToStaticMarkup` escapes the apostrophe in "Sudan's" — compare the text
 *  a reader sees, not its HTML encoding. */
const ENTITIES: Record<string, string> = {
  "&#x27;": "'",
  "&quot;": '"',
  "&lt;": "<",
  "&gt;": ">",
  "&amp;": "&",
};

function decode(text: string): string {
  // ONE pass over the string, not a chain of `.replace`s. Chained, `&amp;`
  // becomes `&` before `&lt;` is considered, so a served `&amp;lt;` decodes to
  // `<` — a character the payload never contained. A single scan cannot
  // re-examine what it just wrote.
  return text.replace(/&(?:#x27|quot|lt|gt|amp);/g, (m) => ENTITIES[m] ?? m);
}

function captionText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-caption"[^>]*>([^<]*)</);
  return m ? decode(m[1]) : null;
}

function pillText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-headline-pill"[^>]*>([^<]*)</);
  return m ? decode(m[1]) : null;
}

describe("#7872 — the eyebrow the specimens were measured against", () => {
  test.each(SERVED)("$label — the card really does print an exact eyebrow", (served) => {
    // Pinned so the pairing under test is REAL: without this the whole suite
    // could pass because no eyebrow rendered at all and there was never a
    // duplicate to remove.
    expect(resolvesLabel(served.resolution_date)).toBe(served.eyebrow);
  });

  test("the control card prints no eyebrow at all", () => {
    expect(resolvesLabel(NO_EYEBROW.resolution_date)).toBe("");
  });
});

describe("#7872 — the rendered caption states the resolution once", () => {
  test.each(SERVED)("$label — the served copy says it twice; the card does not", (served) => {
    // The BEFORE state, asserted on the wire, so this guard cannot go vacuous the
    // day the backend stops appending the window: if no served candidate carries
    // the clause any more, this line fails and the guard is retired deliberately.
    expect(
      WINDOW_CLAUSE.test(served.context_summary) ||
        WINDOW_CLAUSE.test(served.headline) ||
        WINDOW_CLAUSE.test(served.reason),
    ).toBe(true);

    const html = render(served);
    // The exact statement survives...
    expect(html).toContain(served.eyebrow);
    // ...and the vague restatement of the same field is gone from the caption.
    const caption = captionText(html);
    expect(caption).toBeTruthy();
    expect(caption).not.toMatch(WINDOW_CLAUSE);
  });

  test("the card whose whole caption was the clause gains a sentence, not a blank", () => {
    // The point of subtracting INSIDE the chain rather than after it. "Resolves
    // within a day" under "Closes in 21h" was the entire caption; door 2 carries
    // a why-now the eyebrow cannot give, and an empty line would have been a
    // worse answer than the duplicate.
    const spy = SERVED.find((s) => s.label === "whole-caption-is-the-clause")!;
    expect(captionText(render(spy))).toBe("Big odds movement");
  });

  test.each(SERVED)("$label — the caption is still the shared chain's answer (notice 35)", (served) => {
    // Not "the same rule" — the same function, given the same eyebrow. A second
    // copy of the preference order is how these surfaces drift apart.
    expect(captionText(render(served))).toBe(
      feedContextSnippet(futuresItem(served), served.eyebrow),
    );
  });
});

describe("#7872 — CONTROL: a card with no eyebrow keeps every word", () => {
  test("nothing is removed when the reader cannot see the date elsewhere", () => {
    const html = render(NO_EYEBROW);
    expect(captionText(html)).toBe(NO_EYEBROW.context_summary);
  });

  test("the clause survives on a no-eyebrow card that HAS one", () => {
    // The no-eyebrow control above happens to carry no window clause, so on its
    // own it proves only that the code did not invent a deletion. This is the
    // case that matters: a card the reader cannot otherwise time.
    const undated: Served = {
      ...SERVED[0],
      label: "undated-but-resolving",
      resolution_date: null,
      eyebrow: "",
    };
    expect(captionText(render(undated))).toBe(
      "Sudan's Emergency Response Rooms leads; resolves within a month",
    );
  });

  test("THE COMPACT ROW — a bundle member shows no eyebrow, so it keeps the clause", () => {
    // `FuturesCompactRow` renders this caption with no resolution line anywhere
    // on the row (its own comment quotes `Core CPI YoY - September 2026 · 2.4% ·
    // Resolves within a month`). This is the surface a `resolution_date`-gated
    // strip would have silently broken, and it is why the gate is the caller's.
    const served = SERVED[0];
    const item = futuresItem(served);
    const html = renderToStaticMarkup(
      <FuturesCompactRow item={item} data={item.data as FeedFuturesData} />,
    );
    const m = html.match(/data-testid="compact-row-caption"[^>]*>([\s\S]*?)<\/div>/);
    expect(m).toBeTruthy();
    expect(m![1]).toMatch(WINDOW_CLAUSE);
    // And the row really does print no eyebrow, so the clause is load-bearing.
    expect(html).not.toContain(served.eyebrow);
  });
});

describe("#7872 — the pill cannot carry the clause back one row up", () => {
  test("a pill #4403 suppressed is not re-admitted by the shorter caption", () => {
    // MEASURED, not assumed: with the caption stripped and the pill left alone,
    // this is the one live card of 91 whose pill returns — the echo test keys on
    // the caption, and the words the pill added are exactly the ones just
    // removed. Its `reason` never says "within a month", so the belt that holds
    // every other card does not hold this one.
    const argentina = SERVED.find((s) => s.label === "tail-clause-with-live-pill")!;
    const html = render(argentina);
    expect(pillText(html)).toBeNull();
    expect(html).not.toMatch(WINDOW_CLAUSE);
  });
});

describe("#7872 — the subtraction only ever removes backend copy", () => {
  const EYEBROW = "Resolves Oct 10, 2026";

  test("all three positions the backend composes", () => {
    expect(
      stripResolutionWindowClause("Leader leads at 32%; resolves within a week", EYEBROW),
    ).toBe("Leader leads at 32%");
    expect(
      stripResolutionWindowClause("90% chance, resolving within a week", EYEBROW),
    ).toBe("90% chance");
    expect(stripResolutionWindowClause("Resolves within a month", EYEBROW)).toBe("");
    expect(
      stripResolutionWindowClause("Resolving within a day, Leader leads at 90%", EYEBROW),
    ).toBe("Leader leads at 90%");
  });

  test("the vocabulary is closed — a sentence the backend never wrote is untouched", () => {
    // This only ever deletes, so a pattern wider than the emitted copy would
    // delete a sentence nobody wrote. `resolves within a fortnight` is not a
    // string `feed_reasons.py` can produce, and a loose `resolves within .*`
    // would eat it.
    for (const text of [
      "Leader leads at 32%; resolves within a fortnight",
      "Leader resolves the tiebreak within a week",
      "Resolution within a month is disputed",
      "Leader leads at 32%; resolves within a week and then some",
    ]) {
      expect(stripResolutionWindowClause(text, EYEBROW)).toBe(text);
    }
  });

  test("no eyebrow, no subtraction — at the helper, in both directions", () => {
    const withClause = "Leader leads at 32%; resolves within a week";
    expect(stripResolutionWindowClause(withClause, "")).toBe(withClause);
    expect(stripResolutionWindowClause(withClause, null)).toBe(withClause);
    expect(stripResolutionWindowClause(withClause, undefined)).toBe(withClause);
    expect(stripResolutionWindowClause(withClause, EYEBROW)).toBe("Leader leads at 32%");
  });
});
