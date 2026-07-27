'use client';

import Script from 'next/script';
import { useEffect } from 'react';
import {
  GA_CONFIG,
  initializeAnalytics,
  isAnalyticsConfigured,
  sendSessionEngagement,
} from '@/lib/analytics';

/**
 * Google Analytics Script Component
 *
 * Loads gtag.js asynchronously using Next.js Script component
 * with 'afterInteractive' strategy for optimal performance.
 *
 * This component should be placed in the root layout.
 */
export function GoogleAnalytics() {
  const configured = isAnalyticsConfigured();

  useEffect(() => {
    if (!configured) return;
    // Initialize analytics after gtag script loads
    initializeAnalytics();

    // Send session engagement on page unload
    const handleUnload = () => {
      sendSessionEngagement();
    };

    // Use visibilitychange for better mobile support
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        sendSessionEngagement();
      }
    };

    window.addEventListener('beforeunload', handleUnload);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', handleUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [configured]);

  // No measurement id configured → don't load gtag.js or emit anything.
  if (!configured) {
    return null;
  }

  return (
    <>
      {/* Load gtag.js asynchronously */}
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_CONFIG.MEASUREMENT_ID}`}
        strategy="afterInteractive"
      />
      {/* Initialize dataLayer + set consent BEFORE gtag processes anything.
          Denied by default (Consent Mode v2); a stored analytics grant is
          applied as an explicit update, so nothing is stored pre-consent and
          the choice deterministically precedes any configuration/event. */}
      <Script
        id="gtag-init"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}

            // Denied by default until an explicit choice. No ads product, so
            // every ads state stays denied even after a grant.
            gtag('consent', 'default', {
              'analytics_storage': 'denied',
              'ad_storage': 'denied',
              'ad_user_data': 'denied',
              'ad_personalization': 'denied'
            });

            // Apply a previously-stored analytics grant deterministically,
            // before gtag.js config runs.
            try {
              var c = localStorage.getItem('${GA_CONFIG.CONSENT_STORAGE_KEY}');
              if (c === 'all' || c === 'analytics') {
                gtag('consent', 'update', {
                  'analytics_storage': 'granted',
                  'ad_storage': 'denied',
                  'ad_user_data': 'denied',
                  'ad_personalization': 'denied'
                });
              }
            } catch (e) { /* localStorage unavailable */ }
          `,
        }}
      />
    </>
  );
}

export default GoogleAnalytics;
