"use client";

import useSWR from "swr";
import type { EventMarket } from "./data";
import { SectionHeader } from "./RainForecast";
import HurricaneTracker from "./HurricaneTracker";
import EventList from "./EventList";
import { fetchNaturalEvents } from "@/lib/weatherApi";

function ListCardHeader({ title, sub, icon, accent }: { title: string; sub: string; icon: string; accent: string }) {
  return (
    <div className="flex items-center" style={{ gap: 10, marginBottom: 16 }}>
      <div
        className="flex items-center justify-center"
        style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${accent}14`, fontSize: 15, color: accent, flexShrink: 0 }}
      >
        {icon}
      </div>
      <div>
        <h3 style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)", margin: 0, lineHeight: 1.2 }}>{title}</h3>
        <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{sub}</span>
      </div>
    </div>
  );
}

function EventListSkeleton({ title, sub, icon, accent, rows }: { title: string; sub: string; icon: string; accent: string; rows: number }) {
  return (
    <div style={{ backgroundColor: "var(--surface-card)", borderRadius: 16, padding: 22 }}>
      <ListCardHeader title={title} sub={sub} icon={icon} accent={accent} />
      <div className="flex flex-col" style={{ gap: 0 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} style={{ borderTop: i > 0 ? "1px solid var(--surface-border)" : undefined, padding: "10px 0" }}>
            <div className="flex items-center justify-between" style={{ gap: 10 }}>
              <div className="flex-1" style={{ minWidth: 0 }}>
                <div className="h-3.5 bg-gray-200 rounded animate-pulse mb-2" style={{ width: `${70 + i * 5}%` }} />
                <div className="flex items-center gap-2">
                  <div className="h-4 w-14 bg-gray-200 rounded-full animate-pulse" />
                  <div className="h-3 w-16 bg-gray-200 rounded animate-pulse" />
                </div>
              </div>
              <div className="flex items-center" style={{ gap: 8, flexShrink: 0 }}>
                <div className="h-1 w-14 bg-gray-200 rounded animate-pulse" />
                <div className="h-5 w-10 bg-gray-200 rounded animate-pulse" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Loaded, and there is nothing to show. Keeps the card's own header so the
 * section still identifies itself, and replaces the rows with a sentence
 * instead of a skeleton that would pulse forever.
 *
 * The copy states the present and promises nothing. RainForecast's "... appear
 * here when they reopen" would read naturally here, but `app/weather` already
 * owes a fix for `appear-here` in `lib/copyBans.ts` — adding five more
 * instances of a phrase the repo has committed to removing is the wrong way to
 * spend that debt. This follows the guard's own ALLOWED voice instead.
 */
function EventListEmpty({ title, sub, icon, accent, message, hint }: { title: string; sub: string; icon: string; accent: string; message: string; hint: string }) {
  return (
    <div style={{ backgroundColor: "var(--surface-card)", borderRadius: 16, padding: 22 }}>
      <ListCardHeader title={title} sub={sub} icon={icon} accent={accent} />
      <div className="py-12 text-center">
        <p className="text-text-secondary text-sm">{message}</p>
        <p className="text-text-muted text-xs mt-1.5">{hint}</p>
      </div>
    </div>
  );
}

function HurricaneTrackerEmpty() {
  return (
    <div style={{ backgroundColor: "#fff", borderRadius: 16, padding: 22 }}>
      <div style={{ marginBottom: 20 }}>
        <div className="flex items-center" style={{ gap: 6, marginBottom: 6 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: "#B91C1C", flexShrink: 0 }} />
          <span style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", color: "#B91C1C" }}>
            Hurricane Season &middot; 2026
          </span>
        </div>
        <h3 style={{ fontSize: 20, fontWeight: 600, color: "#111827", margin: 0 }}>Atlantic season tracker</h3>
      </div>
      <div className="py-12 text-center">
        <p className="text-text-secondary text-sm">No live hurricane markets right now</p>
        <p className="text-text-muted text-xs mt-1.5">This is where Atlantic season questions sit.</p>
      </div>
    </div>
  );
}

function HurricaneTrackerSkeleton() {
  return (
    <div style={{ backgroundColor: "#fff", borderRadius: 16, padding: 22 }}>
      <div className="flex items-start justify-between" style={{ marginBottom: 20 }}>
        <div>
          <div className="h-3 w-36 bg-gray-200 rounded animate-pulse mb-2" />
          <div className="h-5 w-44 bg-gray-200 rounded animate-pulse" />
        </div>
        <div>
          <div className="h-8 w-12 bg-gray-200 rounded animate-pulse mb-1" />
          <div className="h-3 w-24 bg-gray-200 rounded animate-pulse" />
        </div>
      </div>
      <div className="flex items-end" style={{ gap: 8, height: 120, marginBottom: 20 }}>
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="flex-1 flex flex-col items-center justify-end" style={{ height: "100%" }}>
            <div className="h-3 w-6 bg-gray-200 rounded animate-pulse mb-1" />
            <div className="w-full bg-gray-200 rounded animate-pulse" style={{ height: `${20 + Math.sin(i * 0.8) * 40 + 30}%` }} />
          </div>
        ))}
      </div>
      <div className="flex flex-col" style={{ gap: 0 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="grid items-center" style={{ gridTemplateColumns: "1fr auto auto", gap: 10, padding: "10px 0", borderTop: i > 0 ? "1px solid var(--surface-border)" : undefined }}>
            <div className="h-3.5 bg-gray-200 rounded animate-pulse" style={{ width: `${80 - i * 10}%` }} />
            <div className="h-1.5 w-[72px] bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-9 bg-gray-200 rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function NaturalEvents() {
  const { data: liveEvents, error } = useSWR("weather-events", fetchNaturalEvents, { refreshInterval: 3600000 });
  const events = liveEvents as { hurricane: EventMarket[]; earthquake: EventMarket[]; tornadoes: EventMarket[] } | undefined;

  // Only `undefined` means still-loading. A 200 carrying an empty list means
  // loaded-and-empty, and must show an honest card rather than a skeleton that
  // pulses forever (gotcha #53: an empty 200 is a response shape, not an
  // absence). Same defect UX-P170 fixed in RainForecast, same remedy.
  const loaded = liveEvents !== undefined;
  const earthquake = events?.earthquake?.length ? events.earthquake : null;
  const tornadoes = events?.tornadoes?.length ? events.tornadoes : null;
  const hurricane = events?.hurricane?.length ? events.hurricane : null;

  if (error && !events) {
    return (
      <section className="pt-14 px-4 md:px-6">
        <div className="max-w-[1280px] mx-auto">
          <SectionHeader
            kicker="Natural events"
            title="Bigger picture. Rarer events."
            meta="Hurricanes · Earthquakes · Tornadoes"
          />
          <div className="bg-surface-card border border-surface-border rounded-2xl py-16 text-center">
            <p className="text-text-secondary text-sm">Failed to load natural events data</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="pt-14 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Natural events"
          title="Bigger picture. Rarer events."
          meta="Hurricanes · Earthquakes · Tornadoes"
        />
        <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] lg:grid-cols-[1.4fr_1fr_1fr] gap-3.5">
          {hurricane ? (
            <HurricaneTracker items={hurricane} />
          ) : loaded ? (
            <HurricaneTrackerEmpty />
          ) : (
            <HurricaneTrackerSkeleton />
          )}
          {earthquake ? (
            <EventList
              title="Seismic activity"
              sub="Earthquake threshold markets."
              icon="&#x2299;"
              items={earthquake}
              accent="#7C3AED"
            />
          ) : loaded ? (
            <EventListEmpty
              title="Seismic activity"
              sub="Earthquake threshold markets."
              icon="&#x2299;"
              accent="#7C3AED"
              message="No live earthquake markets right now"
              hint="This is where earthquake threshold questions sit."
            />
          ) : (
            <EventListSkeleton title="Seismic activity" sub="Earthquake threshold markets." icon="&#x2299;" accent="#7C3AED" rows={5} />
          )}
          {tornadoes ? (
            <EventList
              title="Tornadoes"
              sub="Season-long count markets."
              icon="&#x27F3;"
              items={tornadoes}
              accent="#F59E0B"
            />
          ) : loaded ? (
            <EventListEmpty
              title="Tornadoes"
              sub="Season-long count markets."
              icon="&#x27F3;"
              accent="#F59E0B"
              message="No live tornado markets right now"
              hint="This is where season-long tornado counts sit."
            />
          ) : (
            <EventListSkeleton title="Tornadoes" sub="Season-long count markets." icon="&#x27F3;" accent="#F59E0B" rows={3} />
          )}
        </div>
      </div>
    </section>
  );
}
