"use client";

import useSWR from "swr";
import { probColor, type ClimateMarket } from "./data";
import { fetchClimate } from "@/lib/weatherApi";
import { SourceBadge } from "./SourceBadge";

const COLUMNS: { scale: ClimateMarket["scale"]; label: string; kicker: string }[] = [
  { scale: "2026", label: "2026", kicker: "This year" },
  { scale: "2030", label: "2030", kicker: "End of decade" },
  { scale: "2050", label: "2050", kicker: "Mid-century" },
];

function ClimateColumn({
  label,
  kicker,
  items,
}: {
  label: string;
  kicker: string;
  items: ClimateMarket[];
}) {
  return (
    <div
      className="border border-surface-border"
      style={{
        backgroundColor: "#fff",
        borderRadius: 16,
        padding: 22,
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div
          className="font-mono"
          style={{
            fontSize: 32,
            fontWeight: 600,
            color: "#111827",
            lineHeight: 1,
          }}
        >
          {label}
        </div>
        <span
          style={{
            fontSize: 11.5,
            fontWeight: 600,
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color: "#9CA3AF",
          }}
        >
          {kicker}
        </span>
      </div>

      {/* Market rows */}
      <div className="flex flex-col" style={{ gap: 14 }}>
        {items.length === 0 && (
          <p className="text-text-muted" style={{ fontSize: 12.5 }}>
            No live markets for this horizon yet.
          </p>
        )}
        {items.map((item, i) => {
          const color = probColor(item.prob);

          return (
            <div key={i}>
              {/* Question */}
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: "#374151",
                  marginBottom: 8,
                  textWrap: "pretty",
                }}
              >
                {item.q}
              </div>

              {/* Bar + percentage */}
              <div
                className="flex items-center"
                style={{ gap: 8, marginBottom: 6 }}
              >
                <div
                  style={{
                    flex: 1,
                    height: 6,
                    backgroundColor: "#F3F4F6",
                    borderRadius: 9999,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${item.prob}%`,
                      height: "100%",
                      backgroundColor: color,
                      borderRadius: 9999,
                      transition: "width 0.6s ease-out",
                    }}
                  />
                </div>
                <span
                  className="font-mono"
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color,
                    minWidth: 40,
                    textAlign: "right",
                  }}
                >
                  {item.prob}%
                </span>
              </div>

              {/* Source */}
              <SourceBadge src={item.src} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ClimateColumnSkeleton({ label, kicker }: { label: string; kicker: string }) {
  return (
    <div
      className="border border-surface-border"
      style={{ backgroundColor: "#fff", borderRadius: 16, padding: 22 }}
    >
      <div style={{ marginBottom: 16 }}>
        <div className="font-mono" style={{ fontSize: 32, fontWeight: 600, color: "#111827", lineHeight: 1 }}>{label}</div>
        <span style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", color: "#9CA3AF" }}>{kicker}</span>
      </div>
      <div className="flex flex-col" style={{ gap: 14 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i}>
            <div className="h-3.5 bg-gray-200 rounded animate-pulse mb-2" style={{ width: `${85 - i * 10}%` }} />
            <div className="flex items-center" style={{ gap: 8, marginBottom: 6 }}>
              <div style={{ flex: 1, height: 6, backgroundColor: "#F3F4F6", borderRadius: 9999 }}>
                <div className="h-full bg-gray-200 rounded-full animate-pulse" style={{ width: `${40 + i * 15}%` }} />
              </div>
              <div className="h-4 w-10 bg-gray-200 rounded animate-pulse" />
            </div>
            <div className="h-4 w-14 bg-gray-200 rounded-full animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ClimateDashboard() {
  const { data: liveClimate, error } = useSWR("weather-climate", fetchClimate, { refreshInterval: 21600000 });
  const climate = (liveClimate as ClimateMarket[])?.length ? (liveClimate as ClimateMarket[]) : null;

  if (error && !climate) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-2xl py-16 text-center">
        <p className="text-text-secondary text-sm">Failed to load climate data</p>
      </div>
    );
  }

  // Still loading (undefined) → skeletons. Loaded-but-empty ([]) → honest empty
  // state, NOT infinite bare-header skeletons (#995 freeze symptom; data gap is
  // upstream/Lane 1, this is resilience only).
  if (liveClimate === undefined) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {COLUMNS.map((col) => (
          <ClimateColumnSkeleton key={col.scale} label={col.label} kicker={col.kicker} />
        ))}
      </div>
    );
  }

  if (!climate) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-2xl py-16 text-center">
        <p className="text-text-secondary text-sm">No live climate markets right now</p>
        <p className="text-text-muted text-xs mt-1.5">Long-horizon climate markets appear here when they reopen.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
      {COLUMNS.map((col) => {
        const items = climate.filter((c) => c.scale === col.scale);
        return (
          <ClimateColumn
            key={col.scale}
            label={col.label}
            kicker={col.kicker}
            items={items}
          />
        );
      })}
    </div>
  );
}
