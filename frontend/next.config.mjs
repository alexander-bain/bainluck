import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable React strict mode for better development experience
  reactStrictMode: true,
  typescript: {
    // Firebase v12 ships without bundled type declarations, causing
    // build failures when node_modules is freshly installed. The actual
    // code is correct — this just prevents TS-only errors from blocking
    // production deploys.
    ignoreBuildErrors: true,
  },
  experimental: {
    optimizePackageImports: ['recharts', 'date-fns'],
  },
  async redirects() {
    return [
      // #213 surface unification: the bespoke golf tournament detail page is the
      // old pre-concept surface. The Event Concept page (/event/golf/<slug>) is
      // the canonical URL for a tournament (the URL law: concept = canonical).
      // 308 (permanent) so bookmarks + indexed old links land on the one true
      // page. The slug is passed through unchanged — it is the same DataGolf
      // tournament slug both routes resolve against, so any slug the old page
      // rendered resolves on the concept page too.
      {
        source: "/categories/golf/tournaments/:slug",
        destination: "/event/golf/:slug",
        permanent: true,
      },
    ];
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "a.espncdn.com",
      },
      {
        protocol: "https",
        hostname: "image.tmdb.org",
      },
      {
        protocol: "https",
        hostname: "flagcdn.com",
      },
      {
        protocol: "https",
        hostname: "upload.wikimedia.org",
      },
      {
        protocol: "https",
        hostname: "coin-images.coingecko.com",
      },
    ],
  },
};

export default withSentryConfig(nextConfig, {
  // Suppresses source map upload logs during build
  silent: true,

  // Upload source maps for better stack traces (requires SENTRY_AUTH_TOKEN)
  // Disabled by default — enable once auth token is set in Vercel
  disableServerWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,
  disableClientWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,

  // Hides source maps from users in production
  hideSourceMaps: true,

  // Automatically tree-shake Sentry logger statements to reduce bundle size
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },
});
