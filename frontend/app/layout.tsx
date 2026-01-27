import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OddsTracker - Win Probabilities",
  description: "See sports betting odds as intuitive win probabilities",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen flex flex-col">
          {/* Header */}
          <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
            <div className="max-w-6xl mx-auto px-4 py-4">
              <div className="flex items-center justify-between">
                <Link href="/" className="flex items-center gap-2">
                  <span className="text-2xl">📊</span>
                  <span className="text-xl font-bold text-gray-900">
                    OddsTracker
                  </span>
                </Link>
                <nav className="flex items-center gap-4">
                  <Link
                    href="/"
                    className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                  >
                    All Events
                  </Link>
                </nav>
              </div>
            </div>
          </header>

          {/* Main Content */}
          <main className="flex-1">
            <div className="max-w-6xl mx-auto px-4 py-6">{children}</div>
          </main>

          {/* Footer */}
          <footer className="bg-white border-t border-gray-200 mt-auto">
            <div className="max-w-6xl mx-auto px-4 py-4">
              <p className="text-center text-sm text-gray-500">
                OddsTracker - Convert odds to win probabilities
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
