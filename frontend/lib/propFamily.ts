/**
 * Prop-family grouping for the event props body (UX-P036, gap K14).
 *
 * Why this module exists: the backend builds every game prop's props_script key
 * as `f"{market_name}|{outcome_name}"` and sets `label = outcome_name`
 * (`backend/app/routes/events.py:4707`). So the STATISTIC is on the wire and the
 * label drops it — a live MLB game renders 81 rows reading "Tommy White: 4+"
 * with no way to tell a Hits+Runs+RBIs prop from a Hits prop. Measured on
 * Athletics @ Red Sox 2026-08-09: 73 of 81 rows named no statistic, and three
 * families were interleaved into one flat list.
 *
 * `routes/events.py` belongs to the latency lane (#1494), so this recovers the
 * family CLIENT-SIDE from the key that is already paid for.
 *
 * PURE: no I/O, no React, no DB.
 */

/** Separator the backend uses between market name and outcome name in a key. */
export const FAMILY_SEPARATOR = "|";

/**
 * The family (market name) encoded in a props_script key, or null when the key
 * carries none.
 *
 * Null is the IMPORTANT case, not the edge case: the concept-page consumer
 * (`app/event/[domain]/[slug]/page.tsx`, golf/combat) builds marks with
 * `key: mid` — a NUMBER. Those must keep rendering exactly as they do today, so
 * anything without a parseable family degrades to "ungrouped".
 */
export function propFamilyName(key: string | number): string | null {
  if (typeof key !== "string") return null;
  const i = key.indexOf(FAMILY_SEPARATOR);
  if (i <= 0) return null;
  const family = key.slice(0, i).trim();
  return family.length > 0 ? family : null;
}

/**
 * The boilerplate prefix shared by every family name, ending at a `": "`
 * boundary — "Boston vs A's: Hits" and "Boston vs A's: Home Runs" share
 * "Boston vs A's: ", which is the matchup the user is already looking at.
 *
 * Requires **two or more distinct names**: sharedness across families is the
 * only evidence that a prefix is boilerplate rather than meaning. With a single
 * family, "Best Picture: Winner" would otherwise be stripped to "Winner".
 *
 * Returns "" when there is nothing safe to strip.
 */
export function sharedFamilyPrefix(names: string[]): string {
  const distinct = Array.from(new Set(names));
  if (distinct.length < 2) return "";

  // Longest common character prefix across all names.
  let common = distinct[0];
  for (const name of distinct.slice(1)) {
    let i = 0;
    while (i < common.length && i < name.length && common[i] === name[i]) i += 1;
    common = common.slice(0, i);
    if (!common) return "";
  }

  // Retreat to the last ": " boundary so we never cut a word in half.
  const cut = common.lastIndexOf(": ");
  if (cut < 0) return "";
  const prefix = common.slice(0, cut + 2);

  // Never strip a name down to nothing.
  if (distinct.some((n) => n.slice(prefix.length).trim().length === 0)) return "";
  return prefix;
}

/** Apply {@link sharedFamilyPrefix} to a list of family names. */
export function stripSharedFamilyPrefix(names: string[]): string[] {
  const prefix = sharedFamilyPrefix(names);
  if (!prefix) return names;
  return names.map((n) => (n.startsWith(prefix) ? n.slice(prefix.length).trim() : n));
}

export interface PropFamilyGroup<T> {
  /**
   * Display name, already prefix-stripped. `null` means "no family" — the
   * caller must render these exactly as it did before grouping existed.
   */
  name: string | null;
  items: T[];
}

/**
 * Partition items into family groups, preserving the caller's ordering both
 * BETWEEN groups (by first appearance) and WITHIN them.
 *
 * When no item carries a family, returns a single `{ name: null }` group — so a
 * caller can branch on `groups.length === 1 && groups[0].name === null` and emit
 * its original markup untouched.
 */
export function groupByPropFamily<T>(
  items: T[],
  keyOf: (item: T) => string | number,
): PropFamilyGroup<T>[] {
  const named = new Map<string, T[]>();
  const unfamiliar: T[] = [];
  const order: string[] = [];

  for (const item of items) {
    const family = propFamilyName(keyOf(item));
    if (family == null) {
      unfamiliar.push(item);
      continue;
    }
    let bucket = named.get(family);
    if (!bucket) {
      bucket = [];
      named.set(family, bucket);
      order.push(family);
    }
    bucket.push(item);
  }

  if (order.length === 0) return [{ name: null, items }];

  const display = stripSharedFamilyPrefix(order);
  const groups: PropFamilyGroup<T>[] = order.map((family, i) => ({
    name: display[i],
    items: named.get(family) as T[],
  }));

  // Mixed payloads shouldn't happen, but a family-less remainder must never be
  // dropped on the floor — it trails the named groups, in its original order.
  if (unfamiliar.length > 0) groups.push({ name: null, items: unfamiliar });
  return groups;
}
