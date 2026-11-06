"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import ExamSection from "@/components/evals/ExamSection";
import ForwardRecordSection from "@/components/evals/ForwardRecordSection";
import GapList from "@/components/evals/GapList";
import ReadingGuide from "@/components/evals/ReadingGuide";
import RelationReportCard from "@/components/evals/RelationReportCard";
import RunTimeline from "@/components/evals/RunTimeline";
import SourceList from "@/components/evals/SourceList";
import TestLibrary from "@/components/evals/TestLibrary";
import TestsForTheTests, { BiteMeter } from "@/components/evals/TestsForTheTests";
import TopScreen from "@/components/evals/TopScreen";
import { BreakagesPicture, ChecksPicture, ExamPicture, KindsPicture, ReviewerPicture, Topic } from "@/components/evals/Topics";
import Watchers from "@/components/evals/Watchers";
import { useForwardRecord } from "@/components/evals/useForwardRecord";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  CONFUSION_COPY,
  EVALS_PAGE_TITLE,
  EXAM_COPY,
  FORWARD_COPY,
  GAPS_COPY,
  HERO_COPY,
  LIBRARY_COPY,
  READING_COPY,
  SOURCES_COPY,
  TESTS_FOR_TESTS_COPY,
  TIMELINE_COPY,
  TOPIC_COPY,
  WATCHERS_COPY,
} from "@/lib/evals/copy";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { loadReviewerResults } from "@/lib/evals/reviewerResults";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { loadRuns } from "@/lib/evals/runs";
import { loadScoreboard } from "@/lib/evals/scoreboard";
import { loadExam } from "@/lib/evals/twinExam";
import { loadWatchers } from "@/lib/evals/watchers";
import { sourcesFor, type EvalsSectionId } from "@/lib/evals/sources";

/**
 * /evals — "How Bain Luck tests itself" (#12102).
 *
 * Built a section at a time from the plan on #11951 (Decide 43-A). A section
 * that has no data yet is absent, not empty. S1 carried the hero, the gaps, the
 * reading guide and the sources; S3 the exams on the record, the live forward
 * record and its hero tile; S4 the test library, the tests for the tests and
 * their hero tile; S5 the checks that run on their own; S2 the twin exam's
 * gates, its report card and its hero tile, from Builder B's scorer record.
 *
 * Since Alex's Nov 6 goal the page opens with the top screen — one plain
 * answer and three pictures for a reader with no AI background — and then one
 * topic per question: a plain paragraph, a picture, and the sections above
 * under that topic's own "Show the details" fold. The gaps stay open. No word
 * that needs the glossary appears outside a fold, and the folds use plain
 * words too: the glossary maps the technical names to them
 * (`topScreen.test.tsx`).
 *
 * Truth rules, each enforced by a test under `lib/evals/__tests__/` and
 * `components/evals/__tests__/`: every number renders through `Figure` with a
 * truth kind, an as-of time and a source link; a PLANNED item renders no figure;
 * a verdict is read from its record, never recomputed; held-out results are
 * counts only.
 */

/** The sections on the page, in order. Sources list only what these read. */
const EXAM = loadExam();
const RUNS = loadRuns();
const SCOREBOARD = loadScoreboard();
const REVIEWER_STUDY = loadReviewerStudy();
const WATCHERS = loadWatchers();
const REVIEWER_RESULTS = loadReviewerResults(REVIEWER_STUDY);

const SECTIONS_ON_PAGE: readonly EvalsSectionId[] = [
  "forward-record",
  ...(EXAM ? (["exam", "confusion"] as const) : []),
  "timeline",
  ...(REVIEWER_STUDY ? (["tests-for-tests"] as const) : []),
  ...(SCOREBOARD ? (["test-library"] as const) : []),
  ...(WATCHERS ? (["watchers"] as const) : []),
  "gaps",
];

const SECTION_TITLES: Record<EvalsSectionId, string> = {
  exam: EXAM_COPY.title,
  confusion: CONFUSION_COPY.title,
  timeline: TIMELINE_COPY.title,
  "forward-record": FORWARD_COPY.title,
  "test-library": LIBRARY_COPY.title,
  "tests-for-tests": TESTS_FOR_TESTS_COPY.title,
  watchers: WATCHERS_COPY.title,
  gaps: GAPS_COPY.title,
};

export default function EvalsPage() {
  // Its own page type (Fable, 42-A, on PR #12114), so /evals views, scroll
  // depth and engagement never count toward /about's.
  usePageTracking({ pageType: "evals", pageTitle: EVALS_PAGE_TITLE });
  useScrollDepth({ pageType: "evals" });
  useEngagementTime({ pageType: "evals" });
  const forward = useForwardRecord();

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12" data-testid="evals-page">
      <TopScreen forward={forward} study={REVIEWER_STUDY} results={REVIEWER_RESULTS} watchers={WATCHERS} />

      {/* One topic per question the top screen asks, then the gaps: each opens
          in plain words with a picture, and everything the page carried before
          sits under that topic's "Show the details" fold, unchanged (Alex, Nov 6). */}
      <Topic
        id="probabilities"
        title={TOPIC_COPY.probabilities.title}
        why={TOPIC_COPY.probabilities.why}
        picture={<KindsPicture state={forward} />}
      >
        <ForwardRecordSection state={forward} />
      </Topic>

      <Topic
        id="matching"
        title={TOPIC_COPY.matching.title}
        why={TOPIC_COPY.matching.why}
        picture={EXAM && <ExamPicture exam={EXAM} />}
      >
        {EXAM && <ExamSection exam={EXAM} />}
        {EXAM && <RelationReportCard exam={EXAM} />}
        <EvalsSection
          id="timeline"
          title={TIMELINE_COPY.title}
          lead={TIMELINE_COPY.lead}
          detail={TIMELINE_COPY.detail}
        >
          <RunTimeline runs={RUNS} />
        </EvalsSection>
      </Topic>

      {REVIEWER_STUDY && (
        <Topic
          id="reviewer"
          title={TOPIC_COPY.reviewer.title}
          why={TOPIC_COPY.reviewer.why}
          picture={REVIEWER_RESULTS && <ReviewerPicture results={REVIEWER_RESULTS} study={REVIEWER_STUDY} />}
        >
          <TestsForTheTests board={null} study={REVIEWER_STUDY} />
        </Topic>
      )}

      {SCOREBOARD && (
        <Topic
          id="tests"
          title={TOPIC_COPY.tests.title}
          why={TOPIC_COPY.tests.why}
          picture={<BreakagesPicture board={SCOREBOARD} />}
        >
          <TestLibrary board={SCOREBOARD}>
            <BiteMeter board={SCOREBOARD} />
          </TestLibrary>
        </Topic>
      )}

      {WATCHERS && (
        <Topic
          id="checks"
          title={TOPIC_COPY.checks.title}
          why={TOPIC_COPY.checks.why}
          picture={<ChecksPicture list={WATCHERS} />}
        >
          <Watchers list={WATCHERS} />
        </Topic>
      )}

      <EvalsSection
        id="gaps"
        title={GAPS_COPY.title}
        lead={GAPS_COPY.lead}
        detail={GAPS_COPY.detail}
        truth={{ kind: "reviewed", asOf: GAPS_REVIEWED_AT }}
      >
        <GapList gaps={GAPS} />
      </EvalsSection>

      <Topic id="more" title={TOPIC_COPY.more.title} why={TOPIC_COPY.more.why}>
        <div className="space-y-2 text-body text-text-primary" data-testid="evals-about">
          <p>{HERO_COPY.lead}</p>
          <p className="text-caption text-text-secondary">{HERO_COPY.detail}</p>
        </div>
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
      </Topic>
    </div>
  );
}
