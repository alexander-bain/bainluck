/**
 * #4403 — the /sports futures card header row prints whole strings at 390px.
 *
 * The defect was not "text is truncated". Truncation is the correct behaviour for
 * a row that is over-subscribed; the defect was that the row was over-subscribed
 * by a DUPLICATE. The pill and the reason line come out of the same backend
 * branch, so the pill was spending 43–56% of a sentence to say what the sentence
 * one row below said in full, and it took the category chip down with it (41–59%
 * gone, leaving "🥋 …").
 *
 * These tests pin the rule from BOTH sides, because a rule that only ever
 * suppresses is indistinguishable from deleting the pill:
 *   - an echo pill is dropped and the category NAME comes back;
 *   - a pill that says something new still renders, and THEN the category name
 *     is the thing that yields.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { headlineEchoesReason } from "@/lib/headlineEcho";

describe("#4403 headlineEchoesReason — the redundancy test itself", () => {
  test("the live pill/reason pairs measured on production are all echoes", () => {
    // Verbatim from `/sports` at 390px, production master 35d0b359, 2026-09-09.
    const pairs: [string, string][] = [
      [
        "Alexander Volkanovski leads at 48%",
        "Alexander Volkanovski (48%) leads Featherweight Title Holder on Dec 31, 2026?",
      ],
      [
        "Justin Gaethje leads at 83%",
        "Justin Gaethje (83%) leads Lightweight Title Holder on Dec 31, 2026?",
      ],
      [
        "New favorite: USA (65%)",
        "New favorite: USA (65%) now leads Women's FIBA World Cup Champion",
      ],
      [
        "Los Angeles Rams leads at 14%",
        "Los Angeles Rams (14%) leads NFL Super Bowl Winner",
      ],
    ];
    for (const [headline, reason] of pairs) {
      expect(headlineEchoesReason(headline, reason)).toBe(true);
    }
  });

  test("a headline that contributes a word the reason lacks is NOT an echo", () => {
    expect(
      headlineEchoesReason(
        "Buffalo Bills up 12 points today",
        "Alexander Volkanovski (48%) leads Featherweight Title Holder",
      ),
    ).toBe(false);
  });

  test("a DIFFERENT number is not an echo, even with identical words", () => {
    // The trap this guards: strip the digits and "leads at 48%" echoes
    // "leads at 12%". Digits are significant tokens for exactly this reason.
    expect(headlineEchoesReason("Team X leads at 48%", "Team X leads at 12%")).toBe(false);
    expect(headlineEchoesReason("Team X leads at 48%", "Team X leads at 48% now")).toBe(true);
  });

  test("no reason means no echo — the pill is then the only copy on the card", () => {
    expect(headlineEchoesReason("New favorite: USA (65%)", null)).toBe(false);
    expect(headlineEchoesReason("New favorite: USA (65%)", "")).toBe(false);
    expect(headlineEchoesReason("New favorite: USA (65%)", "   ")).toBe(false);
  });

  test("no headline is never an echo (nothing to suppress)", () => {
    expect(headlineEchoesReason(null, "anything at all")).toBe(false);
    expect(headlineEchoesReason("", "anything at all")).toBe(false);
    // A headline of pure punctuation contributes no significant token; it must
    // not be reported as "contained", which would be true vacuously.
    expect(headlineEchoesReason("—", "anything at all")).toBe(false);
  });

  test("punctuation and word order do not decide the answer", () => {
    expect(headlineEchoesReason("Volkanovski leads at 48%", "48% — Volkanovski, leads")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// The rendered card. Rendering FeedCard needs its whole feed-item shape, so the
// row is asserted through the component that owns the decision rather than
// through a hand-built DOM: a test that re-implements the conditional cannot
// fail when the component's copy of it changes.
// ---------------------------------------------------------------------------

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import type { FeedItem } from "@/lib/types";

const REASON =
  "Alexander Volkanovski (48%) leads Featherweight Title Holder on Dec 31, 2026?";
const ECHO_PILL = "Alexander Volkanovski leads at 48%";

function futuresItem(headline: string | null, reason: string | null): FeedItem {
  return {
    type: "futures",
    score: 80,
    headline,
    reason,
    data: {
      id: 4403,
      name: "Featherweight Title Holder on Dec 31, 2026?",
      llm_sport_category: "mma",
      resolution_date: "2026-12-31T00:00:00Z",
      source_count: 2,
      resolved: false,
      top_outcomes: [
        { name: "Alexander Volkanovski", probability: 0.48 },
        { name: "Movsar Evloev", probability: 0.41 },
      ],
    },
  } as unknown as FeedItem;
}

const card = (headline: string | null, reason: string | null) =>
  renderToStaticMarkup(<FeedCard item={futuresItem(headline, reason)} />);

describe("#4403 the rendered header row", () => {
  test("an echo pill is dropped and the category NAME is printed in full", () => {
    const html = card(ECHO_PILL, REASON);
    // The sentence survives exactly once — in the reason line, whole.
    expect(html).toContain("Alexander Volkanovski (48%) leads Featherweight Title Holder");
    expect(html).not.toContain(">Alexander Volkanovski leads at 48%<");
    // …and the chip has its name back, which is the pixels the pill gave up.
    expect(html).toContain("MMA");
  });

  test("a non-echo pill still renders, and THEN the category name yields to it", () => {
    const html = card("Volkanovski odds up 12 points today", REASON);
    expect(html).toContain("Volkanovski odds up 12 points today");
    // The emoji still marks the category; the word does not compete for the row.
    expect(html).not.toContain("MMA");
  });

  test("with no reason line the pill always renders — nothing else carries it", () => {
    expect(card("New favorite: USA (65%)", null)).toContain("New favorite: USA (65%)");
  });

  test("the resolution date is never the thing that yields (#4244 held)", () => {
    expect(card(ECHO_PILL, REASON)).toMatch(/Resolves [A-Z][a-z]{2} \d+, 2026/);
  });
});
