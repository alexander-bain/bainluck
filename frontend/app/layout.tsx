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
        <div className="min-h-screen flex flex-col bg-snow">
          {/* Header */}
          <header className="bg-white border-b border-mist sticky top-0 z-50">
            <div className="max-w-content mx-auto px-4 md:px-8 lg:px-12 py-4">
              <div className="flex items-center justify-between">
                <Link href="/" className="flex items-center">
                  <span className="text-title-2 text-graphite">
                    OddsTracker
                  </span>
                </Link>
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
            <div className="max-w-content mx-auto px-4 md:px-8 lg:px-12 py-4">
              <p className="text-center text-caption text-slate">
                Win probabilities updated in real-time
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}

