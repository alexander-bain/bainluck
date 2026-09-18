/**
 * #6903 — a futures card's badge stops saying the card's own heading back to it.
 *
 * Found on the D48 mystery-shop of production `/categories/tech` at 390px
 * (discover/187, 2026-09-18 08:20Z, anonymous; screenshot
 * `artifacts-discover/shop-0820Z/tech-4400.png`). What the reader saw:
 *
 *     Ren Zhengfei public appearanc…          <- badge, truncated mid-word
 *     Ren Zhengfei public appearance?         <- heading
 *     48% chance by December 31               <- caption
 *
 * `generate_futures_headline` substitutes the MARKET NAME for the subject whenever
 * the mover's own label cannot stand alone — a bare number, a month-day such as
 * `October 31`, `Yes`/`No` (`_weak_outcome_label`). On a bundle member row, which
 * prints `headline` and nothing else, that is the right call. On a card that prints
 * `data.name` one line above, the restatement is at the FRONT of a `truncate`d
 * badge — so the restatement is what survives and the movement the string exists to
 * deliver ("odds up 53.5 points": `October 31` jumped 53.5, the biggest move on
 * that board) is what falls off.
 *
 * Measured 08:25Z over the main feed and six category feeds, 244 distinct futures
 * cards: 14 carry the shape, and on 7 of them everything behind the heading is
 * `resolves within a month` — which the caption beneath and the date chip to the
 * right already say.
 *
 * #6560 fixed the `reason`-shaped half of this class and measured `headline`
 * restating the name 0 of 27 — on 27 cards that carried no weak-label template.
 * This is the residual, so the two guards live side by side.
 *
 * The fix is a DELETION, the same species as `stripMarketNameTail` (UX-1052) on the
 * other end of the sentence: no copy is minted here (ruling 003). The backend string
 * is deliberately untouched, because the bundle member row is the consumer that
 * needs the prefix.
 */
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import { feedContextSnippet, stripCardTitleHead } from "@/components/discover/utils";
import type { FeedItem } from "@/lib/types";

/**
 * Verbatim from `GET /api/feed?limit=50&category=<c>`, production, 2026-09-18
 * 08:25Z. Five of the fourteen, covering every template that mints the shape:
 * `major_movement_24h` (whole name, and the `_short_market_name` truncated name),
 * `recent_movement`, and `resolving_soon_30d`.
 */
const SERVED: {
  label: string;
  category: string;
  name: string;
  headline: string;
  reason: string;
  context_summary: string;
  /** What the badge must read once the heading is gone; `null` = suppressed. */
  expectedPill: string | null;
}[] = [
  {
    label: "movement-whole-name — the shopped card",
    category: "tech",
    name: "Ren Zhengfei public appearance?",
    headline: "Ren Zhengfei public appearance odds up 53.5 points",
    reason: "Big odds movement in Ren Zhengfei public appearance?",
    context_summary: "48% chance by December 31",
    expectedPill: "Odds up 53.5 points",
  },
  {
    label: "movement-truncated-name — the backend's own `...` cut",
    category: "weather",
    name: "How many tropical cyclones will make landfall in China during 2026?",
    headline:
      "How many tropical cyclones will make landfall in China... odds down 33.1 points",
    reason:
      "Big odds movement in How many tropical cyclones will make landfall in China during 2026?",
    // The one card of the 244 whose CAPTION was the restatement too.
    context_summary:
      "How many tropical cyclones will make landfall in China... odds down 33.1 points",
    // Suppressed: stripped, it is word-for-word the caption beneath it (#4403).
    expectedPill: null,
  },
  {
    label: "movement — second specimen, different category",
    category: "economics",
    name: "Will McCormick merge with Unilever Foods?",
    headline: "Will McCormick merge with Unilever Foods odds down 50 points",
    reason: "Big odds movement in Will McCormick merge with Unilever Foods?",
    context_summary: "78% chance by December 31, 2027",
    expectedPill: "Odds down 50 points",
  },
  {
    label: "shifted-since — a third template",
    category: "politics",
    name: "Senate passes Clarity Act?",
    headline: "Senate passes Clarity Act shifted since Sep 15",
    reason: "Senate passes Clarity Act? has shifted since Sep 15",
    context_summary: "8% chance by October 31",
    // Suppressed, not promoted: stripped to "Shifted since Sep 15" it is a subset
    // of the served `reason`, and #6560 ruled the reason clause stays so the badge
    // "can only lose ground, never gain it". The heading stops being repeated; the
    // category name comes back to the row. That clause is deliberately untouched.
    expectedPill: null,
  },
  {
    label: "resolving-soon — the 7-card majority, heading with no `?`",
    category: "economics",
    name: "Velo Point of Sale Growth in September",
    headline: "Velo Point of Sale Growth in September resolves within a month",
    reason: "Velo Point of Sale Growth in September resolves within a month",
    context_summary: "Resolves within a month",
    // Suppressed: behind the heading it says only what the caption already says.
    expectedPill: null,
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
      id: 6903,
      name: served.name,
      llm_sport_category: served.category,
      resolution_date: "2027-01-01T04:59:00Z",
      source_count: 2,
      resolved: false,
      top_outcomes: [
        { name: "December 31", probability: 0.48 },
        { name: "October 31", probability: 0.36 },
      ],
    },
  } as unknown as FeedItem;
}

const render = (served: (typeof SERVED)[number]) =>
  renderToStaticMarkup(<FeedCard item={futuresItem(served)} />);

function pillText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-headline-pill"[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

function captionText(html: string): string | null {
  const m = html.match(/data-testid="futures-card-caption"[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

/** The heading's own words, so "restates" is not a bare substring test — the two
 *  strings differ in punctuation and case on four of the five specimens. */
function words(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => w.length > 2);
}

function restatesHeading(text: string, name: string): boolean {
  const seen = new Set(words(text));
  const nameWords = words(name);
  return nameWords.length > 0 && nameWords.every((w) => seen.has(w));
}

/** The BEFORE predicate, written independently of the helper under test: does the
 *  served string OPEN with this card's heading? A character comparison, because on
 *  the cyclone specimen the backend has already cut the name mid-question — so a
 *  word-set test (`restatesHeading`) reads that card as innocent and would make the
 *  guard vacuous on exactly the specimen the reader complained about. */
function opensWithHeading(text: string, name: string): boolean {
  const heading = name.replace(/\s*\?\s*$/, "");
  const k = Math.min(30, heading.length);
  return (
    k > 0 && text.slice(0, k).toLowerCase() === heading.slice(0, k).toLowerCase()
  );
}

describe("#6903 — the badge over a futures heading does not restate it", () => {
  test.each(SERVED)(
    "$label — the served headline restates the heading; the rendered badge does not",
    (served) => {
      // The BEFORE, asserted on the wire. The day the backend stops prefixing the
      // name this line fails, and the guard is retired deliberately rather than
      // going quietly vacuous.
      expect(opensWithHeading(served.headline, served.name)).toBe(true);

      const pill = pillText(render(served));
      expect(pill).toBe(served.expectedPill);
      if (pill !== null) {
        expect(restatesHeading(pill, served.name)).toBe(false);
      }
    },
  );

  test("the shopped card finally says what moved, in a badge that fits", () => {
    // The whole point. The old badge was 50 characters and rendered as "Ren
    // Zhengfei public appearanc…"; the movement never reached the reader.
    const shopped = SERVED[0];
    const pill = pillText(render(shopped))!;
    expect(pill).toBe("Odds up 53.5 points");
    expect(pill).toContain("53.5");
    expect(pill.length).toBeLessThan(shopped.headline.length - 25);
  });

  test("the cyclone card's CAPTION stops being a clipped copy of its own heading", () => {
    // The one card of the 244 that served the restatement as `context_summary`, so
    // the sentence under the heading was the heading again, cut mid-clause.
    const cyclone = SERVED[1];
    const caption = captionText(render(cyclone))!;
    expect(caption).toBe("Odds down 33.1 points");
    expect(restatesHeading(caption, cyclone.name)).toBe(false);
  });

  test.each(SERVED)(
    "$label — the caption never loses a claim the payload carried",
    (served) => {
      // A rule that only ever removes copy is indistinguishable from deleting the
      // line, so every specimen must still caption something — and whatever it
      // captions must not open with the heading either (the truncated arm reaches
      // the reader through this string, not through the badge).
      const caption = captionText(render(served));
      expect(caption).toBeTruthy();
      expect(opensWithHeading(caption!, served.name)).toBe(false);
    },
  );

  describe("NEGATIVE CONTROLS — the strip fires on a restatement and nothing else", () => {
    test("a headline that merely MENTIONS the heading later is untouched", () => {
      // #6560's shape: the name is a TAIL, which `stripMarketNameTail` handles and
      // this helper must not touch — otherwise two rules would fight over one string.
      expect(
        stripCardTitleHead(
          "Arsenal (49%) leads English Premier League Champion",
          "English Premier League Champion",
        ),
      ).toBe("Arsenal (49%) leads English Premier League Champion");
    });

    test("a headline that says something new keeps every word", () => {
      expect(
        stripCardTitleHead("New favorite: Ciryl Gane (68%)", "Who will be UFC Heavyweight champion at the end of 2026?"),
      ).toBe("New favorite: Ciryl Gane (68%)");
    });

    test("an ellipsis that is not THIS card's heading is not a head", () => {
      // The truncated arm keys on the name, not on the punctuation: a served string
      // may contain "..." for its own reasons.
      expect(
        stripCardTitleHead("Chicago leads... Boston up 7 points today", "Where will it rain this weekend (Sep 19 - Sep 20)?"),
      ).toBe("Chicago leads... Boston up 7 points today");
    });

    test("a string that is ONLY the heading yields nothing, so the chain moves on", () => {
      expect(stripCardTitleHead("Velo Point of Sale Growth in September", "Velo Point of Sale Growth in September")).toBe("");
      const item = {
        type: "futures",
        context_summary: "Velo Point of Sale Growth in September",
        headline: null,
        reason: "Resolves within a month",
        data: { name: "Velo Point of Sale Growth in September" },
      } as unknown as FeedItem;
      expect(feedContextSnippet(item)).toBe("Resolves within a month");
    });

    test("no market name, no strip", () => {
      // The #4265 parity record carries no `name`; both clients must agree there.
      expect(stripCardTitleHead("Odds up 3 points", undefined)).toBe("Odds up 3 points");
      expect(stripCardTitleHead("Odds up 3 points", "")).toBe("Odds up 3 points");
    });
  });
});
