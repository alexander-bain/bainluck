/**
 * A card's method note, one tap away instead of in front of the number.
 *
 * STANDING NOTICE 34 (Alex, 2026-09-08, on the US Open page): *"all the grey
 * text is madness, and shouldn't be user-facing at all"* — coverage counts,
 * limitations and method notes go *"in the PR, the artifact, or a tooltip on
 * the source mark — never in the page body… A reader sees the number, the
 * small source mark (D91), and at most one short caption."*
 *
 * `/calibration` had eight of these blocks when the notice landed (#4118, two
 * censuses by calibration/1062 plus one found on calibration/1063's LOOK), and
 * six of them were four-to-six lines of grey standing between a heading and the
 * table it described.
 *
 * WHY THIS MOVES THE PROSE INSTEAD OF DELETING IT. Half of those paragraphs
 * exist because Alex asked for them in an earlier session — UX-P075 item (a)
 * (2026-08-14) made the cohort's proxy footnote non-optional, and the Queue-316
 * comms pass describes its hooks as *"a claim Alex asked to be made in words"*
 * (`__tests__/components/calibrationAuditHooks.test.tsx`). A build lane does not
 * overwrite four dated specific instructions with one later general one. Notice
 * 34 offers the reconciliation itself: the objection is to prose **in the page
 * body**, and it names disclosure as a destination. So the sentence survives
 * verbatim, in its own card, behind one grey line — and the reader gets the
 * number first.
 *
 * This is the page's own idiom, not a new one: `page.tsx` already folds "Show
 * the math" and "Technical: data corrections log" exactly this way.
 *
 * CLOSED BY DEFAULT AND IN THE DOM. `<details>` keeps its content in the
 * accessibility tree and in `textContent`, so every audit hook, rail and
 * screen-reader path that could read the paragraph before can still read it.
 * Nothing became unreachable; it stopped being unavoidable.
 */
export function CalibrationCardNote({
  label = "How to read this",
  className = "",
  children,
}: {
  /** The summary line. Name the card's subject when "how to read this" is vague. */
  label?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <details className={`group mb-4 ${className}`.trim()} data-testid="calibration-card-note">
      <summary className="cursor-pointer list-none select-none text-xs text-text-muted hover:text-text-secondary">
        {label}{" "}
        <span
          aria-hidden="true"
          className="inline-block transition-transform group-open:rotate-180"
        >
          &#9662;
        </span>
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}
