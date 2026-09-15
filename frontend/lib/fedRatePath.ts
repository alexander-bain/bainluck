/**
 * The rate-path card's heading, derived from the columns it is about to draw.
 *
 * #2870 — the heading was the literal `2026 rate path` sitting ~90px above
 * three columns whose own subheadings read `Jan 2027 meeting`, `Mar 2027
 * meeting`, `Apr 2027 meeting`. Nothing bound the two together, so the card
 * contradicted itself on one screen and needed no external control to prove
 * it. Same class as #2674, and the same remedy: stop writing the label by
 * hand and compute it from the data that is rendered, so the two cannot
 * disagree by construction.
 *
 * The backend half of #2870 widens which meetings reach the card, which is
 * exactly what makes a hardcoded year unfixable by editing it — the set now
 * legitimately spans two calendar years.
 */

export interface RatePathMeeting {
  /** `YYYYMM`, as built by `routes/economics.py`. 0 when the market's title
   *  carried no parseable month+year. */
  sort_key?: number | null;
  /** e.g. `"Sep 2026 meeting"`. */
  date?: string | null;
}

/**
 * The year a column is about, or null if it cannot be read.
 *
 * `sort_key` is preferred because it is what the columns are SORTED by, so a
 * heading derived from it can never disagree with the order on screen.
 *
 * ⚠️ `sort_key` is 0, not null, when the backend could not parse a month+year
 * out of the market title. Dividing that by 100 yields year 0 — a plausible
 * number that would quietly become `"0–2027 rate path"`. The floor below is
 * the guard, and it is why the fallback to `date` exists at all.
 */
export function meetingYear(m: RatePathMeeting): number | null {
  const key = m?.sort_key;
  if (typeof key === "number" && Number.isFinite(key) && key >= 100000) {
    return Math.floor(key / 100);
  }
  const match = /\b(20\d{2})\b/.exec(m?.date ?? "");
  return match ? Number(match[1]) : null;
}

/**
 * The heading for a set of rendered rate-path columns.
 *
 *   []                          -> "Rate path"        (no year claimed)
 *   [Jan 2027, Mar 2027]        -> "2027 rate path"
 *   [Sep 2026 … Apr 2027]       -> "2026–27 rate path"
 *
 * The empty case drops the year rather than guessing one: the card's heading
 * renders outside the heatmap, so it is still on screen when there are no
 * columns, and a year printed over nothing is the very defect this fixes.
 */
export function ratePathHeading(meetings: readonly RatePathMeeting[] | null | undefined): string {
  const years = (meetings ?? [])
    .map(meetingYear)
    .filter((y): y is number => y !== null);

  if (years.length === 0) return "Rate path";

  const first = Math.min(...years);
  const last = Math.max(...years);
  if (first === last) return `${first} rate path`;

  // Same century reads better abbreviated ("2026–27"); anything else is
  // spelled out rather than rendered as a confusing two-digit tail.
  const abbreviated =
    Math.floor(first / 100) === Math.floor(last / 100)
      ? String(last).slice(2)
      : String(last);
  return `${first}–${abbreviated} rate path`;
}
