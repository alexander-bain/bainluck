/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable React strict mode for better development experience
  reactStrictMode: true,

  // Proxy Firebase auth handler through our own domain.
  // This makes signInWithPopup same-origin, avoiding Safari ITP
  // blocking cross-origin popup communication with *.firebaseapp.com.
  // See: https://firebase.google.com/docs/auth/web/redirect-best-practices
  async rewrites() {
    return [
      {
        source: "/__/auth/:path*",
        destination: `https://${process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "bainluck-26a47.firebaseapp.com"}/__/auth/:path*`,
      },
    ];
  },
};

export default nextConfig;
