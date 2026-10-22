/**
 * #10346 pilot — three supported highlights for ONE completed MLB game, shown
 * only when the page is opened with `?highlights=preview`.
 *
 * This is a reversible experiment, not a ranker. The three stories were chosen
 * by hand against the evidence below; nothing here scores, sorts or generalises
 * to another event. With the parameter absent, or on any other event, the page
 * renders exactly what it rendered before. Removing the experiment is deleting
 * this file, its component and the one mount on the event page.
 *
 * EVIDENCE (receipts in artifacts/discover-10346-highlights-pilot-20261022/):
 *   Official result — MLB Stats API, gamePk 849851 (boxscore-849851.json, and
 *     feedlive-849851-excerpt.json for the event→gamePk binding and clocks),
 *     AL Wild Card Series game 1 of 3, Final: Boston 0, New York Yankees 9.
 *     Schlittler 6.1 IP, 10 K, 2 H, 0 ER, 117 pitches (winning pitcher).
 *     Rice 4-for-5, 2 HR (5th inning, 0 on; 8th inning, 3 on), 6 RBI.
 *     Box score: "First pitch: 8:15 PM." (ET), "T: 3:01."
 *   Chances — the values this page already serves (served-admission-excerpt.json):
 *     Schlittler 10+ strikeouts: Kalshi `pregame_mark` 0.185 (outcome 237550446).
 *       Strikeouts are outside the typed after-set, so this is the only admitted
 *       value. The page serves no pin instant for it; observedAt is the stored
 *       Kalshi row carrying that same 0.185 (bid 18 / ask 19).
 *     Rice 2+ home runs: the typed one-number expectation, `blend_mean` 0.0155,
 *       observed at the Kalshi pin 2026-09-29T23:50:23.519Z, from Kalshi 0.02
 *       (237550483) and Polymarket 0.011 (238585485), both `pregame_pin_5509`.
 *       Shown as a whole percent: 2%. It is "2 OR MORE", not exactly two.
 *     Yankees win the series (Kalshi outcome 235705604, Series Winner): 56%
 *       (bid 55 / ask 57) recorded 2026-09-29T23:51:28.157Z; 80.5% (bid 79 /
 *       ask 82) recorded 2026-09-30T03:55:42.969Z, the first stored row after
 *       the final out. Same outcome id both times.
 *
 * WHAT THE COPY MAY NOT SAY: any clock interval ("N min before first pitch",
 * "after the final out") — the reader sees "Pregame" / "After Game 1" and the
 * recorded time; "exactly two homers"; "the win moved the series by N points"
 * (after Game 1, not because of it); a present-tense series standing; contract
 * mechanics (bids, asking prices); or anything about Game 2.
 */

export const HIGHLIGHTS_PREVIEW_PARAM = "highlights";
export const HIGHLIGHTS_PREVIEW_VALUE = "preview";

export type QuoteSource = "Kalshi" | "Polymarket";

export interface QuoteContributor {
  source: QuoteSource;
  outcomeId: number;
  /** 0–1. */
  probability: number;
  /** ISO instant this contributor was observed. */
  observedAt: string;
}

export interface HighlightQuote {
  /** The phase, in reader words. Never a clock interval. */
  when: "Pregame" | "After Game 1";
  /** The exact question the number answers, in reader words. */
  question: string;
  /** 0–1 — the value the page serves for this question. */
  probability: number;
  /** Whole-percent display, for a blended value carried to more precision than it earns. */
  whole?: boolean;
  /** ISO instant of the shown value. */
  observedAt: string;
  /** Where the number comes from — the exact-source details. */
  contributors: readonly QuoteContributor[];
}

/** A count against its line: one mark per official event, the line it needed. */
export interface CountVisual {
  kind: "count";
  /** Singular unit of one mark. */
  unit: string;
  actual: number;
  /** The question's line: "N or more". */
  line: number;
  /** Optional label under each counted mark, in order. */
  marks?: readonly string[];
}

export interface EventHighlight {
  id: string;
  /** Who or what the story is about. Distinct per highlight. */
  subject: string;
  /** The official fact. */
  headline: string;
  detail: string;
  /** Count stories show the result against the line; the series story pairs two chances. */
  visual?: CountVisual;
  before: HighlightQuote;
  after?: HighlightQuote;
  /** Why it earns its slot — for the reviewer and the artifact, not the page. */
  rationale: string;
}

export interface EventHighlightsPreview {
  eventId: number;
  officialSource: string;
  highlights: readonly EventHighlight[];
}

const BOS_NYY_WILD_CARD_G1: EventHighlightsPreview = {
  eventId: 15319563,
  officialSource: "Official MLB box score",
  highlights: [
    {
      id: "schlittler-10k",
      subject: "Cam Schlittler",
      headline: "Schlittler struck out 10",
      detail: "6⅓ scoreless innings, two hits allowed",
      visual: { kind: "count", unit: "strikeout", actual: 10, line: 10 },
      before: {
        when: "Pregame",
        question: "10+ strikeouts",
        probability: 0.185,
        observedAt: "2026-09-29T23:52:03.774Z",
        contributors: [
          { source: "Kalshi", outcomeId: 237550446, probability: 0.185, observedAt: "2026-09-29T23:52:03.774Z" },
        ],
      },
      rationale:
        "Founder-labelled lead for this game (#5105, Oct 2). The founder's note offers the middle-range idea as a hypothesis, not a rule. Pitcher story; no overlap with the hitting or series stories.",
    },
    {
      id: "rice-2hr",
      subject: "Ben Rice",
      headline: "Rice homered twice, the second a grand slam",
      detail: "4 for 5; drove in 6 of the Yankees' 9 runs",
      visual: { kind: "count", unit: "home run", actual: 2, line: 2, marks: ["5th", "8th · slam"] },
      before: {
        when: "Pregame",
        question: "2+ home runs",
        probability: 0.0155,
        whole: true,
        observedAt: "2026-09-29T23:50:23.519Z",
        contributors: [
          { source: "Kalshi", outcomeId: 237550483, probability: 0.02, observedAt: "2026-09-29T23:50:23.519Z" },
          { source: "Polymarket", outcomeId: 238585485, probability: 0.011, observedAt: "2026-09-29T23:50:22.756Z" },
        ],
      },
      rationale:
        "The offensive story: 6 of the 9 runs. Chosen for share of the result, not rarity. Replaces the Yankees 8+ runs prop, which would retell Rice's runs.",
    },
    {
      id: "nyy-series-g1",
      subject: "Yankees",
      headline: "Yankees won Game 1, 9–0",
      detail: "Yankees led the best-of-three 1–0 after Game 1",
      before: {
        when: "Pregame",
        question: "the Yankees winning the series",
        probability: 0.56,
        observedAt: "2026-09-29T23:51:28.157Z",
        contributors: [
          { source: "Kalshi", outcomeId: 235705604, probability: 0.56, observedAt: "2026-09-29T23:51:28.157Z" },
        ],
      },
      after: {
        when: "After Game 1",
        question: "the Yankees winning the series",
        probability: 0.805,
        observedAt: "2026-09-30T03:55:42.969Z",
        contributors: [
          { source: "Kalshi", outcomeId: 235705604, probability: 0.805, observedAt: "2026-09-30T03:55:42.969Z" },
        ],
      },
      rationale:
        "The consequence: a different question on a different clock from both player stories. Two dated observations of the same outcome bracket the game; worded 'after Game 1', never 'because of'.",
    },
  ],
};

const PREVIEWS: ReadonlyMap<number, EventHighlightsPreview> = new Map([
  [BOS_NYY_WILD_CARD_G1.eventId, BOS_NYY_WILD_CARD_G1],
]);

/**
 * The preview for this event, or null. Null unless the parameter is exactly
 * `preview`, the event is one we hold evidence for, and the game is completed —
 * a highlight about a result never renders before the result exists.
 */
export function highlightsPreviewFor(
  eventId: number | null | undefined,
  status: string | null | undefined,
  param: string | null | undefined,
): EventHighlightsPreview | null {
  if (param !== HIGHLIGHTS_PREVIEW_VALUE) return null;
  if (status !== "completed") return null;
  if (eventId == null) return null;
  return PREVIEWS.get(eventId) ?? null;
}

/** "18.5%", "2%", "80.5%" — one decimal only when the quote carries one, none when `whole`. */
export function formatQuotePercent(probability: number, whole = false): string {
  if (whole) return `${Math.round(probability * 100)}%`;
  const pct = Math.round(probability * 1000) / 10;
  return `${Number.isInteger(pct) ? pct.toFixed(0) : pct.toFixed(1)}%`;
}

const RECORDED = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

/** "Sep 29, 7:52 PM ET" — the local time at the ballpark the value was recorded. */
export function formatRecordedAt(iso: string): string {
  return `${RECORDED.format(new Date(iso))} ET`;
}

/** "Kalshi" or "Kalshi + Polymarket" — the short source mark. */
export function sourceMark(quote: HighlightQuote): string {
  return Array.from(new Set(quote.contributors.map((c) => c.source))).join(" + ");
}

/** The DOM id of the catalogue wrapper the highlights link opens. */
export const ALL_MARKETS_ANCHOR_ID = "all-markets";
