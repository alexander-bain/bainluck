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
import BottomNav from "@/components/BottomNav";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Bain Luck - Win Probabilities",
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

                    <div className="flex items-center gap-3">
                      {/* Desktop: full search bar */}
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
              <footer className="hidden md:block bg-surface-card border-t border-surface-border mt-auto">
                <div className="max-w-content mx-auto px-6 py-4">
                  <nav className="flex items-center justify-center gap-6">
                    <Link
                      href="/pulse"
                      className="flex items-center gap-1.5 text-text-muted hover:text-text-secondary transition-colors text-sm"
                    >
                      <span>💓</span>
                      <span>What is Pulse?</span>
                    </Link>
                    <span className="text-surface-border">·</span>
                    <Link
                      href="/market-moves"
                      className="flex items-center gap-1.5 text-text-muted hover:text-text-secondary transition-colors text-sm"
                    >
                      <span>📊</span>
                      <span>Market Moves</span>
                    </Link>
                    <span className="text-surface-border">·</span>
                    <Link
                      href="/oscars"
                      className="flex items-center gap-1.5 text-text-muted hover:text-text-secondary transition-colors text-sm"
                    >
                      <span>🏆</span>
                      <span>Oscars</span>
                    </Link>
                    <span className="text-surface-border">·</span>
                    <Link
                      href="/about"
                      className="flex items-center gap-1.5 text-text-muted hover:text-text-secondary transition-colors text-sm"
                    >
                      <span>🍀</span>
                      <span>About</span>
                    </Link>
                  </nav>
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
