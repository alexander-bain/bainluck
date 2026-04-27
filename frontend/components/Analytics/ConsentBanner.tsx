'use client';

import { useState } from 'react';
import { useAnalyticsContext } from './AnalyticsProvider';

/**
 * GDPR/Privacy Consent Banner
 *
 * Displays a non-intrusive banner at the bottom of the screen
 * asking users for consent to track analytics.
 *
 * Supports three consent levels:
 * - All: Full tracking including ads (future-proofed)
 * - Analytics only: Just analytics, no ad tracking
 * - None: No tracking (still allows site to function)
 */
export function ConsentBanner() {
  const { showConsentBanner, setConsent, dismissBanner } = useAnalyticsContext();
  const [showDetails, setShowDetails] = useState(false);

  if (!showConsentBanner) {
    return null;
  }

  return (
    <div className="fixed bottom-16 md:bottom-0 left-0 right-0 z-[100] p-2 sm:p-4 animate-slide-up">
      <div className="max-w-4xl mx-auto bg-surface-card rounded-xl shadow-2xl border border-surface-border overflow-hidden">
        {/* Main Banner */}
        <div className="p-3 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-4">
            {/* Icon and Text */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1 sm:mb-2">
                <span className="text-base sm:text-xl">🍪</span>
                <h3 className="text-sm sm:text-base font-semibold text-text-primary">
                  We value your privacy
                </h3>
              </div>
              <p className="text-xs sm:text-sm text-text-secondary leading-relaxed hidden sm:block">
                We use cookies and similar technologies to understand how you use Bain Luck
                and improve your experience. You can choose which types of tracking to allow.
              </p>
              <button
                onClick={() => setShowDetails(!showDetails)}
                className="mt-1 sm:mt-2 text-xs sm:text-sm text-blue-600 hover:text-blue-700 underline underline-offset-2"
              >
                {showDetails ? 'Hide details' : 'Learn more'}
              </button>
            </div>

            {/* Buttons */}
            <div className="flex flex-row gap-2 sm:gap-3 flex-shrink-0">
              <button
                onClick={() => setConsent('none')}
                className="px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-text-secondary bg-slate/10 hover:bg-slate/20 rounded-lg transition-colors"
              >
                Decline
              </button>
              <button
                onClick={() => setConsent('analytics')}
                className="px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-text-primary bg-surface-border hover:bg-slate/20 rounded-lg transition-colors hidden sm:block"
              >
                Analytics only
              </button>
              <button
                onClick={() => setConsent('all')}
                className="px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-white bg-graphite hover:bg-ink rounded-lg transition-colors"
              >
                Accept
              </button>
            </div>
          </div>

          {/* Details Section */}
          {showDetails && (
            <div className="mt-4 pt-4 border-t border-surface-border">
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Essential */}
                <div className="p-3 bg-slate/5 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                    <span className="text-sm font-medium text-text-primary">Essential</span>
                    <span className="text-xs text-text-secondary">(Always on)</span>
                  </div>
                  <p className="text-xs text-text-secondary">
                    Required for the site to function. Includes your consent preferences
                    and basic functionality.
                  </p>
                </div>

                {/* Analytics */}
                <div className="p-3 bg-slate/5 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                    <span className="text-sm font-medium text-text-primary">Analytics</span>
                  </div>
                  <p className="text-xs text-text-secondary">
                    Helps us understand how you use the site so we can improve it.
                    We use Google Analytics with anonymized data.
                  </p>
                </div>

                {/* Marketing (future) */}
                <div className="p-3 bg-slate/5 rounded-lg opacity-50">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-purple-500/150"></span>
                    <span className="text-sm font-medium text-text-primary">Marketing</span>
                    <span className="text-xs text-text-secondary">(Not currently used)</span>
                  </div>
                  <p className="text-xs text-text-secondary">
                    Would be used for personalized content and ads.
                    We don&apos;t currently use marketing cookies.
                  </p>
                </div>

                {/* Cross-platform */}
                <div className="p-3 bg-slate/5 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                    <span className="text-sm font-medium text-text-primary">Cross-platform</span>
                  </div>
                  <p className="text-xs text-text-secondary">
                    If you log in, we connect your activity across web and mobile
                    to provide a seamless experience.
                  </p>
                </div>
              </div>

              <p className="mt-4 text-xs text-text-muted">
                You can change your preferences at any time. Your choice will be saved
                and remembered for future visits. For more information, see our{' '}
                <a href="/privacy" className="underline hover:text-text-secondary">
                  Privacy Policy
                </a>
                .
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Animation styles */}
      <style jsx>{`
        @keyframes slide-up {
          from {
            transform: translateY(100%);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        .animate-slide-up {
          animation: slide-up 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}

export default ConsentBanner;
