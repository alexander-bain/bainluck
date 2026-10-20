"use client";

import PageHeader from "@/components/admin/PageHeader";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchSourceIntelligence, SourceIntelligenceData } from "@/lib/api";
import SourceIntelligenceView, { siPageStatus } from "@/app/admin/_views/SourceIntelligenceView";

export default function SourceIntelligencePage() {
  usePageTracking({ pageType: "source_intelligence", pageTitle: "Source Intelligence" });
  useScrollDepth({ pageType: "source_intelligence" });
  useEngagementTime({ pageType: "source_intelligence" });

  const { data, error, isLoading } = useSWR<SourceIntelligenceData>(
    "source-intelligence",
    fetchSourceIntelligence,
    { refreshInterval: 300_000, keepPreviousData: true }
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-text-muted text-sm">Loading analysis...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-text-muted text-sm">
          Unable to load source intelligence data.{" "}
          <button onClick={() => window.location.reload()} className="underline">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <SourceIntelligenceView
      data={data}
      header={
        <PageHeader
          question="Which probability source is most accurate?"
          status={siPageStatus(data)}
          summary="Brier scores and calibration curves across all sources"
          ideal="All sources measured. Best source identified per sport."
          subtitle="When sources disagree, who is right?"
        />
      }
      updated={
        <p className="mt-2 text-text-muted text-xs">
          Updated {new Date(data.generated_at).toLocaleDateString("en-US", {
            month: "long", day: "numeric", year: "numeric",
          })}
        </p>
      }
    />
  );
}
