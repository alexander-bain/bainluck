"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";

const DISMISSED_KEY = "bainluck_onboarding_dismissed";

export default function OnboardingBanner({
  teamCount,
}: {
  teamCount?: number;
}) {
  const { isAuthenticated, isLoading } = useAuthContext();
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    const wasDismissed = localStorage.getItem(DISMISSED_KEY);
    setDismissed(!!wasDismissed);
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
  };

  if (isLoading || !isAuthenticated || dismissed || (teamCount && teamCount > 0)) {
    return null;
  }

  return (
    <div className="bg-surface-card border border-accent-brand/20 rounded-card p-4" role="banner" aria-label="Personalize your feed">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="text-lg mt-0.5">⭐</span>
          <div>
            <p className="text-sm font-semibold text-text-primary">
              Personalize your feed
            </p>
            <p className="text-xs text-text-secondary mt-0.5">
              Tell us your teams and sports to see what matters most to you.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            href="/onboarding"
            className="px-3 py-1.5 bg-accent-brand text-text-inverse rounded-lg text-xs font-medium hover:bg-accent-brand/90 transition-colors"
          >
            Get Started
          </Link>
          <button
            onClick={handleDismiss}
            className="text-text-muted hover:text-text-secondary p-1 transition-colors"
            title="Dismiss"
            aria-label="Dismiss onboarding banner"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
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
