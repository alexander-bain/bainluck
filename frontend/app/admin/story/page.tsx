"use client";

import Link from "next/link";
import {
  Activity,
  Database,
  BarChart3,
  FlaskConical,
  MessageSquare,
  Tags,
  Target,
  ArrowRight,
} from "lucide-react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { STORY_CHAPTERS } from "@/components/admin/StoryMode";
import {
  STORY_ONE_LINER,
  STORY_ANTI_THESIS,
  STORY_BLEND,
  STORY_THESIS,
  STORY_HUMAN_LINE,
  CASE_STUDIES,
} from "@/lib/story-content";
import CaseStudyCard from "@/components/story/CaseStudyCard";

const CHAPTER_ICONS = [Activity, Database, Tags, BarChart3, FlaskConical, Target, MessageSquare];

export default function StoryIndexPage() {
  usePageTracking({ pageType: "admin_story", pageTitle: "Admin: Pipeline Walkthrough" });
  useScrollDepth({ pageType: "admin_story" });
  useEngagementTime({ pageType: "admin_story" });

  return (
    <div className="max-w-4xl">
      {/* ── The public story (shared source of truth with /about) ── */}
      <section className="mb-10">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h1 className="text-xl font-bold text-text-primary">The public story</h1>
          <Link
            href="/about"
            className="text-xs font-medium text-accent-brand hover:underline shrink-0"
          >
            View /about →
          </Link>
        </div>
        <p className="text-xs text-text-muted mb-4">
          This is the exact narrative shown on the public About page — same source module
          (<code className="text-text-secondary">lib/story-content.ts</code>), so edits here and
          there can never drift.
        </p>

        <div className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-4">
          <p className="text-sm text-text-primary leading-relaxed">{STORY_ONE_LINER}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="bg-surface-deep rounded-lg p-3 border border-surface-border">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1">
                Anti-thesis
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                {STORY_ANTI_THESIS.heading}
              </p>
            </div>
            <div className="bg-surface-deep rounded-lg p-3 border border-surface-border">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1">
                The blend
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{STORY_BLEND.heading}</p>
            </div>
            <div className="bg-surface-deep rounded-lg p-3 border border-surface-border">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1">
                Who builds it
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{STORY_HUMAN_LINE}</p>
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-2">
              {STORY_THESIS.heading}
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {CASE_STUDIES.map((study) => (
                <CaseStudyCard key={study.id} study={study} />
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="mb-8">
        <h2 className="text-xl font-bold text-text-primary">
          How Bain Luck Works
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          A 7-stage pipeline from raw data to user experience. Click any stage to explore its admin dashboard.
        </p>
      </div>

      <div className="space-y-3">
        {STORY_CHAPTERS.map((ch, i) => {
          const Icon = CHAPTER_ICONS[i] || Activity;
          const isLast = i === STORY_CHAPTERS.length - 1;

          return (
            <div key={ch.chapter}>
              <Link
                href={`${ch.route}?story=${ch.chapter}`}
                className="flex items-start gap-4 bg-surface-card border border-surface-border rounded-xl p-5 hover:border-accent-brand/40 hover:shadow-sm transition-all group"
              >
                <div className="flex items-center justify-center w-10 h-10 rounded-full bg-accent-brand/10 text-accent-brand shrink-0 group-hover:bg-accent-brand group-hover:text-white transition-colors">
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-text-muted">
                      Stage {ch.chapter}
                    </span>
                    <span className="text-sm font-semibold text-text-primary">
                      {ch.title}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed">
                    {ch.narrative}
                  </p>
                  <p className="text-[11px] text-text-muted mt-2 italic">
                    Why: {ch.why}
                  </p>
                </div>
                <ArrowRight className="w-4 h-4 text-text-muted group-hover:text-accent-brand shrink-0 mt-1 transition-colors" />
              </Link>

              {!isLast && (
                <div className="flex justify-center py-1">
                  <div className="w-px h-4 bg-surface-border" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-8 flex justify-center">
        <Link
          href="/admin?story=1"
          className="inline-flex items-center gap-2 rounded-xl bg-accent-brand px-6 py-3 text-sm font-medium text-white hover:bg-accent-brand/90 transition-colors"
        >
          Start Walkthrough
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}
