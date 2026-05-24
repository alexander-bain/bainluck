import type { Metadata } from "next";
import Link from "next/link";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { GoogleAnalytics, AnalyticsProvider, ConsentBanner } from "@/components/Analytics";
import { AuthProvider } from "@/components/AuthProvider";
import PinSyncEffect from "@/components/PinSyncEffect";
import dynamic from "next/dynamic";
import UserMenu from "@/components/UserMenu";
const SearchBar = dynamic(() => import("@/components/SearchBar"), { ssr: false });
import SWRProvider from "@/components/SWRProvider";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import BottomNav from "@/components/BottomNav";
import DesktopNav from "@/components/DesktopNav";
import { Suspense } from "react";
const NavigationProgress = dynamic(() => import("@/components/NavigationProgress"), { ssr: false });
const MobileSearchTrigger = dynamic(() => import("@/components/MobileSearchTrigger"), { ssr: false });

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-jetbrains-mono",
  display: "swap",
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

  return (
    <html lang="en" className={jetbrainsMono.variable}>
      <head>
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
        <GoogleAnalytics />
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

              {/* Bottom Tab Nav (mobile only) */}
              <BottomNav />

              {/* Footer (desktop only) */}
            </div>

            {/* Consent Banner - shows if user hasn't made a choice */}
            <ConsentBanner />
          </AuthProvider>
        </AnalyticsProvider>
        </SWRProvider>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
