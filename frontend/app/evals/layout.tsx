import type { Metadata } from "next";

import {
  EVALS_DESCRIPTION,
  EVALS_PATH,
  EVALS_SHARE_TITLE,
  EVALS_TAB_TITLE,
} from "@/lib/evals/copy";
import { defaultShareCard } from "@/lib/shareCard";

// #12102 — /evals, "How Bain Luck tests itself".
//
// UNLISTED, per Decide 43-A1 (Alex, Nov 5): `noindex, nofollow`, no footer link
// and no sitemap entry until Alex has read the served page on his phone. The
// route still renders for anyone holding the URL; S10 removes this line and adds
// the footer link and the sitemap entry, with Alex's "looks right" on NOW.
// `/daily` carries the same pair for the same reason.
//
// The canonical and `og:url` name this route, and the share card is explicit,
// because a route that declares `openGraph` does not reliably inherit the root
// card (`lib/shareCard.ts`; enforced by `__tests__/shareUnfurl.test.ts`).
export const metadata: Metadata = {
  title: EVALS_TAB_TITLE,
  description: EVALS_DESCRIPTION,
  alternates: { canonical: EVALS_PATH },
  openGraph: {
    title: EVALS_SHARE_TITLE,
    description: EVALS_DESCRIPTION,
    url: EVALS_PATH,
    images: defaultShareCard(),
  },
  robots: { index: false, follow: false },
};

export default function EvalsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
