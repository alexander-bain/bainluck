/**
 * Standard "As of" timestamp formatter (Ruling 198-B & Wording Sweep #12759):
 * - Same calendar day as `now`: `"As of 1:29 PM"`
 * - Older day in the same year: `"As of Nov 13"`
 * - Different calendar year: `"As of Nov 13, 2025"`
 *
 * Uses `Intl.DateTimeFormat` directly so prototype spies on `toLocaleDateString`
 * remain undisturbed, and returns `null` on empty or unparseable input.
 */
const TIME_FMT = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
});

const MONTH_DAY_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});

const MONTH_DAY_YEAR_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

export function formatAsOfStamp(
  iso: string | null | undefined,
  now: Date = new Date(),
): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;

  const sameYear = at.getFullYear() === now.getFullYear();
  const sameDay =
    sameYear &&
    at.getMonth() === now.getMonth() &&
    at.getDate() === now.getDate();

  if (sameDay) {
    return `As of ${TIME_FMT.format(at)}`;
  }

  if (sameYear) {
    return `As of ${MONTH_DAY_FMT.format(at)}`;
  }

  return `As of ${MONTH_DAY_YEAR_FMT.format(at)}`;
}
