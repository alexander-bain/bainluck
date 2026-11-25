import type { MetadataRoute } from "next";

/**
 * Web app manifest referencing the Decision 382: B / 390: A clear-background
 * brand icon assets (`original artwork supplied by Alex`).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Bain Luck",
    short_name: "Bain Luck",
    description:
      "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.",
    start_url: "/",
    display: "standalone",
    background_color: "#F5F5F7",
    theme_color: "#F5F5F7",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
