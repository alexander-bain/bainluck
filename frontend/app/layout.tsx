import type { Metadata } from "next";
import Link from "next/link";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { GoogleAnalytics, AnalyticsProvider, ConsentBanner } from "@/components/Analytics";
import { AuthProvider } from "@/components/AuthProvider";
import PinSyncEffect from "@/components/PinSyncEffect";
import dynamic from "next/dynamic";
import UserMenu from "@/components/UserMenu";
const SearchBox = dynamic(() => import("@/components/SearchBox"), { ssr: false });
import SWRProvider from "@/components/SWRProvider";
import { Analytics } from "@vercel/analytics/next";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "OddsTracker - Win Probabilities",
  description: "See sports betting odds as intuitive win probabilities",
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
        <GoogleAnalytics />
        <SWRProvider>
        <AnalyticsProvider>
          <AuthProvider>
            <PinSyncEffect />
            <div className="min-h-screen flex flex-col bg-snow">
              {/* Header */}
              <header className="bg-white border-b border-mist sticky top-0 z-50">
                <div className="max-w-content mx-auto px-4 md:px-8 lg:px-12 py-4">
                  <div className="flex items-center justify-between gap-4">
                    <Link href="/" className="flex items-center gap-2">
                      <span className="text-2xl">🎯</span>
                      <span className="text-title-2 text-graphite">
                        OddsTracker
                      </span>
                    </Link>

                    <div className="flex items-center gap-4">
                      <SearchBox />
                      <UserMenu />
                    </div>
                  </div>
                </div>
              </header>

              {/* Main Content */}
              <main className="flex-1">
                <div className="max-w-content mx-auto px-4 md:px-8 lg:px-12 py-6">
                  {children}
                </div>
              </main>

              {/* Footer */}
              <footer className="bg-white border-t border-mist mt-auto">
                <div className="max-w-content mx-auto px-4 md:px-8 lg:px-12 py-6">
                  {/* Navigation Links */}
                  <nav className="flex items-center justify-center gap-6 mb-4">
                    <Link
                      href="/pulse"
                      className="flex items-center gap-1.5 text-slate hover:text-graphite transition-colors"
                    >
                      <span>💓</span>
                      <span className="font-medium">What is Pulse?</span>
                    </Link>
                    <span className="text-mist">|</span>
                    <Link
                      href="/about"
                      className="flex items-center gap-1.5 text-slate hover:text-graphite transition-colors"
                    >
                      <span>🎯</span>
                      <span className="font-medium">About</span>
                    </Link>
                  </nav>

                  {/* Tagline */}
                  <p className="text-center text-caption text-slate">
                    📊 Win probabilities updated in real-time
                  </p>
                </div>
              </footer>
            </div>

            {/* Consent Banner - shows if user hasn't made a choice */}
            <ConsentBanner />
          </AuthProvider>
        </AnalyticsProvider>
        </SWRProvider>
        <Analytics />
      </body>
    </html>
  );
}
