import type { ReactNode } from "react";

import TruthChip from "@/components/evals/TruthChip";
import type { Truth } from "@/lib/evals/truth";

/**
 * One /evals section, in `/calibration`'s card: a title, the section's truth
 * chip, a line a 13-year-old can follow (`lead`) and one for a reader who
 * evaluates systems for a living (`detail`).
 *
 * `data-truth-scope` names the label every figure inside the card is under; the
 * page test fails a figure whose nearest scope says something different.
 */
export default function EvalsSection({
  id,
  title,
  lead,
  detail,
  truth,
  children,
}: {
  id: string;
  title: string;
  lead: string;
  detail?: string;
  truth?: Truth;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      data-evals-section={id}
      data-truth-scope={truth?.kind}
      className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`${id}-title`} className="text-title-3 text-text-primary">
          {title}
        </h2>
        {truth && <TruthChip truth={truth} />}
      </div>
      <p className="mt-2 text-body text-text-primary">{lead}</p>
      {detail && <p className="mt-1 text-caption text-text-secondary">{detail}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}
