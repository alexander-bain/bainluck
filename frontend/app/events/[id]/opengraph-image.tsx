import { ImageResponse } from "next/og";
import type { EventDetailResponse } from "@/lib/types";
import { formatShareProbability } from "@/lib/share";

export const runtime = "edge";
export const alt = "Bain Luck game probability";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function eventStatus(event: EventDetailResponse): string {
  if (event.status === "live") return "Live now";
  if (event.status === "completed" || event.status === "closed") return "Final";
  return "Upcoming";
}

export default async function Image({ params }: { params: { id: string } }) {
  const event = await fetchEvent(params.id);
  const homeProbability = event?.current_odds?.home_probability ?? 0.5;
  const awayProbability = event?.current_odds?.away_probability ?? 0.5;
  const awayPct = formatShareProbability(awayProbability) || "--";
  const homePct = formatShareProbability(homeProbability) || "--";
  const awayWidth = Math.max(3, Math.min(97, Math.round(awayProbability * 100)));
  const homeColor = event?.home_team_data?.primary_color || "#2563eb";
  const awayColor = event?.away_team_data?.primary_color || "#dc2626";
  const awayTeam = event?.away_team || "Away";
  const homeTeam = event?.home_team || "Home";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background: "#f8fafc",
          color: "#111827",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ fontSize: 38 }}>🍀</div>
            <div style={{ fontSize: 30, fontWeight: 800 }}>Bain Luck</div>
          </div>
          <div
            style={{
              border: "2px solid #d1d5db",
              borderRadius: 999,
              padding: "10px 18px",
              fontSize: 20,
              color: "#4b5563",
            }}
          >
            {event?.sport_key || event?.sport || "Event"}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 36 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18, width: 460 }}>
            <div
              style={{
                width: 126,
                height: 126,
                borderRadius: 32,
                background: awayColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "white",
                fontSize: 44,
                fontWeight: 900,
              }}
            >
              {initials(awayTeam)}
            </div>
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05 }}>{awayTeam}</div>
            <div style={{ fontSize: 74, fontWeight: 950, color: awayColor }}>{awayPct}</div>
          </div>

          <div style={{ color: "#94a3b8", fontSize: 38, fontWeight: 800 }}>vs</div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 18, width: 460 }}>
            <div
              style={{
                width: 126,
                height: 126,
                borderRadius: 32,
                background: homeColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "white",
                fontSize: 44,
                fontWeight: 900,
              }}
            >
              {initials(homeTeam)}
            </div>
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05, textAlign: "right" }}>{homeTeam}</div>
            <div style={{ fontSize: 74, fontWeight: 950, color: homeColor }}>{homePct}</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              width: "100%",
              height: 30,
              borderRadius: 999,
              background: homeColor,
              overflow: "hidden",
              display: "flex",
            }}
          >
            <div style={{ width: `${awayWidth}%`, height: "100%", background: awayColor }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#64748b", fontSize: 23 }}>
            <div>{event ? eventStatus(event) : "Probability-first odds"}</div>
            <div>bainluck.com/discover</div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
