"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import ForwardRecordSection from "@/components/evals/ForwardRecordSection";
import GapList from "@/components/evals/GapList";
import HeroTiles from "@/components/evals/HeroTiles";
import ReadingGuide from "@/components/evals/ReadingGuide";
import RunTimeline from "@/components/evals/RunTimeline";
import SourceList from "@/components/evals/SourceList";
import { useForwardRecord } from "@/components/evals/useForwardRecord";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  EVALS_PAGE_TITLE,
  FORWARD_COPY,
  GAPS_COPY,
  HERO_COPY,
  READING_COPY,
  SOURCES_COPY,
  TIMELINE_COPY,
} from "@/lib/evals/copy";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { loadRuns } from "@/lib/evals/runs";
import { sourcesFor, type EvalsSectionId } from "@/lib/evals/sources";

/**
 * /evals — "How Bain Luck tests itself" (#12102).
 *
 * Built a section at a time from the plan on #11951 (Decide 43-A). A section
 * that has no data yet is absent, not empty. S1 carried the hero, the gaps, the
 * reading guide and the sources; S3 adds the exams on the record, the live
 * forward record and its hero tile. Each later step adds its own section, its
 * sources and its copy together.
 *
 * Truth rules, each enforced by a test under `lib/evals/__tests__/` and
 * `components/evals/__tests__/`: every number renders through `Figure` with a
 * truth kind, an as-of time and a source link; a PLANNED item renders no figure;
 * a verdict is read from its record, never recomputed; held-out results are
 * counts only.
 */

/** The sections on the page, in order. Sources list only what these read. */
const SECTIONS_ON_PAGE: readonly EvalsSectionId[] = ["timeline", "forward-record", "gaps"];

const SECTION_TITLES: Record<EvalsSectionId, string> = {
  timeline: TIMELINE_COPY.title,
  "forward-record": FORWARD_COPY.title,
  gaps: GAPS_COPY.title,
};

const RUNS = loadRuns();

export default function EvalsPage() {
  // Its own page type (Fable, 42-A, on PR #12114), so /evals views, scroll
  // depth and engagement never count toward /about's.
  usePageTracking({ pageType: "evals", pageTitle: EVALS_PAGE_TITLE });
  useScrollDepth({ pageType: "evals" });
  useEngagementTime({ pageType: "evals" });
  const forward = useForwardRecord();

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12" data-testid="evals-page">
      <header className="text-center space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">{EVALS_PAGE_TITLE}</h1>
        <p className="text-body text-text-primary max-w-2xl mx-auto">{HERO_COPY.lead}</p>
        <p className="text-caption text-text-secondary max-w-2xl mx-auto">{HERO_COPY.detail}</p>
        <HeroTiles forward={forward} />
      </header>

      <EvalsSection
        id="timeline"
        title={TIMELINE_COPY.title}
        lead={TIMELINE_COPY.lead}
        detail={TIMELINE_COPY.detail}
      >
        <RunTimeline runs={RUNS} />
      </EvalsSection>

      <ForwardRecordSection state={forward} />

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
