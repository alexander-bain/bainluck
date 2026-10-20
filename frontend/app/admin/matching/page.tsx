"use client";

import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import PageHeader from "@/components/admin/PageHeader";
import {
  MaturedLinkageCard,
  PredictionMarketDiagnosticSection,
  SourceContributionSection,
  SportCoverageSections,
  tier1Summary,
  type AccuracyData,
  type LinkRateData,
  type MaturedLinkageData,
} from "@/app/admin/_views/MatchingView";

export default function MatchingPage() {
  usePageTracking({ pageType: "admin_matching", pageTitle: "Admin: Data Quality — Matching" });
  useScrollDepth({ pageType: "admin_matching" });
  useEngagementTime({ pageType: "admin_matching" });

  const { secret } = useAdminAuth();

  const { data: accuracy, isLoading } = useSWR<AccuracyData>(
    ["schedule-accuracy", secret],
    () =>
      adminFetch("/api/admin/schedule/accuracy?days=14", secret)
        .then((r) => r.ok ? r.json() : null),
    { refreshInterval: 300000 }
  );

  // L2-128 Item 2a: prediction-market linkage (game markets → events). Served
  // from the L2-90 warm cache; a cold read falls back to inline compute.
  const { data: linkRate, isLoading: linkRateLoading } = useSWR<LinkRateData>(
    ["prediction-market-link-rate", secret],
    () =>
      adminFetch("/api/admin/prediction-markets/link-rate", secret)
        .then((r) => r.ok ? r.json() : null),
    { refreshInterval: 300000 }
  );

  // Queue #220/221 Item 2 — the matured-linkage headline metric.
  const { data: maturedLinkage } = useSWR<MaturedLinkageData>(
    ["prediction-market-matured-linkage", secret],
    () =>
      adminFetch("/api/admin/prediction-markets/matured-linkage", secret)
        .then((r) => (r.ok ? r.json() : null)),
    { refreshInterval: 300000 }
  );

  const tier1 = tier1Summary(accuracy);

  return (
    <div className="max-w-4xl space-y-6">
      <PageHeader
        question="Are events properly linked across data sources?"
        status={isLoading ? "loading" : tier1.status}
        summary={
          isLoading
            ? "Loading..."
            : `${tier1.linked}/${tier1.total} Tier 1 events have Odds API data (${tier1.pct}%)`
        }
        ideal="Every Tier 1 event should have Odds API, ESPN, and StatPal data."
        subtitle="Source linkage determines whether event pages show sportsbook odds, charts, and cross-source comparison."
      />

      {/* Queue #220/221 Item 2 — MATURED LINKAGE: the headline number that means
          something. Below-100 = a real phantom blend source. */}
      {maturedLinkage && <MaturedLinkageCard data={maturedLinkage} />}

      <SportCoverageSections accuracy={accuracy} loading={isLoading} />

      <PredictionMarketDiagnosticSection linkRate={linkRate} loading={linkRateLoading} />

      <SourceContributionSection />
    </div>
  );
}
