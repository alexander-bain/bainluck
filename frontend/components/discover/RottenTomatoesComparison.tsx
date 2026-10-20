import Link from "next/link";
import type { RottenTomatoesComparison as Comparison } from "@/lib/discover/rottenTomatoesComparison";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import { feedItemHref, resolvesLabel } from "./utils";

/** #723 / #10357: the already-grouped films share visible threshold columns.
 * Rows remain independent forecasts, not probabilities of beating other films.
 */
export function RottenTomatoesComparison({ comparison }: { comparison: Comparison }) {
  return (
    <div className="overflow-x-auto border-t border-surface-border">
      <table className="w-full text-sm">
        <caption className="text-left px-4 pt-3 pb-2 text-xs text-text-secondary">
          Forecasts for each score threshold. Open a film for its full question and score range.
        </caption>
        <thead>
          <tr className="text-xs text-text-secondary">
            <th scope="col" className="text-left px-4 py-2 font-medium">Film</th>
            {comparison.columns.map(column => (
              <th key={column.label} scope="col" className="px-2 py-2 font-medium whitespace-nowrap">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {comparison.rows.map(({ item, data, points }) => (
            <tr key={data.id}>
              <th scope="row" className="px-4 py-3 text-left font-medium min-w-[8rem]">
                <Link href={feedItemHref(item)!} className="text-text-primary hover:text-accent-brand focus-visible:underline">
                  {data.name}
                </Link>
                <span className="block text-xs text-text-secondary font-normal">{resolvesLabel(data.resolution_date)}</span>
                <PriceAgeMark observedAt={data.price_observed_at} cadence="futures" />
              </th>
              {points.map(point => (
                <td key={point.label} className="px-2 py-3 text-center tabular-nums text-text-primary">
                  {formatProbabilityPercent(point.probability)}
                  <div aria-hidden="true" className="mt-1 h-1 rounded-full bg-surface-hover">
                    <div className="h-1 rounded-full bg-accent-brand" style={{ width: `${point.probability * 100}%` }} />
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
