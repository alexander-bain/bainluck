import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #4193: a pass-through layout that exists only to state this route's identity.
// Without it the page inherits the root's `canonical: "/"` and `og:url: "/"` and
// tells search engines and unfurlers that it is a duplicate of the home page.
export const metadata: Metadata = selfCanonical("/search");

export default function SearchLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
