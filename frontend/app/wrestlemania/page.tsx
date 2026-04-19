"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  fetchWrestlemaniaCard,
  registerWMPlayer,
  submitWMPick,
  deleteWMPick,
  fetchWMLeaderboard,
  fetchWMCommentary,
} from "@/lib/api";
import type {
  WMCardResponse,
  WMMatch,
  WMOutcome,
  WMLeaderboardEntry,
  WMCommentaryEntry,
} from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import NameEntryModal from "@/components/wrestlemania/NameEntryModal";
import RetroHero from "@/components/wrestlemania/RetroHero";
import MatchCard from "@/components/wrestlemania/MatchCard";
import PickDrawer from "@/components/wrestlemania/PickDrawer";
import Leaderboard from "@/components/wrestlemania/Leaderboard";
import CommentaryBanner from "@/components/wrestlemania/CommentaryBanner";
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
  return (day === 0 || day === 6) && hour >= 18 && hour <= 23;
}

export default function WrestlemaniaPage() {
  return (
    <Suspense fallback={<div className="wrestlemania-theme" style={{ minHeight: "100vh" }} />}>
      <WrestlemaniaContent />
    </Suspense>
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com";

function WrestlemaniaContent() {
  usePageTracking({ pageType: "wrestlemania", pageTitle: "WrestleMania 42" });
  useScrollDepth({ pageType: "wrestlemania" });
  useEngagementTime({ pageType: "wrestlemania" });

  const searchParams = useSearchParams();
  const adminSecret = searchParams.get("secret") || undefined;

  const [card, setCard] = useState<WMCardResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<WMLeaderboardEntry[]>([]);
  const [banner, setBanner] = useState("");
  const [commentaryFeed, setCommentaryFeed] = useState<WMCommentaryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [storedPlayer, setStoredPlayer] = useState<StoredPlayer | null>(null);
  const [showNameModal, setShowNameModal] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [drawerState, setDrawerState] = useState<{
    match: WMMatch;
    outcome: WMOutcome;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lbPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const commentaryPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const loadCard = useCallback(async () => {
    try {
      const data = await fetchWrestlemaniaCard(storedPlayer?.player_token);
      setCard(data);
      setError(null);
      if (data.player && storedPlayer) {
        setStoredPlayer((prev) => (prev ? { ...prev } : null));
      }
    } catch (e) {
      setError("Failed to load card");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [storedPlayer]);

  const loadLeaderboard = useCallback(async () => {
    try {
      const data = await fetchWMLeaderboard();
      setLeaderboard(data.leaderboard);
    } catch (e) {
      console.error("Leaderboard fetch failed:", e);
    }
  }, []);

  const loadCommentary = useCallback(async () => {
    try {
      const data = await fetchWMCommentary();
      setBanner(data.banner);
      setCommentaryFeed(data.feed);
    } catch (e) {
      console.error("Commentary fetch failed:", e);
    }
  }, []);

  useEffect(() => {
    loadCard();
    loadLeaderboard();
    loadCommentary();

    const cardInterval = isShowtime() ? 10_000 : 30_000;
    pollRef.current = setInterval(loadCard, cardInterval);
    lbPollRef.current = setInterval(loadLeaderboard, 15_000);
    commentaryPollRef.current = setInterval(loadCommentary, isShowtime() ? 60_000 : 120_000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (lbPollRef.current) clearInterval(lbPollRef.current);
      if (commentaryPollRef.current) clearInterval(commentaryPollRef.current);
    };
  }, [loadCard, loadLeaderboard, loadCommentary]);

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
      const data = await fetchWrestlemaniaCard(player.player_token);
      setCard(data);
    } catch (e) {
      console.error("Registration failed:", e);
      alert("Registration failed. Try a different name.");
    } finally {
      setRegistering(false);
    }
  };

  const handleSubmitPick = async (matchId: number, outcomeId: number, stake: number) => {
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

  const handleResolve = async (matchId: number, outcomeId: number) => {
    if (!adminSecret) return;
    try {
      await fetch(`${API_URL}/api/wrestlemania/admin/resolve?secret=${encodeURIComponent(adminSecret)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_id: matchId, winner_outcome_id: outcomeId }),
      });
      await loadCard();
      await loadLeaderboard();
      await loadCommentary();
    } catch (e) {
      console.error("Resolve failed:", e);
    }
  };

  const handleUnresolve = async (matchId: number) => {
    if (!adminSecret) return;
    try {
      await fetch(`${API_URL}/api/wrestlemania/admin/unresolve?secret=${encodeURIComponent(adminSecret)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_id: matchId, winner_outcome_id: 0 }),
      });
      await loadCard();
      await loadLeaderboard();
      await loadCommentary();
    } catch (e) {
      console.error("Unresolve failed:", e);
    }
  };

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

      <RetroHero bankroll={bankroll} playerName={storedPlayer?.display_name} />

      {banner && <CommentaryBanner text={banner} />}

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
        <div className="wm-layout">
          {/* Main column: match cards */}
          <div className="wm-main-col">
            {nights.map((n) => (
              <div key={n.night}>
                <div className="wm-night-divider">
                  <span className="wm-night-divider-label">
                    Night {n.night} — {n.night === 1 ? "Saturday, April 19" : "Sunday, April 20"}
                  </span>
                </div>
                {n.matches.map((match) => (
                  <MatchCard key={match.id} match={match} onOutcomeClick={handleOutcomeClick} adminSecret={adminSecret} onResolve={handleResolve} onUnresolve={handleUnresolve} />
                ))}
              </div>
            ))}
          </div>

          {/* Sidebar: leaderboard + commentary (desktop) */}
          <div className="wm-sidebar">
            <Leaderboard
              entries={leaderboard}
              currentPlayerId={card?.player?.id}
              commentaryFeed={commentaryFeed}
            />
          </div>
        </div>
      )}

      {/* Mobile: leaderboard below cards (hidden on desktop via CSS) */}
      {card && (
        <div className="wm-mobile-leaderboard">
          <Leaderboard
            entries={leaderboard}
            currentPlayerId={card?.player?.id}
            commentaryFeed={commentaryFeed}
          />
        </div>
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
    </div>
  );
}
