import type { Metadata } from "next";
import type { EventDetailResponse } from "@/lib/types";
import { buildShareUrl, formatShareProbability, truncateShareText } from "@/lib/share";

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

function statusLabel(event: EventDetailResponse): string {
  if (event.status === "live") return "Live now";
  if (event.status === "completed" || event.status === "closed") return "Final";
  const start = new Date(event.commence_time);
  if (Number.isNaN(start.getTime())) return "Upcoming";
  return start.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
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

  const homeProbability = formatShareProbability(event.current_odds?.home_probability);
  const awayProbability = formatShareProbability(event.current_odds?.away_probability);
  const matchup = `${event.away_team} vs ${event.home_team}`;
  const title = homeProbability && awayProbability
    ? `${matchup}: ${event.home_team} ${homeProbability}, ${event.away_team} ${awayProbability} | Bain Luck`
    : `${matchup} Odds | Bain Luck`;
  const description = truncateShareText(
    homeProbability && awayProbability
      ? `${statusLabel(event)}. Bain Luck gives ${event.home_team} a ${homeProbability} win probability and ${event.away_team} a ${awayProbability} win probability.`
      : `${statusLabel(event)}. Follow ${matchup} with probability-first odds on Bain Luck.`
  );
  const url = buildShareUrl(`/events/${event.id}`);
  const image = buildShareUrl(`/events/${event.id}/opengraph-image`);

  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title,
      description,
      url,
      siteName: "Bain Luck",
      type: "article",
      images: [{ url: image, alt: matchup, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export default function EventDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
