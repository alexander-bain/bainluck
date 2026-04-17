"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { fetchWrestlemaniaCard } from "@/lib/api";
import type { WMCardResponse, WMMatch } from "@/lib/types";
import "../wrestlemania.css";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com";

export default function WrestlemaniaAdminPage() {
  const searchParams = useSearchParams();
  const secret = searchParams.get("secret") || "";
  const [card, setCard] = useState<WMCardResponse | null>(null);
  const [resolving, setResolving] = useState<number | null>(null);

  useEffect(() => {
    fetchWrestlemaniaCard().then(setCard).catch(console.error);
  }, []);

  const resolveMatch = async (matchId: number, winnerOutcomeId: number) => {
    setResolving(matchId);
    try {
      const res = await fetch(
        `${API_URL}/api/wrestlemania/admin/resolve?secret=${encodeURIComponent(secret)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            match_id: matchId,
            winner_outcome_id: winnerOutcomeId,
          }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Resolve failed");
      alert(`Resolved: ${data.winner} wins! (${data.settled_picks} picks settled)`);
      const updated = await fetchWrestlemaniaCard();
      setCard(updated);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Resolve failed");
    } finally {
      setResolving(null);
    }
  };

  if (!secret) {
    return (
      <div className="wrestlemania-theme" style={{ padding: "2rem", textAlign: "center" }}>
        <h1>Admin: Missing ?secret= parameter</h1>
      </div>
    );
  }

  return (
    <div className="wrestlemania-theme" style={{ padding: "1rem" }}>
      <h1 style={{ fontFamily: "'Bebas Neue', Impact, sans-serif", fontSize: "2rem", textAlign: "center", marginBottom: "1rem" }}>
        WrestleMania 42 — Admin
      </h1>

      {card?.nights.map((night) => (
        <div key={night.night}>
          <h2 style={{ fontFamily: "'Bebas Neue', Impact, sans-serif", color: "var(--wm-neon-cyan)", margin: "1.5rem 0 0.5rem" }}>
            Night {night.night}
          </h2>
          {night.matches.map((match) => (
            <div key={match.id} className="wm-match-card" style={{ cursor: "default" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <strong>{match.title}</strong>
                <span className={`wm-match-status ${match.status}`}>{match.status}</span>
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--wm-text-muted)", marginBottom: "0.5rem" }}>
                {match.picks.length} picks placed
              </div>
              {match.status !== "resolved" && (
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {match.outcomes.map((o) => (
                    <button
                      key={o.id}
                      onClick={() => resolveMatch(match.id, o.id)}
                      disabled={resolving === match.id}
                      style={{
                        padding: "0.5rem 1rem",
                        background: "var(--wm-dark-bg)",
                        border: "1px solid var(--wm-card-border)",
                        color: "var(--wm-text-primary)",
                        borderRadius: "4px",
                        cursor: "pointer",
                        fontSize: "0.8rem",
                      }}
                    >
                      {o.name} wins ({o.probability ? Math.round(o.probability * 100) : "?"}%)
                    </button>
                  ))}
                </div>
              )}
              {match.status === "resolved" && (
                <div style={{ color: "var(--wm-neon-gold)", fontSize: "0.85rem" }}>
                  Winner: {match.outcomes.find((o) => o.is_winner)?.name ?? "—"}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
