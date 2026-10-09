"use client";

import { useId, type ReactNode } from "react";

/**
 * #5105 (thin supply) — the opening cards, then the ordinary-live continuation
 * under its own heading. Not mounted anywhere yet.
 *
 * The caller passes each section ALREADY processed on its own (see
 * `lib/discover/continuationSections`: partition by server position first,
 * then group / space / personalize each section separately) and renders the
 * cards itself through `renderSection`, so click targets and card content are
 * exactly the existing cards. This component only orders the two lists and
 * labels the second one. It never writes a pseudo-card, a total, or a blank
 * opening: no continuation card means no heading; no opening card means the
 * heading leads.
 */
export interface ContinuationSectionsProps<T> {
  opening: readonly T[];
  continuation: readonly T[];
  renderSection: (items: readonly T[], section: "opening" | "continuation") => ReactNode;
  heading?: string;
}

export const CONTINUATION_HEADING = "Live events";

export default function ContinuationSections<T>({
  opening,
  continuation,
  renderSection,
  heading = CONTINUATION_HEADING,
}: ContinuationSectionsProps<T>) {
  const headingId = useId();
  return (
    <>
      {opening.length > 0 && renderSection(opening, "opening")}
      {continuation.length > 0 && (
        <section aria-labelledby={headingId} data-discover-section="continuation">
          <h2 id={headingId} className="mb-3 mt-6 text-lg font-black tracking-tight text-text-primary">
            {heading}
          </h2>
          {renderSection(continuation, "continuation")}
        </section>
      )}
    </>
  );
}
