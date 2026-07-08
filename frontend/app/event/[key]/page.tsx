"use client";

// #999 Event Concept Pages — slice 1. Generic /event/[key] rendering any
// individual-competitor event via /api/event/{key}. Golf renders here at parity
// (winner field + sections + matchups). Probability-only (no odds), light-mode
// tokens, blend-only (no source names on plain rows).

import { useParams } from "next/navigation";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchEventConcept, formatProbability } from "@/lib/api";
import {
  statusLabel,
  fieldOrder,
  childLeader,
  eventDateRange,
} from "@/lib/eventConceptDisplay";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

export default function EventConceptPage() {
  // Next.js 14: dynamic params for a CLIENT component come from useParams().
  // `use(params)` on a plain object throws at render (L2-60 P1). useParams()
  // returns the segment STILL percent-encoded, so decode ONCE here before
  // fetchEventConcept re-encodes it for the URL — otherwise the key double-encodes
  // (event%253A…) and the fetch 404s (L2-61). decodeURIComponent is safe/idempotent
  // for our keys (colons aren't %-escapes). #999
  const params = useParams();
  const rawKey = (params?.key as string) || "";
  const decodedKey = (() => {
    try {
      return decodeURIComponent(rawKey);
    } catch {
      return rawKey;
    }
  })();

  // GA4 hooks — before any conditional return (MANDATORY).
  usePageTracking({ pageType: "event_concept", pageTitle: `Event ${decodedKey}` });
  useScrollDepth({ pageType: "event_concept" });
  useEngagementTime({ pageType: "event_concept" });

  const { data, error, isLoading } = useSWR(
    decodedKey ? ["event-concept", decodedKey] : null,
    () => fetchEventConcept(decodedKey),
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <LoadingSpinner text="Loading event..." />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <ErrorMessage
          title="Event not found"
          message="This event may have no markets yet, or the link is incorrect."
        />
      </div>
    );
  }

  const { event, primary, sections, children } = data;
  const dateRange = eventDateRange(event.start_date, event.end_date);
  const competitors = fieldOrder(primary.competitors).slice(0, 20);

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="border-b border-surface-border pb-4">
        <div className="flex items-center gap-2 mb-2 text-[11px] uppercase tracking-widest text-text-muted">
          <span>{event.domain}</span>
          <span
            className={`px-1.5 py-0.5 rounded font-semibold ${
              event.status === "live"
                ? "bg-accent-live/15 text-accent-live"
                : event.status === "settled"
                  ? "bg-text-muted/15 text-text-secondary"
                  : "bg-accent-brand/10 text-accent-brand"
            }`}
          >
            {statusLabel(event.status)}
          </span>
        </div>
        <h1 className="text-title-1 font-semibold text-text-primary tracking-tight">
          {event.name || decodedKey}
        </h1>
        {(dateRange || event.venue || event.location) && (
          <p className="text-sm text-text-secondary mt-1.5">
            {[dateRange, event.venue, event.location].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>

      {/* Primary block — winner-field leaderboard (flexes to co-equal list in a
          future slice via primary.kind). Probability-only. */}
      {primary.kind === "winner_field" && competitors.length > 0 && (
        <section className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-4">
            {primary.label || "Winner"}
          </h2>
          <div className="space-y-1.5">
            {competitors.map((c, i) => (
              <div
                key={`${c.name}-${i}`}
                className="flex items-center justify-between py-1.5 border-b border-surface-border/40 last:border-0"
              >
                <span className="text-sm text-text-primary">
                  <span className="text-text-muted font-mono text-xs mr-2">{i + 1}</span>
                  {c.name}
                </span>
                <span className="font-mono text-sm font-semibold text-text-primary tabular-nums">
                  {formatProbability(c.probability)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Market sections (winner / top-N / props) */}
      {sections.length > 0 && (
        <section className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-3">Markets</h2>
          <div className="flex flex-wrap gap-2">
            {sections.map((s) => (
              <span
                key={s.type}
                className="text-xs px-2 py-1 rounded-full bg-surface-elevated text-text-secondary"
              >
                {s.label}
                {s.market_ids && s.market_ids.length > 0 ? ` · ${s.market_ids.length}` : ""}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Children — matchups / props */}
      {children.length > 0 && (
        <section className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-4">Matchups &amp; props</h2>
          <div className="space-y-2">
            {children.map((child) => {
              const lead = childLeader(child);
              return (
                <div
                  key={child.market_id}
                  className="flex items-center justify-between py-1.5 border-b border-surface-border/40 last:border-0"
                >
                  <span className="text-sm text-text-secondary truncate mr-3">
                    {child.market_name || child.name || "Market"}
                  </span>
                  {lead && (
                    <span className="text-sm text-text-primary whitespace-nowrap">
                      {lead.name}{" "}
                      <span className="font-mono font-semibold tabular-nums">
                        {formatProbability(lead.probability)}
                      </span>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
