"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";

const DISMISSED_KEY = "bainluck_onboarding_dismissed";

/**
 * Shows a CTA banner for authenticated users who haven't completed onboarding.
 * Dismissable — stores the dismissal in localStorage so it doesn't reappear.
 *
 * Uses the feed response's personalization metadata to determine if the user
 * has set up their preferences (0 teams = hasn't onboarded).
 */
export default function OnboardingBanner({
  teamCount,
}: {
  teamCount?: number;
}) {
  const { isAuthenticated, isLoading } = useAuthContext();
  const [dismissed, setDismissed] = useState(true); // Default hidden

  // Check localStorage for dismissal on mount
  useEffect(() => {
    const wasDismissed = localStorage.getItem(DISMISSED_KEY);
    setDismissed(!!wasDismissed);
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
  };

  // Don't show if: loading, not authenticated, dismissed, or already has teams
  if (isLoading || !isAuthenticated || dismissed || (teamCount && teamCount > 0)) {
    return null;
  }

  return (
    <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-100 rounded-xl p-4 mb-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="text-xl mt-0.5">⭐</span>
          <div>
            <p className="text-sm font-semibold text-graphite">
              Personalize your feed
            </p>
            <p className="text-xs text-slate mt-0.5">
              Tell us your teams and sports to see what matters most to you.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            href="/onboarding"
            className="px-3 py-1.5 bg-graphite text-white rounded-lg text-xs font-medium hover:bg-graphite/90 transition-colors"
          >
            Get Started
          </Link>
          <button
            onClick={handleDismiss}
            className="text-slate hover:text-graphite p-1 transition-colors"
            title="Dismiss"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
