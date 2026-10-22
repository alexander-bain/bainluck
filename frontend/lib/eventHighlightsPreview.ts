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
 *   Official result — MLB Stats API, gamePk 849851 (boxscore + feed/live),
 *     AL Wild Card Series game 1 of 3, Final: Boston 0, New York Yankees 9.
 *     Schlittler 6.1 IP, 10 K, 2 H, 0 ER, 117 pitches (winning pitcher).
 *     Rice 4-for-5, 2 HR, 6 RBI; first HR bottom 5 (0–2), grand slam bottom 8 (0–9).
 *     First pitch 2026-09-30T00:15:26.152Z; final play ended 03:16:33.590Z.
 *   Dated quotes — our own `futures_odds_snapshots`, read per outcome id:
 *     Schlittler 10+ strikeouts (Kalshi outcome 237550446): 18.5%, bid 18 / ask 19,
 *       at 2026-09-29T23:52:03.774Z — the last stored observation before first pitch.
 *     Rice 2+ home runs (Kalshi outcome 237550483): 2%, bid 0 / ask 2, same instant.
 *       The 2% is the midpoint of a book with no buyers. It is "2 OR MORE", not
 *       exactly two. Polymarket's Rice O/U 1.5 (238585485) is the same question
 *       and is not used as a second source or a second story.
 *     Yankees win the series (Kalshi outcome 235705604): 56%, bid 55 / ask 57, at
 *       2026-09-29T23:51:28.157Z; 80.5%, bid 79 / ask 82, at 2026-09-30T03:55:42.969Z,
 *       the first stored observation after the final out.
 *
 * WHAT THE COPY MAY NOT SAY: "at first pitch" (the quotes are ~23 minutes
 * earlier), "exactly two homers", "the win moved the series by 24 points"
 * (after Game 1, not because of it), or anything about Game 2.
 */

export const HIGHLIGHTS_PREVIEW_PARAM = "highlights";
export const HIGHLIGHTS_PREVIEW_VALUE = "preview";

export interface HighlightQuote {
  /** "Before" unless the fixture names the moment, e.g. "After Game 1". */
  label?: string;
  /** The exact question the number answers, in reader words. */
  question: string;
  /** 0–1. */
  probability: number;
  source: "Kalshi" | "Polymarket";
  /** ISO instant the quote was observed. */
  observedAt: string;
  /** Plain-English position of that instant relative to the game. */
  when: string;
  /** Present only when the quote needs one honest qualifier. */
  caveat?: string;
}

export interface EventHighlight {
  id: string;
  /** Who or what the story is about. Distinct per highlight. */
  subject: string;
  /** The official fact. */
  headline: string;
  detail: string;
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
      before: {
        question: "10+ strikeouts",
        probability: 0.185,
        source: "Kalshi",
        observedAt: "2026-09-29T23:52:03.774Z",
        when: "23 min before first pitch",
      },
      rationale:
        "Founder-labelled lead for this game (#5105, Oct 2): a middle-range expectation that came true reads better than the rarest hit. Pitcher story; no overlap with the hitting or series stories.",
    },
    {
      id: "rice-2hr",
      subject: "Ben Rice",
      headline: "Rice homered twice, the second a grand slam",
      detail: "4 for 5; drove in 6 of the Yankees' 9 runs",
      before: {
        question: "2+ home runs",
        probability: 0.02,
        source: "Kalshi",
        observedAt: "2026-09-29T23:52:03.774Z",
        when: "23 min before first pitch",
        caveat: "No one was bidding; 2% was the asking price",
      },
      rationale:
        "The offensive story: 6 of the 9 runs. Chosen for share of the result, not rarity. Replaces the Yankees 8+ runs prop, which would retell Rice's runs.",
    },
    {
      id: "nyy-series-g1",
      subject: "Yankees",
      headline: "Yankees won Game 1, 9–0",
      detail: "Best-of-three Wild Card Series, Yankees lead 1–0",
      before: {
        question: "Yankees win the series",
        probability: 0.56,
        source: "Kalshi",
        observedAt: "2026-09-29T23:51:28.157Z",
        when: "24 min before first pitch",
      },
      after: {
        label: "After Game 1",
        question: "Yankees win the series",
        probability: 0.805,
        source: "Kalshi",
        observedAt: "2026-09-30T03:55:42.969Z",
        when: "39 min after the final out",
      },
      rationale:
        "The consequence: a different question on a different clock from both player stories. Two dated observations bracket the game; worded 'after Game 1', never 'because of'.",
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

/** "18.5%", "2%", "80.5%" — one decimal only when the quote carries one. */
export function formatQuotePercent(probability: number): string {
  const pct = Math.round(probability * 1000) / 10;
  return `${Number.isInteger(pct) ? pct.toFixed(0) : pct.toFixed(1)}%`;
}

/** The DOM id of the catalogue wrapper the highlights link opens. */
export const ALL_MARKETS_ANCHOR_ID = "all-markets";
