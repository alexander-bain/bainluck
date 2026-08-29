import type { Metadata } from "next";
import type { EventDetailResponse } from "@/lib/types";
import { buildShareUrl } from "@/lib/share";
import { buildEventShareCopy, withSiteSuffix } from "@/lib/eventShareMeta";
import EventBootScript from "@/components/event/EventBootScript";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

async function fetchEvent(id: string): Promise<EventDetailResponse | null> {
  const eventId = Number.parseInt(id, 10);
  if (!Number.isFinite(eventId) || eventId <= 0) return null;

  try {
    const response = await fetch(`${API_URL}/api/events/${eventId}`, {
      next: { revalidate: 60 },
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const event = await fetchEvent(id);
  if (!event) {
    return {
      title: "Event Odds - Bain Luck",
      description: "Game probabilities translated into plain English.",
    };
  }

  // Q441/#1495: a settled event leads with the RESULT, not with the last price
  // captured before the final whistle. The copy decision lives in a pure module so
  // it is testable without a browser; this layout only wires it.
  const matchup = `${event.away_team} vs ${event.home_team}`;
  const { title, description } = buildEventShareCopy(event);
  // The root layout's metadata template is `%s | Bain Luck`, so `title` must NOT
  // carry a suffix — appending one here is what printed `| Bain Luck | Bain Luck`
  // on every event page. og:/twitter: bypass the template and so add it explicitly.
  const socialTitle = withSiteSuffix(title);
  const url = buildShareUrl(`/events/${event.id}`);
  const image = buildShareUrl(`/events/${event.id}/opengraph-image`);

  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: socialTitle,
      description,
      url,
      siteName: "Bain Luck",
      type: "article",
      images: [{ url: image, alt: matchup, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
      images: [image],
    },
  };
}

/**
 * LAT-P219 (#2846) — the boot script is rendered by the LAYOUT, not by the page.
 *
 * The other three boots (`/discover`, `/sports`, `/tournaments/{slug}`) sit inside their page's own
 * JSX, which works because those pages render one tree. `app/events/[id]/page.tsx` does not: it is a
 * `"use client"` page whose FIRST render — the one the server emits into the HTML — takes an early
 * `if (eventLoading)` return that paints a `LoadingSpinner` and nothing else. A boot script placed in
 * the page's main return would therefore never appear in the server-rendered document, never
 * execute, and never park anything, while every unit test that renders the loaded state still
 * passed. Putting it in the layout removes the dependency on which branch the page takes.
 */
export default async function EventDetailLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const eventId = Number.parseInt(id, 10);
  const bootable = Number.isFinite(eventId) && eventId > 0;

  return (
    <>
      {bootable && <EventBootScript eventId={eventId} />}
      {children}
    </>
  );
}
