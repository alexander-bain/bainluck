import type { SourceRow } from "@/lib/calibrationSourceRows";

/**
 * One row of `/calibration`'s Source Comparison table.
 *
 * WHY THIS IS A COMPONENT AND NOT INLINE JSX (UX-P128).
 *
 * It was inline, and the defect it carried was a RENDER defect: `datagolf` —
 * 171 published outcomes, all of them `price_moved: false` and therefore all
 * outside the default cohort — arrived with `ece([]) === 0` and printed
 * **"0 outcomes · 0.0pp ECE"** in green, in first place, under a subhead
 * reading "sorted by ECE … Lower is better."
 *
 * `calibrationAuditHooks.test.tsx` states this page's testing convention and
 * its reason: the page is a 2,000-line client component behind SWR, so its
 * hooks are asserted at SOURCE level because *"rendering it would prove less
 * and break more."* That reasoning holds for the page and does not hold for
 * this: a defect in what a cell PRINTS is not provable by grepping the file it
 * was printed from. So the twelve lines that print it live here, where a test
 * can mount them and read the text a reader would read.
 *
 * The component is deliberately dumb. Every decision — is this row a
 * measurement, where does it sort, which numbers are real — was already made in
 * `lib/calibrationSourceRows.ts`. This only renders the verdict, which is what
 * makes a null here unrepresentable rather than merely discouraged: the
 * no-data branch is selected by `state`, and the numeric branch is the only
 * place a `toFixed` appears.
 */
export interface SourceComparisonRowProps {
  row: SourceRow;
  /** Reader-facing name for a single source key, for the multi-shape subtitle. */
  sourceLabel: (source: string) => string;
  /** The cohort toggle's own label, so the remedy names the real control. */
  toggleLabel: string;
}

export default function SourceComparisonRow({
  row,
  sourceLabel,
  toggleLabel,
}: SourceComparisonRowProps) {
  return (
    <tr
      className="border-t border-surface-border"
      data-testid="calibration-provider-row"
      data-provider={row.provider}
      data-provider-n={row.n}
      data-provider-sources={row.sources.join(",")}
      data-row-state={row.state}
    >
      <td className="py-2.5 pr-4 font-medium text-text-primary">
        {row.label}
        {row.sources.length > 1 && (
          <span className="block text-xs font-normal text-text-muted">
            {row.sources.map(sourceLabel).join(" · ")}
          </span>
        )}
      </td>
      {row.state === "no-cohort-data" ? (
        /* One cell across the four number columns. Four separate em-dashes
           would still scan as a row of values; one sentence scans as the
           absence it is, and it names the remedy rather than leaving the
           reader with a smaller mystery. */
        <td
          className="py-2.5 text-right text-xs text-text-muted"
          colSpan={4}
          data-testid="calibration-provider-no-data"
        >
          No outcomes in this cohort &mdash; not measured, not ranked. Use
          &ldquo;{toggleLabel}&rdquo; to include them.
        </td>
      ) : (
        <>
          <td className="py-2.5 pr-4 text-right tabular-nums">{row.n.toLocaleString()}</td>
          <td
            className={`py-2.5 pr-4 text-right tabular-nums font-semibold ${
              (row.ece as number) < 3
                ? "text-green-600"
                : (row.ece as number) < 5
                  ? "text-blue-600"
                  : "text-orange-600"
            }`}
          >
            {(row.ece as number).toFixed(1)}pp
          </td>
          <td className="py-2.5 pr-4 text-right tabular-nums text-text-muted">
            {(row.mce as number).toFixed(1)}pp
          </td>
          <td className="py-2.5 text-right tabular-nums">{(row.brier as number).toFixed(4)}</td>
        </>
      )}
    </tr>
  );
}
