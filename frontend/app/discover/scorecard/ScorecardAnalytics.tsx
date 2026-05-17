"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

export function ScorecardAnalytics() {
  usePageTracking({ pageType: "scorecard", pageTitle: "Prediction Scorecard" });
  useScrollDepth({ pageType: "scorecard" });
  useEngagementTime({ pageType: "scorecard" });
  return null;
}
