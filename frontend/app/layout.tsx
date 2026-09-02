import type { Metadata } from "next";
import Link from "next/link";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AnalyticsProvider, ConsentBanner, TelemetryGate } from "@/components/Analytics";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { AuthProvider } from "@/components/AuthProvider";
import PinSyncEffect from "@/components/PinSyncEffect";
import UserMenu from "@/components/UserMenu";
import SWRProvider from "@/components/SWRProvider";
import BottomNav from "@/components/BottomNav";
import DesktopNav from "@/components/DesktopNav";
import Footer from "@/components/Footer";
import { BUILD_META_NAME, frontendCommitSha } from "@/lib/buildInfo";
import { Suspense } from "react";
// LAT-P200: these three were `dynamic(..., { ssr: false })` right here, and
// because this file is a Server Component that split never happened — see the
// header of DeferredChrome.tsx. The `dynamic()` calls now live behind a client
// boundary, which is where `import()` is an actual split point.
import {
  DeferredNavigationProgress as NavigationProgress,
  DeferredSearchBar as SearchBar,
  DeferredMobileSearchTrigger as MobileSearchTrigger,
} from "@/components/layout/DeferredChrome";

// LAT-P202: `preload: false` is the whole fix, and it is deliberate.
//
// next/font preloads by default, which emits `<link rel="preload" as="font">` into the document
// head. A font preload is a HIGH-priority fetch, so on a slow connection this 31 kB file competes
// with — and is scheduled ahead of — the render-blocking CSS and the entry JS that actually draw
// the page. That would be a fair trade if the font drew the page. It does not: JetBrains Mono is
// wired only into `fontFamily.mono` (tailwind.config.ts) / `--font-mono` (globals.css), i.e. the
// probability numbers. Body copy and headings run on the system sans stack, and the measured LCP
// element on Discover is a plain `text-2xl font-black` DIV that never waits on this file.
//
// Measured on production before changing anything, by simulating exactly this edit — stripping the
// preload tag out of the live HTML and serving both arms from the same bytes, interleaved, 3G +
// 4x CPU, 390 ms TTFB on both arms, n=6/6 (tools/cold-load.mjs, COLD_ABLATE=fontpreload):
//
//     FCP  1810 -> 1422 ms  (-388)      LCP  2726 -> 2516 ms  (-210)
//     DCL  1820 -> 1431 ms  (-389)      load 2655 -> 2452 ms  (-203)
//     CLS 0.062 -> 0.062    (unchanged — next/font's metric-matched fallback absorbs the swap)
//
// `display: "swap"` stays and is what makes this safe: the numbers render immediately in the
// fallback and swap when the font lands. Dropping the preload lengthens that fallback window; it
// does not create one. CLS was measured, not assumed, precisely because that window gets longer.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-jetbrains-mono",
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: {
    template: "%s | Bain Luck",
    default: "Bain Luck — Prediction Market Discovery",
  },
  description:
    "See what the world thinks will happen. Explore prediction markets as intuitive probabilities across sports, politics, economics, entertainment, and weather.",
  keywords: [
    "prediction markets",
    "odds",
    "probabilities",
    "sports odds",
    "politics predictions",
    "economics forecasts",
    "Kalshi",
    "Polymarket",
    "calibration",
  ],
  metadataBase: new URL("https://bainluck.com"),
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    siteName: "Bain Luck",
    title: "Bain Luck — Prediction Market Discovery",
    description:
      "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.",
    url: "https://bainluck.com",
  },
  twitter: {
    card: "summary",
    title: "Bain Luck — Prediction Market Discovery",
    description:
      "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.",
  },
};


const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "Bain Luck",
  url: "https://bainluck.com",
  description:
    "Prediction market discovery platform that translates betting and prediction markets into intuitive probabilities.",
  applicationCategory: "FinanceApplication",
  operatingSystem: "Web, iOS, macOS",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const buildCommit = frontendCommitSha();

  return (
    <html lang="en" className={jetbrainsMono.variable}>
      <head>
        {/* Frontend deployment identity (L2-221). Vercel deploys independently
            of Heroku and of the GitHub SHA that triggered CI, so a browser
            audit needs the FRONTEND's own marker to know which build it just
            rendered. Non-secret: a commit sha of a public repo. Rendered here
            as well as at /api/frontend-build so the marker travels with the page that
            was actually captured, not just with an API call beside it. */}
        {buildCommit && <meta name={BUILD_META_NAME} content={buildCommit} />}
        {/* Preconnect to API origin — saves DNS + TLS roundtrip on first fetch */}
        <link rel="preconnect" href={apiUrl} crossOrigin="anonymous" />
        <link rel="dns-prefetch" href={apiUrl} />
        {/* ESPN CDN for team logos */}
        <link rel="preconnect" href="https://a.espncdn.com" crossOrigin="anonymous" />
        <link rel="dns-prefetch" href="https://a.espncdn.com" />
      </head>
      <body className="font-sans">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        <Suspense fallback={null}>
          <NavigationProgress />
        </Suspense>
        {/* Every CONSENT-GATED telemetry provider (GA/gtag.js, Vercel
            Analytics, Web Vitals) mounts ONLY through the consent gate — see
            components/Analytics/TelemetryGate.tsx. */}
        <TelemetryGate />
        {/* Speed Insights is mounted OUTSIDE the gate, and that is the ruling
            (LAT-P197, Alex D30 / 2026-09-01), not an oversight.

            It is strictly-necessary performance telemetry: no cookie, no
            storage read, no identifier — it reports how fast this page
            rendered for the visitor whose page it was. Behind the gate it only
            ever measured visitors who had already answered the banner, which
            is the slowest-page population least likely to be represented: the
            number we tune the site on was sampled on consent, not on traffic.

            Consequence, stated plainly because it is a real one: a visitor who
            declines still sends speed beacons. `/privacy` and the banner both
            say so — the C90 P1 lesson runs in both directions, and copy that
            claims a decline stops everything would now be the false half. */}
        <SpeedInsights />
        <SWRProvider>
        <AnalyticsProvider>
          <AuthProvider>
            <PinSyncEffect />
            <div className="min-h-screen flex flex-col bg-surface-deep">
              {/* Header */}
              <header className="bg-surface-card/80 backdrop-blur-lg border-b border-surface-border sticky top-0 z-50">
                <div className="max-w-content mx-auto px-4 md:px-6 py-3">
                  <div className="flex items-center justify-between gap-4">
                    <Link href="/" className="flex items-center gap-2.5">
                      <span className="text-xl">🍀</span>
                      <span className="text-lg font-semibold text-text-primary tracking-tight">
                        Bain Luck
                      </span>
                    </Link>

                    <DesktopNav />

                    <div className="md:hidden flex-1 min-w-0 mx-2">
                      <MobileSearchTrigger />
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="hidden md:block w-64 lg:w-80">
                        <SearchBar compact />
                      </div>
                      <UserMenu />
                    </div>
                  </div>
                </div>
              </header>

              {/* Main Content */}
              <main className="flex-1 pb-20 md:pb-0">
                <div className="max-w-content mx-auto px-3 md:px-6 py-4">
                  {children}
                </div>
              </main>

              {/* Site footer (all pages) */}
              <Footer />

              {/* Bottom Tab Nav (mobile only) */}
              <BottomNav />
            </div>

            {/* Consent Banner - shows if user hasn't made a choice */}
            <ConsentBanner />
          </AuthProvider>
        </AnalyticsProvider>
        </SWRProvider>
      </body>
    </html>
  );
}
