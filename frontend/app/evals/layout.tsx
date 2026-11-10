import type { Metadata } from "next";

import {
  EVALS_DESCRIPTION,
  EVALS_PATH,
  EVALS_SHARE_TITLE,
  EVALS_TAB_TITLE,
} from "@/lib/evals/copy";
import { defaultShareCard } from "@/lib/shareCard";

// #12102, #12467 — /evals, "How Bain Luck tests itself".
//
// Listed publicly per Ruling 104 (Alex, Mon Nov 9): linked from the footer and
// the sitemap, and indexable. `/daily` keeps its own `noindex`.
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
};

export default function EvalsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
