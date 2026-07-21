/**
 * CaseStudyCard — renders one case study in the L2-143 PUNCH TEMPLATE:
 *   headline (the paradox, numbers in it)
 *   → what the score said  → what the number knew (the cropped annotated chart)
 *   → the ≤2-line takeaway.
 * Shared between the public /about page and the /admin/story preview so the copy
 * has one source of truth. Pure presentational — no client hooks.
 */
import type { CaseStudy } from "@/lib/story-content";
import CaseStudyChart from "./CaseStudyChart";

export default function CaseStudyCard({ study }: { study: CaseStudy }) {
  return (
    <article className="bg-surface-card rounded-2xl p-6 sm:p-7 border border-surface-border shadow-card space-y-5">
      {/* kicker + headline (the paradox) */}
      <div className="space-y-2.5">
        <p className="text-micro tracking-wider text-accent-brand uppercase font-semibold">
          {study.kicker}
        </p>
        <h3 className="text-title-3 text-text-primary leading-snug">{study.headline}</h3>
      </div>

      {/* Beat 1 — what the score said */}
      <div className="flex gap-2.5">
        <span className="text-micro font-semibold text-text-muted uppercase tracking-wide shrink-0 w-24 pt-0.5">
          The score said
        </span>
        <p className="text-caption text-text-secondary leading-relaxed flex-1">
          {study.scoreSaid}
        </p>
      </div>

      {/* Beat 2 — what the number knew (the cropped annotated chart + the moment) */}
      <div className="bg-surface-deep rounded-xl p-4 sm:p-5 border border-surface-border space-y-3">
        <span className="text-micro font-semibold text-accent-brand uppercase tracking-wide">
          The number knew
        </span>
        <CaseStudyChart chart={study.chart} />
        <p className="text-caption text-text-secondary leading-relaxed">{study.moment}</p>
      </div>

      {/* Beat 3 — the takeaway */}
      <p className="text-body-strong text-text-primary leading-relaxed">{study.takeaway}</p>

      <p className="text-micro text-text-muted">{study.source}</p>
    </article>
  );
}
