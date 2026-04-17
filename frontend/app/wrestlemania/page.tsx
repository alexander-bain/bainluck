"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  fetchWrestlemaniaCard,
  registerWMPlayer,
  submitWMPick,
  deleteWMPick,
  fetchWMLeaderboard,
} from "@/lib/api";
import type {
  WMCardResponse,
  WMMatch,
  WMOutcome,
  WMLeaderboardEntry,
} from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import NameEntryModal from "@/components/wrestlemania/NameEntryModal";
import RetroHero from "@/components/wrestlemania/RetroHero";
import MatchCard from "@/components/wrestlemania/MatchCard";
import PickDrawer from "@/components/wrestlemania/PickDrawer";
import Leaderboard from "@/components/wrestlemania/Leaderboard";
import "./wrestlemania.css";

const WM_STORAGE_KEY = "wm42_player";

interface StoredPlayer {
  player_id: number;
  player_token: string;
  display_name: string;
}

function isShowtime(): boolean {
  const now = new Date();
  const day = now.getDay();
  const hour = now.getHours();
  // Sat/Sun 6pm-11pm ET (approximate with local time)
  return (day === 0 || day === 6) && hour >= 18 && hour <= 23;
}

export default function WrestlemaniaPage() {
  usePageTracking({ pageType: "wrestlemania", pageTitle: "WrestleMania 42" });
  useScrollDepth({ pageType: "wrestlemania" });
  useEngagementTime({ pageType: "wrestlemania" });

  const [card, setCard] = useState<WMCardResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<WMLeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [storedPlayer, setStoredPlayer] = useState<StoredPlayer | null>(null);
  const [showNameModal, setShowNameModal] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [activeNight, setActiveNight] = useState(1);
  const [drawerState, setDrawerState] = useState<{
    match: WMMatch;
    outcome: WMOutcome;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lbPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load stored player on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(WM_STORAGE_KEY);
      if (stored) {
        setStoredPlayer(JSON.parse(stored));
      } else {
        setShowNameModal(true);
      }
    } catch {
      setShowNameModal(true);
    }
  }, []);

  // Fetch card data
  const loadCard = useCallback(async () => {
    try {
      const data = await fetchWrestlemaniaCard(storedPlayer?.player_token);
      setCard(data);
      setError(null);

      // If we have a stored player, update bankroll from server
      if (data.player && storedPlayer) {
        setStoredPlayer((prev) =>
          prev ? { ...prev } : null
        );
      }
    } catch (e) {
      setError("Failed to load card");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [storedPlayer]);

  // Fetch leaderboard
  const loadLeaderboard = useCallback(async () => {
    try {
      const data = await fetchWMLeaderboard();
      setLeaderboard(data.leaderboard);
    } catch (e) {
      console.error("Leaderboard fetch failed:", e);
    }
  }, []);

  // Initial load + polling
  useEffect(() => {
    loadCard();
    loadLeaderboard();

    const cardInterval = isShowtime() ? 10_000 : 30_000;
    pollRef.current = setInterval(loadCard, cardInterval);
    lbPollRef.current = setInterval(loadLeaderboard, 15_000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (lbPollRef.current) clearInterval(lbPollRef.current);
    };
  }, [loadCard, loadLeaderboard]);

  // Register player
  const handleRegister = async (name: string) => {
    setRegistering(true);
    try {
      const player = await registerWMPlayer(name);
      const stored: StoredPlayer = {
        player_id: player.id,
        player_token: player.player_token,
        display_name: player.display_name,
      };
      localStorage.setItem(WM_STORAGE_KEY, JSON.stringify(stored));
      setStoredPlayer(stored);
      setShowNameModal(false);
      // Reload card with player token
      const data = await fetchWrestlemaniaCard(player.player_token);
      setCard(data);
    } catch (e) {
      console.error("Registration failed:", e);
      alert("Registration failed. Try a different name.");
    } finally {
      setRegistering(false);
    }
  };

  // Submit pick
  const handleSubmitPick = async (
    matchId: number,
    outcomeId: number,
    stake: number
  ) => {
    if (!storedPlayer) return;
    setSubmitting(true);
    try {
      await submitWMPick(storedPlayer.player_token, matchId, outcomeId, stake);
      setDrawerState(null);
      await loadCard();
      await loadLeaderboard();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to place pick";
      alert(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Delete pick
  const handleDeletePick = async (pickId: number) => {
    if (!storedPlayer) return;
    try {
      await deleteWMPick(storedPlayer.player_token, pickId);
      setDrawerState(null);
      await loadCard();
      await loadLeaderboard();
    } catch (e) {
      console.error("Delete pick failed:", e);
    }
  };

  // Open drawer
  const handleOutcomeClick = (match: WMMatch, outcome: WMOutcome) => {
    if (!storedPlayer) {
      setShowNameModal(true);
      return;
    }
    if (match.status !== "open") return;
    setDrawerState({ match, outcome });
  };

  const bankroll = card?.player?.bankroll ?? 1_000_000;
  const nights = card?.nights ?? [];

  return (
    <div className="wrestlemania-theme">
      {showNameModal && (
        <NameEntryModal onSubmit={handleRegister} loading={registering} />
      )}

      <RetroHero
        bankroll={bankroll}
        playerName={storedPlayer?.display_name}
      />

      {error && (
        <div style={{ textAlign: "center", padding: "2rem", color: "var(--wm-neon-pink)" }}>
          {error}
        </div>
      )}

      {loading && !card && (
        <div style={{ textAlign: "center", padding: "2rem", color: "var(--wm-text-muted)" }}>
          Loading card...
        </div>
      )}

      {card && (
        <>
          <div className="wm-night-tabs">
            {nights.map((n) => (
              <button
                key={n.night}
                className={`wm-night-tab ${activeNight === n.night ? "active" : ""}`}
                onClick={() => setActiveNight(n.night)}
              >
                Night {n.night}
                <span style={{ fontSize: "0.7rem", display: "block", color: "var(--wm-text-muted)" }}>
                  {n.night === 1 ? "Sat Apr 19" : "Sun Apr 20"}
                </span>
              </button>
            ))}
          </div>

          <div className="wm-content">
            {nights
              .find((n) => n.night === activeNight)
              ?.matches.map((match) => (
                <MatchCard
                  key={match.id}
                  match={match}
                  onOutcomeClick={handleOutcomeClick}
                />
              ))}
          </div>
        </>
      )}

      {drawerState && (
        <PickDrawer
          match={drawerState.match}
          outcome={drawerState.outcome}
          bankroll={bankroll}
          onSubmit={handleSubmitPick}
          onDelete={handleDeletePick}
          onClose={() => setDrawerState(null)}
          submitting={submitting}
        />
      )}

      <Leaderboard
        entries={leaderboard}
        currentPlayerId={card?.player?.id}
      />
    </div>
  );
}
