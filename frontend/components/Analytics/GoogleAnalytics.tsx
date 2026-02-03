'use client';

import Script from 'next/script';
import { useEffect } from 'react';
import { GA_CONFIG, initializeAnalytics, sendSessionEngagement } from '@/lib/analytics';

/**
 * Google Analytics Script Component
 *
 * Loads gtag.js asynchronously using Next.js Script component
 * with 'afterInteractive' strategy for optimal performance.
 *
 * This component should be placed in the root layout.
 */
export function GoogleAnalytics() {
  useEffect(() => {
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
  }, []);

  return (
    <>
      {/* Load gtag.js asynchronously */}
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_CONFIG.MEASUREMENT_ID}`}
        strategy="afterInteractive"
      />
      {/* Initialize dataLayer before gtag loads */}
      <Script
        id="gtag-init"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}

            // Set default consent - analytics enabled by default for US users
            // (GDPR regions would need consent banner interaction)
            gtag('consent', 'default', {
              'analytics_storage': 'granted',
              'ad_storage': 'denied',
              'ad_user_data': 'denied',
              'ad_personalization': 'denied'
            });
          `,
        }}
      />
    </>
  );
}

export default GoogleAnalytics;
