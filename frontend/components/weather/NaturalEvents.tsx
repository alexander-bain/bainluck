"use client";

import useSWR from "swr";
import type { EventMarket } from "./data";
import { SectionHeader } from "./RainForecast";
import HurricaneTracker from "./HurricaneTracker";
import EventList from "./EventList";
import { fetchNaturalEvents } from "@/lib/weatherApi";

function EventListSkeleton({ title, sub, icon, accent, rows }: { title: string; sub: string; icon: string; accent: string; rows: number }) {
  return (
    <div style={{ backgroundColor: "var(--surface-card)", borderRadius: 16, padding: 22 }}>
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
            {/* Uniform, not sinusoidal. A skeleton bar row whose heights vary
                draws a distribution the data has not arrived to justify —
                grey, but still a shape. ux/1069, #2960. */}
            <div className="w-full bg-gray-200 rounded animate-pulse" style={{ height: "60%" }} />
          </div>
        ))}
      </div>
      <div className="flex flex-col" style={{ gap: 0 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="grid items-center" style={{ gridTemplateColumns: "1fr auto auto", gap: 10, padding: "10px 0", borderTop: i > 0 ? "1px solid var(--surface-border)" : undefined }}>
            {/* Two lines, because the row it stands in for is two lines: the
                question, then the outcome and the source under it. A one-line
                skeleton here re-introduced the jump the stacked row exists to
                remove — every row grew when the data landed. ux/1083, #3147. */}
            <div style={{ minWidth: 0 }}>
              <div className="h-3.5 bg-gray-200 rounded animate-pulse mb-2" style={{ width: `${80 - i * 10}%` }} />
              <div className="flex items-center gap-2">
                <div className="h-3 w-20 bg-gray-200 rounded animate-pulse" />
                <div className="h-4 w-14 bg-gray-200 rounded-full animate-pulse" />
              </div>
            </div>
            <div className="h-1.5 w-[72px] bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-9 bg-gray-200 rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * A subsection the endpoint answered with an empty list (#2243). Tokens only:
 * no accent tint, because an empty card has no data for the accent to mark.
 */
function EventListEmpty({ title, sub, empty }: { title: string; sub: string; empty: string }) {
  return (
    <div className="bg-surface-card" style={{ borderRadius: 16, padding: 22 }}>
      <h3 className="text-text-primary" style={{ fontSize: 18, fontWeight: 600, margin: 0, lineHeight: 1.2 }}>{title}</h3>
      <span className="text-text-secondary" style={{ fontSize: 12.5 }}>{sub}</span>
      <p className="text-text-secondary text-sm" style={{ paddingTop: 16 }}>{empty}</p>
    </div>
  );
}

function HurricaneTrackerEmpty() {
  return (
    <div className="bg-surface-card" style={{ borderRadius: 16, padding: 22 }}>
      <p className="text-text-secondary text-sm">No live hurricane markets right now</p>
      <p className="text-text-muted text-xs mt-1.5">This card tracks seasonal hurricane markets.</p>
    </div>
  );
}

/**
 * Only an ARRAY with no rows is a proved absence. `undefined` is still
 * loading, and a missing or malformed subsection is not the endpoint saying
 * "nothing" — both keep the skeleton, as before (#2243).
 */
function isProvedEmpty(list: unknown): boolean {
  return Array.isArray(list) && list.length === 0;
}

export default function NaturalEvents() {
  const { data: liveEvents, error } = useSWR("weather-events", fetchNaturalEvents, { refreshInterval: 3600000 });
  const events = liveEvents as { hurricane: EventMarket[]; earthquake: EventMarket[]; tornadoes: EventMarket[] } | undefined;

  const earthquake = events?.earthquake?.length ? events.earthquake : null;
  const tornadoes = events?.tornadoes?.length ? events.tornadoes : null;
  const hurricane = events?.hurricane?.length ? events.hurricane : null;
  // Each subsection earns its own verdict: one empty list must not blank its
  // healthy siblings, and a skeleton that pulses forever over a 200 carrying
  // `[]` is the collapse UX-P170 fixed in RainForecast (#2243).
  const hurricaneEmpty = isProvedEmpty(events?.hurricane);
  const earthquakeEmpty = isProvedEmpty(events?.earthquake);
  const tornadoesEmpty = isProvedEmpty(events?.tornadoes);

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
          ) : hurricaneEmpty ? (
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
          ) : earthquakeEmpty ? (
            <EventListEmpty title="Seismic activity" sub="Earthquake threshold markets." empty="No live earthquake markets right now" />
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
          ) : tornadoesEmpty ? (
            <EventListEmpty title="Tornadoes" sub="Season-long count markets." empty="No live tornado markets right now" />
          ) : (
            <EventListSkeleton title="Tornadoes" sub="Season-long count markets." icon="&#x27F3;" accent="#F59E0B" rows={3} />
          )}
        </div>
      </div>
    </section>
  );
}
