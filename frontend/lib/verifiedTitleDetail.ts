/**
 * #9387 / #10224 — the web futures detail's reading of `representation=verified_title`.
 *
 * The server (PR #10216) answers an opted-in title page with ONE current number
 * per outcome across every venue that provably asks the same question. Everything
 * here is a pure reading of that payload: no blend arithmetic, no fixture ids, no
 * synthesized chart points.
 *
 * Three rules carry the truth of the page:
 *   1. A hero names the contributors of the outcome it SHOWS, never the market's
 *      union; one contributor is one source, never "aggregated".
 *   2. The chart is the requested source's own `/history` series — the de-vigged
 *      consensus the source page has always drawn — labelled as that source's
 *      history, with nothing appended at the end to meet the current number.
 *      #10244: it was briefly the opted-in `/probability-timeline`, whose
 *      sportsbook line is a median of raw, margin-inclusive prices (Bills 13.3%
 *      where the sportsbooks' own number was 11.2%), so a line captioned
 *      "Sportsbooks history" sat above the source it named.
 *   3. Every other number on the page that restates an outcome's current value
 *      is that outcome's row in this detail, by id (#10243).
 */
import type {
  FuturesMarketDetailResponse,
  FuturesOutcome,
  FuturesRepresentation,
  RelatedEvent,
} from "./types";

export const VERIFIED_TITLE: FuturesRepresentation = "verified_title";

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

/**
 * "Sportsbooks history" — whose history the chart draws on a verified page.
 *
 * The chart is `/history` for this market, which is this market's own source
 * by construction, so the label is that source's. `null` in source mode (the
 * card is unchanged there) and for a source outside the vocabulary, which is
 * never given an invented name.
 */
export function verifiedHistoryLabel(
  detail: FuturesMarketDetailResponse | null | undefined,
): string | null {
  const source = detail?.source;
  if (!isVerifiedTitle(detail) || !isContributor(source)) return null;
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

/**
 * #10243 — "Games This Week" on the detail's own numbers.
 *
 * `/related-events` serves each team's SOURCE value, so on a verified page its
 * rows printed "Buffalo Bills 11%" below a hero and table reading 13%: one page,
 * two numbers for one team. In verified mode each row's number is the detail's
 * own row for that `outcome_id` — the number the table prints — or no number
 * at all when the row cannot be found (an older payload with no id, or an
 * outcome this detail does not carry). A source value is never printed beside
 * verified ones. Source mode returns the events untouched.
 */
export function relatedEventsOnDetailScale(
  detail: FuturesMarketDetailResponse | null | undefined,
  events: RelatedEvent[],
): RelatedEvent[] {
  if (!isVerifiedTitle(detail) || !Array.isArray(detail?.outcomes)) return events;
  const rows = new Map(detail.outcomes.map((row) => [row.id, row]));
  return events.map((event) => ({
    ...event,
    linked_teams: event.linked_teams.map((team) => {
      const row = typeof team.outcome_id === "number" ? rows.get(team.outcome_id) : undefined;
      return {
        ...team,
        probability: row?.probability ?? null,
        american_odds: row?.american_odds ?? null,
      };
    }),
  }));
}
