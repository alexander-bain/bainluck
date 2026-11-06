"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import GapList from "@/components/evals/GapList";
import ReadingGuide from "@/components/evals/ReadingGuide";
import SourceList from "@/components/evals/SourceList";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  EVALS_PAGE_TITLE,
  GAPS_COPY,
  HERO_COPY,
  READING_COPY,
  SOURCES_COPY,
} from "@/lib/evals/copy";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { sourcesFor, type EvalsSectionId } from "@/lib/evals/sources";

/**
 * /evals — "How Bain Luck tests itself" (#12102).
 *
 * Built a section at a time from the plan on #11951 (Decide 43-A). A section
 * that has no data yet is absent, not empty: this step (S1) carries the hero,
 * the gaps, the reading guide and the sources, and each later step adds its own
 * section, its sources and its copy together.
 *
 * Truth rules, each enforced by a test under `lib/evals/__tests__/` and
 * `components/evals/__tests__/`: every number renders through `Figure` with a
 * truth kind, an as-of time and a source link; a PLANNED item renders no figure;
 * a verdict is read from its record, never recomputed; held-out results are
 * counts only.
 */

/** The sections on the page, in order. Sources list only what these read. */
const SECTIONS_ON_PAGE: readonly EvalsSectionId[] = ["gaps"];

const SECTION_TITLES: Record<EvalsSectionId, string> = {
  gaps: GAPS_COPY.title,
};

export default function EvalsPage() {
  // `page_type` is a closed union in lib/analytics/types.ts, outside this
  // page's files until S10 makes the page public; "about" is the nearest group
  // (an explanatory page), and every view still carries its own path.
  usePageTracking({ pageType: "about", pageTitle: EVALS_PAGE_TITLE });
  useScrollDepth({ pageType: "about" });
  useEngagementTime({ pageType: "about" });

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12" data-testid="evals-page">
      <header className="text-center space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">{EVALS_PAGE_TITLE}</h1>
        <p className="text-body text-text-primary max-w-2xl mx-auto">{HERO_COPY.lead}</p>
        <p className="text-caption text-text-secondary max-w-2xl mx-auto">{HERO_COPY.detail}</p>
      </header>

      <EvalsSection
        id="gaps"
        title={GAPS_COPY.title}
        lead={GAPS_COPY.lead}
        detail={GAPS_COPY.detail}
        truth={{ kind: "reviewed", asOf: GAPS_REVIEWED_AT }}
      >
        <GapList gaps={GAPS} />
      </EvalsSection>

      <EvalsSection
        id="how-to-read"
        title={READING_COPY.title}
        lead={READING_COPY.lead}
        detail={READING_COPY.detail}
      >
        <ReadingGuide />
      </EvalsSection>

      <EvalsSection
        id="sources"
        title={SOURCES_COPY.title}
        lead={SOURCES_COPY.lead}
        detail={SOURCES_COPY.detail}
      >
        <SourceList sources={sourcesFor(SECTIONS_ON_PAGE)} sectionTitles={SECTION_TITLES} />
      </EvalsSection>
    </div>
  );
}
