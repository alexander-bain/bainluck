"use client";

import useSWR from "swr";
import { probColor } from "./data";
import type { RainDay, MonthlyRain as MonthlyRainType } from "./data";
import { SourceBadge } from "./SourceBadge";
import { fetchRain } from "@/lib/weatherApi";

/* ── SectionHeader ───────────────────────────────────────────────────── */

interface SectionHeaderProps {
  kicker: string;
  title: string;
  meta?: string;
}

export function SectionHeader({ kicker, title, meta }: SectionHeaderProps) {
  return (
    <div className="mb-5">
      <span
        className="uppercase tracking-widest font-bold text-emerald-600"
        style={{ fontSize: 11 }}
      >
        {kicker}
      </span>
      <h2
        className="text-text-primary mt-1"
        style={{ fontSize: 28, fontWeight: 600, lineHeight: 1.2 }}
      >
        {title}
      </h2>
      {meta && (
        <span className="text-text-muted font-mono text-xs mt-1 block">
          {meta}
        </span>
      )}
    </div>
  );
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

function rainBarColor(prob: number): string {
  if (prob >= 65) return "#3B82F6";
  if (prob >= 35) return "#F59E0B";
  return "#CBD5E1";
}

function rainTextColor(prob: number): string {
  if (prob >= 65) return "#3B82F6";
  if (prob >= 35) return "#F59E0B";
  return "var(--text-secondary)";
}

function currentMonth(): string {
  const months = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  return months[new Date().getMonth()];
}

/* ── Skeletons ───────────────────────────────────────────────────────── */

function RainDaySkeleton() {
  return (
    <div
      className="grid gap-2 mt-5"
      style={{ gridTemplateColumns: "repeat(7, minmax(70px, 1fr))" }}
    >
      {Array.from({ length: 7 }).map((_, i) => (
        <div
          key={i}
          className="flex flex-col items-center text-center border py-3 px-1 border-surface-border"
          style={{ borderRadius: 12 }}
        >
          <div className="h-3 w-8 bg-gray-200 rounded animate-pulse" />
          <div className="h-2 w-10 bg-gray-200 rounded animate-pulse mt-1" />
          <div className="h-7 w-7 bg-gray-200 rounded-full animate-pulse mt-2 mb-2" />
          <div className="h-5 w-10 bg-gray-200 rounded animate-pulse" />
          <div className="w-full mt-2 px-1">
            <div className="h-1 bg-gray-200 rounded-full animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

function MonthlySkeleton() {
  return (
    <div className="flex flex-col gap-2.5">
      {Array.from({ length: 10 }).map((_, i) => (
        <div
          key={i}
          className="grid items-center gap-2"
          style={{ gridTemplateColumns: "90px 1fr 42px 36px" }}
        >
          <div className="h-4 bg-gray-200 rounded animate-pulse" />
          <div className="h-[7px] bg-gray-200 rounded-full animate-pulse" />
          <div className="h-4 w-10 bg-gray-200 rounded animate-pulse ml-auto" />
          <div className="h-3 w-6 bg-gray-200 rounded animate-pulse ml-auto" />
        </div>
      ))}
    </div>
  );
}

/* ── Main Component ──────────────────────────────────────────────────── */

export default function RainForecast() {
  const { data: liveRain, error } = useSWR("weather-rain", fetchRain, { refreshInterval: 3600000 });
  const rain: RainDay[] | null = (liveRain as { daily: RainDay[] })?.daily?.length ? (liveRain as { daily: RainDay[] }).daily : null;
  const monthlyLive = (liveRain as { monthly: MonthlyRainType[] })?.monthly;
  const monthly: MonthlyRainType[] | null = monthlyLive?.length ? monthlyLive : null;
  const maxMonthly = monthly ? Math.max(...monthly.map((m) => m.prob)) : 0;
  const month = currentMonth();

  return (
    <section className="pt-14 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader kicker="Precipitation" title="Rain & rainfall" />

        <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-3.5">
          {/* Left card — 7-day rain */}
          <div className="bg-surface-card rounded-2xl border border-surface-border p-6">
            <div className="flex items-start justify-between mb-1">
              <div>
                <h3
                  className="text-text-primary"
                  style={{ fontSize: 20, fontWeight: 600 }}
                >
                  NYC · 7-day rain probability
                </h3>
                <p className="text-text-secondary text-sm mt-0.5">
                  Daily &ldquo;Will it rain?&rdquo; markets from Kalshi
                </p>
              </div>
              <SourceBadge src="kalshi" />
            </div>

            {error && !rain ? (
              <div className="py-12 text-center">
                <p className="text-text-secondary text-sm">Failed to load rain data</p>
              </div>
            ) : !rain ? (
              <RainDaySkeleton />
            ) : (
              <>
                <div
                  className="grid gap-2 mt-5 overflow-x-auto"
                  style={{ gridTemplateColumns: "repeat(7, minmax(70px, 1fr))" }}
                >
                  {rain.map((d: RainDay, i: number) => {
                    const isToday = i === 0;
                    const barCol = rainBarColor(d.prob);
                    const txtCol = rainTextColor(d.prob);

                    return (
                      <div
                        key={d.date}
                        className="flex flex-col items-center text-center border py-3 px-1"
                        style={{
                          borderColor: isToday ? "#BAE6FD" : "var(--surface-border)",
                          backgroundColor: isToday ? "#F0F9FF" : "transparent",
                          borderRadius: 12,
                        }}
                      >
                        <span className="text-xs font-semibold text-text-secondary">
                          {isToday ? "Today" : d.day}
                        </span>
                        <span className="text-[10px] font-mono text-text-muted mt-0.5">
                          {d.date}
                        </span>
                        <span className="mt-2 mb-2" style={{ fontSize: 26 }}>
                          {d.icon}
                        </span>
                        <span
                          className="font-mono font-bold"
                          style={{ fontSize: 20, color: txtCol }}
                        >
                          {d.prob}%
                        </span>
                        <div className="w-full mt-2 px-1">
                          <div
                            className="rounded-full overflow-hidden"
                            style={{
                              height: 4,
                              backgroundColor:
                                d.prob >= 35
                                  ? `${barCol}20`
                                  : "var(--surface-elevated)",
                            }}
                          >
                            <div
                              className="h-full rounded-full transition-all duration-500"
                              style={{ width: `${d.prob}%`, backgroundColor: barCol }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-4 pt-3 border-t border-dashed border-surface-border flex items-center justify-between">
                  <span className="text-xs text-text-muted">
                    Resolves daily at midnight ET
                  </span>
                  <span className="text-xs text-text-muted font-mono">
                    {rain[0].date} – {rain[rain.length - 1].date}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Right card — Monthly rainfall */}
          <div className="bg-surface-card rounded-2xl border border-surface-border p-6">
            <div className="flex items-start justify-between mb-1">
              <h3
                className="text-text-primary"
                style={{ fontSize: 20, fontWeight: 600 }}
              >
                {month} rainfall
              </h3>
              <SourceBadge src="kalshi" />
            </div>
            <p className="text-text-secondary text-sm mb-5">
              &ldquo;Above 1 inch this month&rdquo; — 10 cities
            </p>

            {error && !monthly ? (
              <div className="py-12 text-center">
                <p className="text-text-secondary text-sm">Failed to load monthly data</p>
              </div>
            ) : !monthly ? (
              <MonthlySkeleton />
            ) : (
              <div className="flex flex-col gap-2.5">
                {monthly.map((m: MonthlyRainType) => {
                  const col = probColor(m.prob);
                  const barWidth = Math.max(4, (m.prob / maxMonthly) * 100);
                  const delta = m.delta24h ?? 0;

                  return (
                    <div
                      key={m.city}
                      className="grid items-center gap-2"
                      style={{ gridTemplateColumns: "90px 1fr 42px 36px" }}
                    >
                      <span className="text-sm text-text-primary font-medium truncate">
                        {m.city}
                      </span>
                      <div className="h-[7px] rounded-full overflow-hidden bg-surface-elevated">
                        <div
                          className="h-full rounded-full transition-all duration-700 ease-out"
                          style={{ width: `${barWidth}%`, backgroundColor: col }}
                        />
                      </div>
                      <span
                        className="text-right font-mono font-bold text-sm"
                        style={{ color: col }}
                      >
                        {m.prob}%
                      </span>
                      <span
                        className="text-right font-mono text-[10px]"
                        style={{
                          color: delta > 0 ? "#22C55E" : delta < 0 ? "#EF4444" : "#9CA3AF",
                        }}
                      >
                        {delta > 0 ? `+${delta}` : delta === 0 ? "—" : delta}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="mt-4 pt-3 border-t border-dashed border-surface-border text-xs text-text-muted flex items-center justify-between">
              <span>24h change shown at right</span>
              <span className="font-mono">Kalshi · 10 cities</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
