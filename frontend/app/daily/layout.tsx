import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #4193: a pass-through layout that exists only to state this route's identity.
// Without it the page inherits the root's `canonical: "/"` and `og:url: "/"` and
// tells search engines and unfurlers that it is a duplicate of the home page.
//
// #6445: the standalone Daily Challenge page is held back for the initial
// release along with the Discover surfaces that fed it. Nothing on the site
// links here — measured, `/daily` appears in no other file — and it is in no
// sitemap, so search was the last way a reader could still be promoted into a
// game we are hiding. `/play` already carries exactly this pair of lines for
// exactly this reason ("Unlisted from nav; keep it out of search indexes too").
// The route still renders for anyone holding the URL: hidden, not deleted.
export const metadata: Metadata = {
  ...selfCanonical("/daily"),
  robots: { index: false, follow: false },
};

export default function DailyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
