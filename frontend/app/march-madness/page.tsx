"use client";

import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { TOURNAMENT_TYPE_CONFIG, getCountdown, TOURNAMENT_DATES_2026 } from "@/lib/marchMadnessData";
import "./march-madness.css";

export default function MarchMadnessHub() {
  usePageTracking({ pageType: "march_madness", pageTitle: "March Madness" });
  useScrollDepth({ pageType: "march_madness" });
  useEngagementTime({ pageType: "march_madness" });

  const countdown = getCountdown(TOURNAMENT_DATES_2026.selection_sunday + "T23:00:00Z");

  return (
    <div className="mm-page">
      <div className="mm-content">
        <div className="mm-hub">
          <h1>March Madness 2026</h1>
          <p style={{ color: "var(--mm-text-dim)", fontSize: "1.1rem", maxWidth: 500, lineHeight: 1.5 }}>
            Championship futures, historical seed data, and live tournament tracking.
            Selection Sunday is March 15.
          </p>
          <div className="mm-countdown">
            Selection Sunday in <span className="mm-countdown-value">{countdown}</span>
          </div>
          <div className="mm-hub-cards">
            {Object.entries(TOURNAMENT_TYPE_CONFIG).map(([key, config]) => (
              <Link key={key} href={config.path} className="mm-hub-card">
                <span className="mm-hub-card-emoji">{config.emoji}</span>
                <span className="mm-hub-card-label">{config.label}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
