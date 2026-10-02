/**
 * #9387 / #10224 — the web futures detail's reading of `representation=verified_title`.
 *
 * The server (PR #10216) answers an opted-in title page with ONE current number
 * per outcome across every venue that provably asks the same question, and its
 * timeline keeps the requested source's own history, labelled by
 * `history_basis`. Everything here is a pure reading of those two payloads:
 * no blend arithmetic, no fixture ids, no synthesized chart points.
 *
 * Three rules carry the truth of the page:
 *   1. A hero names the contributors of the outcome it SHOWS, never the market's
 *      union; one contributor is one source, never "aggregated".
 *   2. The chart's lines are the requested source's history under that
 *      response's own `history_basis` label — geometry unchanged, nothing
 *      appended at the end to meet the current number.
 *   3. When the hero and the chart's current column disagree, the chart is
 *      asked again once; if they still disagree the history stays and the
 *      chart's current numbers go.
 */
import type {
  FuturesHistoryResponse,
  FuturesMarketDetailResponse,
  FuturesOutcome,
  FuturesOutcomeHistory,
  FuturesRepresentation,
  ProbabilityTimelineResponse,
} from "./types";

export const VERIFIED_TITLE: FuturesRepresentation = "verified_title";

/** Up to 50 lines (the route's ceiling), so a reader's manual pick from the
 *  32-team table still has its history; the route keeps its own order. */
export const VERIFIED_TIMELINE_TOP = 50;

const CONTRIBUTORS = ["odds_api", "kalshi", "polymarket"] as const;
export type Contributor = (typeof CONTRIBUTORS)[number];

/** Notice 33: the sportsbook venue is "Sportsbooks", never "books". */
const CONTRIBUTOR_LABEL: Record<Contributor, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};

const isContributor = (value: unknown): value is Contributor =>
  typeof value === "string" && (CONTRIBUTORS as readonly string[]).includes(value);

/** The EFFECTIVE representation of a response. Anything but the exact string
 *  — absent (old server), malformed, a future value — is source mode. */
export function effectiveRepresentation(
  payload: { representation?: unknown } | null | undefined,
): FuturesRepresentation {
  return payload?.representation === VERIFIED_TITLE ? VERIFIED_TITLE : "source";
}

export function isVerifiedTitle(
  payload: { representation?: unknown } | null | undefined,
): boolean {
  return effectiveRepresentation(payload) === VERIFIED_TITLE;
}

/**
 * A contributor array in the server's vocabulary, in canonical order.
 *
 * `null` means "this cannot be labelled": not an array, or any key outside the
 * vocabulary. The caller then falls back to the source-mode header rather than
 * printing an invented label. An empty array is a real answer (no current
 * contributor) and stays empty.
 */
export function contributorKeys(value: unknown): Contributor[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every(isContributor)) return null;
  return CONTRIBUTORS.filter((key) => value.includes(key));
}

export function contributorLabels(keys: readonly Contributor[]): string[] {
  return keys.map((key) => CONTRIBUTOR_LABEL[key]);
}

/**
 * The hero's source labels for the outcome it displays, or `undefined` for
 * "use the source-mode header". Only an effective verified response has
 * per-outcome contributors; the market-wide union is never consulted here.
 */
export function heroContributorLabels(
  detail: FuturesMarketDetailResponse | null | undefined,
  heroOutcome: FuturesOutcome | null | undefined,
): string[] | undefined {
  if (!isVerifiedTitle(detail) || !heroOutcome) return undefined;
  const keys = contributorKeys(heroOutcome.contributing_sources);
  return keys ? contributorLabels(keys) : undefined;
}

/**
 * Whether a verified hero outcome's value is the requested source's own —
 * the only case where that source's history may draw behind its numeral.
 */
export function heroValueIsSourceOwn(
  detail: FuturesMarketDetailResponse | null | undefined,
  heroOutcome: FuturesOutcome | null | undefined,
): boolean {
  if (!isVerifiedTitle(detail)) return true;
  const keys = contributorKeys(heroOutcome?.contributing_sources);
  return !!keys && keys.length === 1 && keys[0] === detail?.source;
}

/** "Sportsbooks history" — from the timeline response itself, never the detail. */
export function historyBasisLabel(basis: unknown): string | null {
  if (!basis || typeof basis !== "object") return null;
  const { kind, source, market_id } = basis as Record<string, unknown>;
  if (kind !== "single_source" || !isContributor(source)) return null;
  if (typeof market_id !== "number" || !Number.isInteger(market_id)) return null;
  return `${CONTRIBUTOR_LABEL[source]} history`;
}

/**
 * Opted-in detail, made safe to render.
 *
 * Source mode passes through untouched. In verified mode the server already
 * nulls opening and movement on every value another estimator produced, and
 * renumbers `rank` over the verified board — but `rank_change_24h` is still
 * the SOURCE board's rank movement, so beside a verified rank it would pair
 * two estimators. It goes, for every row.
 */
export function sanitizeVerifiedTitleDetail(
  detail: FuturesMarketDetailResponse,
): FuturesMarketDetailResponse {
  if (!isVerifiedTitle(detail) || !Array.isArray(detail.outcomes)) return detail;
  if (detail.outcomes.every((row) => row.rank_change_24h == null)) return detail;
  return {
    ...detail,
    outcomes: detail.outcomes.map((row) =>
      row.rank_change_24h == null ? row : { ...row, rank_change_24h: null },
    ),
  };
}

const hasOwn = (record: object, key: string) =>
  Object.prototype.hasOwnProperty.call(record, key);

/**
 * An opted-in timeline in the shape `FuturesChart` draws.
 *
 * Each metadata row with an id becomes one series, in the route's own order,
 * keyed by its original outcome id; its points are exactly the buckets whose
 * dictionary carries that row's name byte-for-byte. A bucket without the name
 * is a gap and stays one. No point is added at the end: the history's last
 * value is the source's, not the current verified number.
 *
 * `withCurrent: false` drops the current-column metadata entirely — the
 * persistent-disagreement state, where the chart keeps its history and makes
 * no claim about now.
 */
export function timelineToChartHistory(
  timeline: ProbabilityTimelineResponse,
  options: { withCurrent: boolean },
): FuturesHistoryResponse {
  const basisSource =
    timeline.history_basis && isContributor(timeline.history_basis.source)
      ? timeline.history_basis.source
      : typeof timeline.source === "string"
        ? timeline.source
        : "";
  const entries = Array.isArray(timeline.timeline) ? timeline.timeline : [];
  const metas = Array.isArray(timeline.outcomes) ? timeline.outcomes : [];
  const outcomes: FuturesOutcomeHistory[] = metas
    .filter(
      (meta) =>
        typeof meta?.id === "number" &&
        Number.isInteger(meta.id) &&
        typeof meta.name === "string",
    )
    .map((meta) => {
      const history = entries.flatMap((entry) => {
        const values = entry?.outcomes;
        if (!values || typeof values !== "object" || !hasOwn(values, meta.name)) return [];
        const value = values[meta.name];
        if (typeof value !== "number" || !Number.isFinite(value)) return [];
        return [
          {
            timestamp: entry.timestamp,
            probability: value,
            american_odds: null,
            bookmaker: basisSource,
          },
        ];
      });
      const series: FuturesOutcomeHistory = {
        outcome_id: meta.id as number,
        name: meta.name,
        history,
      };
      if (options.withCurrent) {
        series.current_price_available = meta.current_probability != null;
      }
      return series;
    });
  const total = outcomes.reduce((sum, o) => sum + o.history.length, 0);
  const actual = (timeline as { actual_hours?: unknown }).actual_hours;
  return {
    market_id: timeline.market_id,
    market_name: timeline.market_name,
    hours: timeline.hours,
    ...(typeof actual === "number" ? { actual_hours: actual } : {}),
    outcomes,
    total_data_points: total,
    // The /history field's own definition: fewer than 10 points in all.
    sparse: total < 10,
  };
}

const sameKeys = (a: Contributor[] | null, b: Contributor[] | null) =>
  a === null || b === null ? a === b : a.length === b.length && a.every((k, i) => k === b[i]);

/**
 * Do the detail's hero and the chart's current column describe one state?
 *
 * Mode first: a verified hero over a source-mode timeline (or the reverse) is
 * two estimators. In verified mode the corresponding outcome — matched by id,
 * the identity the server maps across — must carry the same value and the same
 * contributors. A hero the timeline does not list has nothing to contradict.
 */
export function chartCurrentAgrees(
  detail: FuturesMarketDetailResponse,
  timeline: ProbabilityTimelineResponse,
  heroId: number | null,
): boolean {
  const mode = effectiveRepresentation(detail);
  if (mode !== effectiveRepresentation(timeline)) return false;
  if (mode !== VERIFIED_TITLE || heroId == null) return true;
  const hero = detail.outcomes?.find((row) => row.id === heroId);
  const meta = (Array.isArray(timeline.outcomes) ? timeline.outcomes : []).find(
    (row) => row.id === heroId,
  );
  if (!hero || !meta) return true;
  if ((hero.probability ?? null) !== (meta.current_probability ?? null)) return false;
  return sameKeys(
    contributorKeys(hero.contributing_sources),
    contributorKeys(meta.contributing_sources),
  );
}

export type VerifiedChartVerdict = "pending" | "agree" | "retry" | "persistent";

/**
 * One retry per detail/range generation. `retriedThisGeneration` is true once
 * the chart has been re-asked for exactly this detail object and range; a
 * mismatch after that is persistent until a new detail or range arrives.
 */
export function verifiedChartVerdict(
  agrees: boolean | null,
  retriedThisGeneration: boolean,
): VerifiedChartVerdict {
  if (agrees === null) return "pending";
  if (agrees) return "agree";
  return retriedThisGeneration ? "persistent" : "retry";
}
