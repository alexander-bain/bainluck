import type { Metadata } from "next";
import type { EventDetailResponse } from "@/lib/types";
import { buildShareUrl } from "@/lib/share";
import {
  buildEventShareCopy,
  isFinishedForShare,
  withSiteSuffix,
} from "@/lib/eventShareMeta";
import {
  isTournamentSportKey,
  resolveEventOutcome,
  type SettledOutcome,
} from "@/lib/eventOutcome";
import type { EventTournamentResponse } from "@/lib/types";
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

/**
 * The tournament container's decided result, for the metadata's rung 2.
 *
 * Asked ONLY for a finished event in a tournament sport — the same `eligible`
 * test `TournamentExtensions` uses, so this never fires on a Lakers game and
 * never costs a scheduled page anything. The route is the one the page itself
 * already calls and is cached for 180s upstream, so on a warm path this is a
 * cache read rather than a second build of the hub.
 *
 * Every failure returns `null`, which the ladder treats as "this rung did not
 * answer" — a metadata request must never take the page down over a section.
 */
async function fetchTournamentResult(
  event: EventDetailResponse,
): Promise<EventTournamentResponse["result"] | null> {
  if (!isFinishedForShare(event)) return null;
  if (!isTournamentSportKey(event.sport)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/tournaments/by-event/${event.id}`,
      { next: { revalidate: 300 } },
    );
    if (!response.ok) return null;
    const payload: EventTournamentResponse = await response.json();
    return payload?.result ?? null;
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

  // CERT-1938: ask the SAME authority ladder the visible hero asks, so the tab and
  // the page cannot disagree about who won. `lib/eventOutcome` owns the order.
  //
  // The score rung is fed STRICTLY: scores go in only when the backend has already
  // stamped `hero_probability_source === "settled"`, which it does only for
  // `completed` with a real completion timestamp. Handing it `event.home_score`
  // unconditionally would re-admit `closed`'s frozen mid-game scores — measured to
  // invert the winner in 2 of 8 sampled rows — through the ladder's front door.
  // The tournament rung has no such problem: it is an independent authority that
  // names a winner outright, so it is trusted for `closed` too.
  const tournamentResult = await fetchTournamentResult(event);
  const scoresAreTrusted = event.hero_probability_source === "settled";
  const outcome: SettledOutcome | null = resolveEventOutcome({
    isFinished: isFinishedForShare(event),
    homeTeam: event.home_team,
    awayTeam: event.away_team,
    homeScore: scoresAreTrusted ? event.home_score ?? null : null,
    awayScore: scoresAreTrusted ? event.away_score ?? null : null,
    tournamentResult,
    linescore: event.linescore,
  });

  const { title, description } = buildEventShareCopy(event, outcome);
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
