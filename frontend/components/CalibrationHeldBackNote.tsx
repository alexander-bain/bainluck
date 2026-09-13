// CAL-P1136 / #5401 — ONE honest line for the groups we are not grading.
//
// klm = A (Alex, 2026-09-12): three source-and-category groups on the accuracy
// page are built on Kalshi opening prices that no order book ever stood behind
// (#4745's defect surviving in a shape its predicate could not see — a lone ask
// on an empty book recorded as a ~0.95 forecast). Until those prices are
// repaired and the groups recounted, they are not graded, not counted, and the
// reader is told so in a sentence.
//
// WHY A COMPONENT AND NOT INLINE JSX ON THE PAGE. The page is a client
// component built out of hooks; nothing in this repo can render it in the node
// test environment. A presentational leaf can be rendered with the real props
// and asserted, which is the difference between a claim about this line and a
// claim about the payload that feeds it.
//
// WHAT IT DELIBERATELY DOES NOT SAY (notice 34 / D102): no coverage count, no
// method note, no paragraph explaining the emptiness. The reader gets the group
// names and one clause of why. The counts a probe needs ride as data
// attributes, which is where the same notice puts them.

import React from "react";

export interface HeldBackCell {
  cell: string;
  source: string;
  category: string;
  n: number;
}

export interface CalibrationHeldBackNoteProps {
  cells: HeldBackCell[] | null | undefined;
  /** Payload-driven source vocabulary (CAL-P1025); house style wins. */
  sourceLabel: (source: string) => string;
  /** Reader-facing category name. */
  categoryLabel: (category: string) => string;
}

/** Joins names as prose: "A", "A and B", "A, B and C". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export default function CalibrationHeldBackNote({
  cells,
  sourceLabel,
  categoryLabel,
}: CalibrationHeldBackNoteProps) {
  // Absent and empty both render NOTHING — and they mean different things
  // upstream (`null` = an unscored board, `[]` = nothing held back), which is
  // why the payload keeps them distinct even though the page treats them the
  // same. The day #5401 lands this section disappears on its own.
  if (!cells || cells.length === 0) return null;

  const names = cells.map(
    c => `${sourceLabel(c.source)} ${categoryLabel(c.category)}`
  );

  return (
    <section
      className="bg-surface-card rounded-xl p-5 border border-surface-border"
      data-testid="calibration-held-back-note"
      data-held-back-count={cells.length}
      data-held-back-cells={cells.map(c => c.cell).join(",")}
      data-held-back-outcomes={cells.reduce((s, c) => s + (c.n || 0), 0)}
    >
      <p className="text-sm text-text-secondary">
        <strong className="text-text-primary">{joinNames(names)}</strong>{" "}
        {cells.length === 1 ? "is" : "are"} held back while we repair prices we
        should never have stored. Those groups aren&rsquo;t graded or counted
        here until the repair lands.
      </p>
    </section>
  );
}
