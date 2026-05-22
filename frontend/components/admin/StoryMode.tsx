"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

export const STORY_CHAPTERS = [
  {
    chapter: 1,
    title: "Ingest",
    route: "/admin",
    narrative:
      "We pull from 6+ data sources every 30 seconds — sportsbooks, ESPN, Kalshi, Polymarket, StatPal, MLB Stats API. Each source has different coverage, latency, and cost characteristics.",
    why: "Without reliable ingestion from multiple sources, the probability aggregation that makes Bain Luck unique would have blind spots.",
  },
  {
    chapter: 2,
    title: "Match",
    route: "/admin/matching",
    narrative:
      'We semantically match markets across sources. The same question ("Will the Lakers win?") appears differently on each platform — different names, odds formats, and update cadences.',
    why: "Matching is the core technical challenge. Without it, users see duplicate or contradictory data instead of one unified view.",
  },
  {
    chapter: 3,
    title: "Classify",
    route: "/admin/taxonomy",
    narrative:
      "Every market gets classified by sport, category, tier, and signal type. Classification drives filtering, ranking, and display decisions downstream.",
    why: "Clean taxonomy means the right content reaches the right surface. Misclassification propagates errors into ranking.",
  },
  {
    chapter: 4,
    title: "Rank",
    route: "/admin/discover-quality",
    narrative:
      "We rank content using ground truth benchmarks, engagement feedback, and interestingness scoring — no vibes-based curation. Every ranking decision is traceable.",
    why: "Ranking is where product judgment meets data. The admin tools let us measure whether our taste matches reality.",
  },
  {
    chapter: 5,
    title: "Evaluate",
    route: "/admin/eval",
    narrative:
      "We close the loop with human-in-the-loop evaluation. Grid matching validates source merging. Card labeling calibrates interestingness. Pairwise comparison measures preference.",
    why: "Automated metrics catch regressions but can't judge taste. Human eval is the ground truth for what makes a market interesting.",
  },
  {
    chapter: 6,
    title: "Measure",
    route: "/admin/source-intelligence",
    narrative:
      "We measure source accuracy with Brier scores and calibration curves. We know which source is best for each sport, and we can prove it.",
    why: "If you can't measure accuracy, you can't improve it. Brier scores turn subjective trust into objective evidence.",
  },
  {
    chapter: 7,
    title: "Listen",
    route: "/admin/bug-reports",
    narrative:
      "Users shake their phone to report bugs. We auto-diagnose severity and root cause, then draft Claude Code prompts for fixes. The whole loop from bug report to fix is AI-assisted.",
    why: "Listening to users completes the feedback loop. AI-assisted triage means bugs get fixed in hours, not weeks.",
  },
];

export function useStoryMode() {
  const searchParams = useSearchParams();
  const storyParam = searchParams.get("story");
  return storyParam ? parseInt(storyParam, 10) : null;
}

export default function StoryBanner() {
  const pathname = usePathname();
  const router = useRouter();
  const activeChapter = useStoryMode();

  if (!activeChapter) return null;

  const chapter = STORY_CHAPTERS.find((c) => c.chapter === activeChapter);
  if (!chapter) return null;

  const prev = STORY_CHAPTERS.find((c) => c.chapter === activeChapter - 1);
  const next = STORY_CHAPTERS.find((c) => c.chapter === activeChapter + 1);

  const exitStory = () => {
    const params = new URLSearchParams(window.location.search);
    params.delete("story");
    const qs = params.toString();
    router.push(pathname + (qs ? `?${qs}` : ""));
  };

  const goTo = (ch: typeof STORY_CHAPTERS[0]) => {
    router.push(`${ch.route}?story=${ch.chapter}`);
  };

  return (
    <div className="bg-accent-brand/5 border border-accent-brand/20 rounded-xl p-4 mb-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex items-center justify-center w-8 h-8 rounded-full bg-accent-brand text-white text-sm font-bold shrink-0">
            {chapter.chapter}
          </span>
          <div>
            <div className="text-sm font-semibold text-text-primary">
              {chapter.title}
            </div>
            <p className="text-xs text-text-secondary mt-0.5 leading-relaxed max-w-2xl">
              {chapter.narrative}
            </p>
          </div>
        </div>
        <button onClick={exitStory} className="p-1 text-text-muted hover:text-text-secondary shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="flex gap-1 mt-3 mb-2">
        {STORY_CHAPTERS.map((ch) => (
          <div
            key={ch.chapter}
            className={`h-1 flex-1 rounded-full ${
              ch.chapter <= activeChapter ? "bg-accent-brand" : "bg-surface-border"
            }`}
          />
        ))}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-2">
        {prev ? (
          <button
            onClick={() => goTo(prev)}
            className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            {prev.title}
          </button>
        ) : (
          <span />
        )}
        <span className="text-[10px] text-text-muted">
          {activeChapter} of {STORY_CHAPTERS.length}
        </span>
        {next ? (
          <button
            onClick={() => goTo(next)}
            className="inline-flex items-center gap-1 text-xs text-accent-brand hover:underline"
          >
            {next.title}
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        ) : (
          <button
            onClick={exitStory}
            className="text-xs text-accent-brand hover:underline"
          >
            Finish walkthrough
          </button>
        )}
      </div>
    </div>
  );
}
