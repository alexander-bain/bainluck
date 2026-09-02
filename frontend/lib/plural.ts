// UX-P265 (#2645) — the ONE place a count picks its noun.
//
// The shopper found `/sports` Top Markets printing "1 sources" and
// "+1 more outcomes" on a single card. The pattern already existed in the repo
// as a local const inside `lib/calibrationPopulation.ts` — unexported, so every
// other surface either re-derived it or, as here, skipped it. This is that
// const lifted out, unchanged in behaviour, so the next surface has something
// to import instead of a fourth hand-rolled ternary.
//
// Deliberately dumb: English count agreement only, caller supplies both forms.
// No `-s` suffixing rule, because "outcomes"/"outcome" and "sources"/"source"
// are cheap to write and an inferred plural is wrong the first time someone
// counts a "category" or a "match".

/** `1 -> one`, everything else -> `many`. Negative and zero take `many`. */
export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** `plural` with the number already attached: `countOf(1, "outcome", "outcomes")` -> `"1 outcome"`. */
export function countOf(n: number, one: string, many: string): string {
  return `${n} ${plural(n, one, many)}`;
}
