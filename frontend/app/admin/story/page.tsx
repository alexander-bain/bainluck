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

const CHAPTER_ICONS = [Activity, Database, Tags, BarChart3, FlaskConical, Target, MessageSquare];

export default function StoryIndexPage() {
  usePageTracking({ pageType: "admin_story", pageTitle: "Admin: Pipeline Walkthrough" });
  useScrollDepth({ pageType: "admin_story" });
  useEngagementTime({ pageType: "admin_story" });

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <h1 className="text-xl font-bold text-text-primary">
          How Bain Luck Works
        </h1>
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
