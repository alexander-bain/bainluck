"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  fetchOscarsData,
  fetchOscarsPool,
  createOscarsPool,
  joinOscarsPool,
  submitOscarsPoolPicks,
  submitOscarsPoolBonusPicks,
  lockOscarsPool,
  revealOscarsWinner,
  revealOscarsBonus,
} from "@/lib/api";
import { CATEGORY_EMOJI, CEREMONY_ORDER, MAJOR_CATEGORIES, PERSON_CATEGORIES, NOMINEES_98TH } from "@/lib/oscarsData";
import { searchMovie, searchPerson, posterUrl, headshotUrl } from "@/lib/tmdb";
import type {
  OscarsResponse,
  OscarsCategory,
  OscarsPoolResponse,
  OscarsPoolMember,
  OscarsPoolBonusMarket,
} from "@/lib/types";

// ─── Constants ──────────────────────────────────────────────────────────────

const STORAGE_KEY_PREFIX = "bainluck_oscars_pool_";
const MAX_CONFIDENCE_PICKS = 3;
const GOLD = "#D4AF37";
const GOLD_DIM = "#B8962E";

// Category display names
const CATEGORY_NAMES: Record<string, string> = {
  best_picture: "Best Picture",
  best_director: "Best Director",
  best_actor: "Best Actor",
  best_actress: "Best Actress",
  best_supporting_actor: "Best Supporting Actor",
  best_supporting_actress: "Best Supporting Actress",
  best_original_screenplay: "Original Screenplay",
  best_adapted_screenplay: "Adapted Screenplay",
  best_animated_feature: "Animated Feature",
  best_international_feature: "International Feature",
  best_documentary_feature: "Documentary Feature",
  best_documentary_short: "Documentary Short",
  best_animated_short: "Animated Short",
  best_live_action_short: "Live Action Short",
  best_original_score: "Original Score",
  best_original_song: "Original Song",
  best_sound: "Sound",
  best_production_design: "Production Design",
  best_cinematography: "Cinematography",
  best_film_editing: "Film Editing",
  best_costume_design: "Costume Design",
  best_makeup_hairstyling: "Makeup & Hairstyling",
  best_visual_effects: "Visual Effects",
  best_casting: "Casting",
};

/** Build fallback OscarsResponse from hardcoded nominees when API returns empty */
function buildFallbackOscarsData(): OscarsResponse {
  const categories = Object.entries(NOMINEES_98TH).map(([key, nominees]) => ({
    key,
    name: CATEGORY_NAMES[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    ceremony_order: CEREMONY_ORDER.indexOf(key) + 1 || 99,
    is_major: MAJOR_CATEGORIES.has(key),
    market_ids: [],
    nominees: nominees.map((n, i) => ({
      name: n.name,
      probability: n.probability,
      american_odds: null,
      opening_probability: null,
      movement_24h: null,
      rank: i + 1,
      sources: {},
      is_winner: false,
      last_updated: null,
    })),
  }));
  categories.sort((a, b) => a.ceremony_order - b.ceremony_order);
  return {
    ceremony_date: "2026-03-15T00:00:00-07:00",
    ceremony_status: "post",
    categories,
    trivia: [],
    total_categories: categories.length,
    biggest_movers: [],
    film_nominations: [],
    llm_previews: {},
  };
}

// ─── Helper components ──────────────────────────────────────────────────────

function GoldButton({
  onClick,
  disabled,
  children,
  className = "",
}: {
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-6 py-3 rounded-lg font-bold text-black transition-all ${
        disabled
          ? "bg-zinc-600 text-zinc-400 cursor-not-allowed"
          : "bg-gradient-to-r from-[#D4AF37] to-[#F4D03F] hover:from-[#F4D03F] hover:to-[#D4AF37] shadow-lg hover:shadow-xl"
      } ${className}`}
    >
      {children}
    </button>
  );
}

function PointsBadge({ points, isCorrect }: { points: number | null; isCorrect: boolean | null }) {
  if (isCorrect === null) return null;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${
        isCorrect ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
      }`}
    >
      {isCorrect ? `+${points?.toFixed(1)}` : "0"}
    </span>
  );
}

function BoldnessMeter({ boldness }: { boldness: number }) {
  const label =
    boldness >= 80
      ? "Wildcard"
      : boldness >= 60
      ? "Bold"
      : boldness >= 40
      ? "Balanced"
      : "Playing it safe";
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <div className="w-16 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${boldness}%`,
            background: `linear-gradient(to right, #22c55e, ${GOLD}, #ef4444)`,
          }}
        />
      </div>
      <span>{label}</span>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function OscarsPoolPage() {
  // Analytics (must be called before any conditional returns)
  usePageTracking({ pageType: "oscars_pool", pageTitle: "Oscars Pool" });
  useScrollDepth({ pageType: "oscars_pool" });
  useEngagementTime({ pageType: "oscars_pool" });

  // State
  const [phase, setPhase] = useState<"loading" | "lobby" | "pool">("loading");
  const [poolCode, setPoolCode] = useState<string>("");
  const [memberToken, setMemberToken] = useState<string>("");
  const [poolData, setPoolData] = useState<OscarsPoolResponse | null>(null);
  const [oscarsData, setOscarsData] = useState<OscarsResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"picks" | "bonus" | "leaderboard">("picks");

  // Pick state
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [confidencePicks, setConfidencePicks] = useState<Set<string>>(new Set());
  const [bonusPicks, setBonusPicks] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<string>("");

  // TMDB image cache: key = "categoryKey_nomineeName" -> URL
  const [nomineeImages, setNomineeImages] = useState<Record<string, string>>({});

  // Lobby state
  const [lobbyMode, setLobbyMode] = useState<"choice" | "create" | "join">("choice");
  const [inputName, setInputName] = useState("");
  const [inputPoolName, setInputPoolName] = useState("");
  const [inputCode, setInputCode] = useState("");
  const [selectedEmoji, setSelectedEmoji] = useState("🎬");

  // Reveal state
  const [revealCategory, setRevealCategory] = useState<string>("");
  const [revealWinner, setRevealWinner] = useState<string>("");
  const [revealResult, setRevealResult] = useState<{
    scored_members: { display_name: string; avatar_emoji: string; picked: string; is_correct: boolean; points_earned: number; was_confidence_pick?: boolean; was_dark_horse?: boolean }[];
  } | null>(null);

  // ─── Load saved session ─────────────────────────────────────────────────

  useEffect(() => {
    // Check URL params first
    const params = new URLSearchParams(window.location.search);
    const codeParam = params.get("code");

    // Check localStorage for saved session
    const savedCode = codeParam || localStorage.getItem(`${STORAGE_KEY_PREFIX}code`);
    const savedToken = localStorage.getItem(`${STORAGE_KEY_PREFIX}token`);

    if (savedCode && savedToken) {
      setPoolCode(savedCode);
      setMemberToken(savedToken);
      setPhase("pool");
    } else if (codeParam) {
      setInputCode(codeParam);
      setLobbyMode("join");
      setPhase("lobby");
    } else {
      setPhase("lobby");
    }
  }, []);

  // ─── Fetch pool data + odds data ────────────────────────────────────────

  const loadPoolData = useCallback(async () => {
    if (!poolCode || !memberToken) return;
    try {
      const [pool, oscarsRaw] = await Promise.all([
        fetchOscarsPool(poolCode, memberToken),
        fetchOscarsData().catch(() => null),
      ]);
      setPoolData(pool);
      // Use API data if it has categories, otherwise use hardcoded fallback
      const oscars = (oscarsRaw && oscarsRaw.categories.length > 0) ? oscarsRaw : buildFallbackOscarsData();
      setOscarsData(oscars);

      // Initialize picks from saved data
      const currentMember = pool.members.find((m: OscarsPoolMember) => m.is_current_user);
      if (currentMember) {
        const savedPicks: Record<string, string> = {};
        const savedConfidence = new Set<string>();
        const savedBonus: Record<string, string> = {};
        for (const pick of currentMember.picks) {
          savedPicks[pick.category_key] = pick.nominee_name;
          if (pick.is_confidence_pick) savedConfidence.add(pick.category_key);
        }
        for (const pick of currentMember.bonus_picks) {
          savedBonus[pick.category_key] = pick.nominee_name;
        }
        setPicks(savedPicks);
        setConfidencePicks(savedConfidence);
        setBonusPicks(savedBonus);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load pool";
      // If pool not found (404), clear stale session and go back to lobby
      if (msg === "Not Found" || msg.includes("404")) {
        localStorage.removeItem(`${STORAGE_KEY_PREFIX}code`);
        localStorage.removeItem(`${STORAGE_KEY_PREFIX}token`);
        setPoolCode("");
        setMemberToken("");
        setPhase("lobby");
        return;
      }
      setError(msg);
    }
  }, [poolCode, memberToken]);

  useEffect(() => {
    if (phase === "pool") {
      loadPoolData();
      // Auto-refresh every 30 seconds during the show
      const interval = setInterval(loadPoolData, 30000);
      return () => clearInterval(interval);
    }
  }, [phase, loadPoolData]);

  // ─── TMDB image enrichment ───────────────────────────────────────────────

  useEffect(() => {
    if (!oscarsData) return;
    let cancelled = false;

    async function enrichImages() {
      const images: Record<string, string> = {};

      // Enrich major categories (all nominees) + craft categories (top 3)
      const enrichPromises: Promise<void>[] = [];

      for (const category of oscarsData!.categories) {
        const isMajor = MAJOR_CATEGORIES.has(category.key);
        const isPerson = PERSON_CATEGORIES.has(category.key);
        const nomineesToEnrich = isMajor ? category.nominees.slice(0, 8) : category.nominees.slice(0, 3);

        for (const nominee of nomineesToEnrich) {
          const imageKey = `${category.key}_${nominee.name}`;
          if (nomineeImages[imageKey]) continue; // Already have it

          enrichPromises.push(
            (async () => {
              try {
                if (isPerson) {
                  const person = await searchPerson(nominee.name);
                  const url = headshotUrl(person?.profile_path ?? null);
                  if (url && !cancelled) images[imageKey] = url;
                } else {
                  const movie = await searchMovie(nominee.name, 2025);
                  const url = posterUrl(movie?.poster_path ?? null);
                  if (url && !cancelled) images[imageKey] = url;
                }
              } catch {
                // Silently fail — image is optional
              }
            })()
          );
        }
      }

      // Run in parallel batches to avoid overwhelming TMDB
      await Promise.allSettled(enrichPromises);
      if (!cancelled && Object.keys(images).length > 0) {
        setNomineeImages((prev) => ({ ...prev, ...images }));
      }
    }

    enrichImages();
    return () => { cancelled = true; };
  }, [oscarsData]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Actions ────────────────────────────────────────────────────────────

  const handleCreate = async () => {
    if (!inputName.trim() || !inputPoolName.trim()) return;
    setError("");
    try {
      const result = await createOscarsPool(inputPoolName.trim(), inputName.trim(), selectedEmoji);
      localStorage.setItem(`${STORAGE_KEY_PREFIX}code`, result.pool_code);
      localStorage.setItem(`${STORAGE_KEY_PREFIX}token`, result.member_token);
      setPoolCode(result.pool_code);
      setMemberToken(result.member_token);
      setPhase("pool");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create pool");
    }
  };

  const handleJoin = async () => {
    if (!inputName.trim() || !inputCode.trim()) return;
    setError("");
    try {
      const result = await joinOscarsPool(inputCode.trim().toUpperCase(), inputName.trim(), selectedEmoji);
      localStorage.setItem(`${STORAGE_KEY_PREFIX}code`, result.pool_code);
      localStorage.setItem(`${STORAGE_KEY_PREFIX}token`, result.member_token);
      setPoolCode(result.pool_code);
      setMemberToken(result.member_token);
      setPhase("pool");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to join pool");
    }
  };

  const handleSavePicks = async () => {
    if (!poolCode || !memberToken) return;
    setSaving(true);
    setError("");
    try {
      const pickList = Object.entries(picks).map(([category_key, nominee_name]) => {
        const cat = oscarsData?.categories.find((c) => c.key === category_key);
        const nominee = cat?.nominees.find((n) => n.name === nominee_name);
        return {
          category_key,
          nominee_name,
          probability_at_pick: nominee?.probability ?? 0.5,
        };
      });
      await submitOscarsPoolPicks(poolCode, memberToken, pickList, Array.from(confidencePicks));
      setLastSaved(new Date().toLocaleTimeString());
      await loadPoolData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save picks");
    }
    setSaving(false);
  };

  const handleSaveBonusPicks = async () => {
    if (!poolCode || !memberToken) return;
    setSaving(true);
    setError("");
    try {
      const bonusList = Object.entries(bonusPicks).map(([bonus_key, selected_option]) => ({
        bonus_key,
        selected_option,
      }));
      await submitOscarsPoolBonusPicks(poolCode, memberToken, bonusList);
      setLastSaved(new Date().toLocaleTimeString());
      await loadPoolData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save bonus picks");
    }
    setSaving(false);
  };

  const handleLock = async () => {
    if (!poolCode || !memberToken) return;
    if (!confirm("Lock all picks? Everyone's picks will be revealed. This can't be undone!")) return;
    try {
      await lockOscarsPool(poolCode, memberToken);
      await loadPoolData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to lock picks");
    }
  };

  const handleReveal = async () => {
    if (!revealCategory || !revealWinner.trim()) return;
    try {
      const isBonus = revealCategory.startsWith("bonus_");
      let result;
      if (isBonus) {
        result = await revealOscarsBonus(poolCode, memberToken, revealCategory, revealWinner.trim());
      } else {
        result = await revealOscarsWinner(poolCode, memberToken, revealCategory, revealWinner.trim());
      }
      setRevealResult(result);
      setRevealCategory("");
      setRevealWinner("");
      await loadPoolData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reveal winner");
    }
  };

  const handleLeavePool = () => {
    if (!confirm("Leave this pool? You can rejoin with the pool code.")) return;
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}code`);
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}token`);
    setPoolCode("");
    setMemberToken("");
    setPoolData(null);
    setPhase("lobby");
  };

  // ─── Computed ───────────────────────────────────────────────────────────

  const isCreator = poolData?.created_by === poolData?.members.find((m) => m.is_current_user)?.display_name;
  const categoriesByOrder = useMemo(() => {
    if (!oscarsData) return [];
    return [...oscarsData.categories].sort(
      (a, b) => (CEREMONY_ORDER.indexOf(a.key) ?? 99) - (CEREMONY_ORDER.indexOf(b.key) ?? 99)
    );
  }, [oscarsData]);

  const totalPossiblePicks = categoriesByOrder.length;
  const picksCount = Object.keys(picks).length;
  const shareUrl = typeof window !== "undefined" ? `${window.location.origin}/oscars/pool?code=${poolCode}` : "";

  // ─── Render ─────────────────────────────────────────────────────────────

  if (phase === "loading") {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="text-zinc-400 animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  // ─── Lobby ──────────────────────────────────────────────────────────────

  if (phase === "lobby") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#1a1408] via-[#09090b] to-[#09090b]">
        <div className="max-w-md mx-auto px-4 py-12">
          {/* Header */}
          <div className="text-center mb-8">
            <Link href="/oscars" className="text-zinc-500 text-sm hover:text-zinc-400 mb-4 inline-block">
              ← Back to Oscars
            </Link>
            <h1 className="text-4xl font-bold mb-2">
              <span style={{ color: GOLD }}>Oscars Pool</span>
            </h1>
            <p className="text-zinc-400">Pick winners. Earn points. Bragging rights forever.</p>
            <p className="text-zinc-500 text-sm mt-2">
              Longshot picks earn more points. Choose 3 confidence picks for 1.5x bonus.
            </p>
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4 text-sm">
              {error}
            </div>
          )}

          {lobbyMode === "choice" && (
            <div className="space-y-4">
              <GoldButton onClick={() => setLobbyMode("create")} className="w-full text-lg">
                Create a Pool
              </GoldButton>
              <button
                onClick={() => setLobbyMode("join")}
                className="w-full px-6 py-3 rounded-lg font-bold border-2 text-white transition-all hover:bg-white/5"
                style={{ borderColor: GOLD, color: GOLD }}
              >
                Join a Pool
              </button>
            </div>
          )}

          {lobbyMode === "create" && (
            <div className="space-y-4">
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Pool Name</label>
                <input
                  type="text"
                  value={inputPoolName}
                  onChange={(e) => setInputPoolName(e.target.value)}
                  placeholder="Bain Family Oscars 2026"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 text-white placeholder-zinc-500 focus:outline-none focus:border-[#D4AF37]"
                  maxLength={50}
                />
              </div>
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Your Name</label>
                <input
                  type="text"
                  value={inputName}
                  onChange={(e) => setInputName(e.target.value)}
                  placeholder="Alexander"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 text-white placeholder-zinc-500 focus:outline-none focus:border-[#D4AF37]"
                  maxLength={30}
                />
              </div>
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Pick your avatar</label>
                <div className="flex flex-wrap gap-2">
                  {["🎬", "🍿", "⭐", "🎭", "🏆", "🎪", "🎯", "🎲", "👑", "🎸", "🌟", "🎩", "💎", "🦋", "🔮"].map((e) => (
                    <button
                      key={e}
                      onClick={() => setSelectedEmoji(e)}
                      className={`w-10 h-10 rounded-lg text-xl flex items-center justify-center transition-all ${
                        selectedEmoji === e ? "bg-[#D4AF37]/20 ring-2 ring-[#D4AF37] scale-110" : "bg-zinc-800 hover:bg-zinc-700"
                      }`}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
              <GoldButton onClick={handleCreate} disabled={!inputName.trim() || !inputPoolName.trim()} className="w-full">
                Create Pool
              </GoldButton>
              <button onClick={() => setLobbyMode("choice")} className="w-full text-zinc-500 text-sm hover:text-zinc-400">
                ← Back
              </button>
            </div>
          )}

          {lobbyMode === "join" && (
            <div className="space-y-4">
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Pool Code</label>
                <input
                  type="text"
                  value={inputCode}
                  onChange={(e) => setInputCode(e.target.value.toUpperCase())}
                  placeholder="ABC123"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 text-white placeholder-zinc-500 focus:outline-none focus:border-[#D4AF37] text-center text-2xl tracking-widest font-mono"
                  maxLength={6}
                />
              </div>
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Your Name</label>
                <input
                  type="text"
                  value={inputName}
                  onChange={(e) => setInputName(e.target.value)}
                  placeholder="Your name"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 text-white placeholder-zinc-500 focus:outline-none focus:border-[#D4AF37]"
                  maxLength={30}
                />
              </div>
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Pick your avatar</label>
                <div className="flex flex-wrap gap-2">
                  {["🎬", "🍿", "⭐", "🎭", "🏆", "🎪", "🎯", "🎲", "👑", "🎸", "🌟", "🎩", "💎", "🦋", "🔮"].map((e) => (
                    <button
                      key={e}
                      onClick={() => setSelectedEmoji(e)}
                      className={`w-10 h-10 rounded-lg text-xl flex items-center justify-center transition-all ${
                        selectedEmoji === e ? "bg-[#D4AF37]/20 ring-2 ring-[#D4AF37] scale-110" : "bg-zinc-800 hover:bg-zinc-700"
                      }`}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
              <GoldButton onClick={handleJoin} disabled={!inputName.trim() || !inputCode.trim()} className="w-full">
                Join Pool
              </GoldButton>
              <button onClick={() => setLobbyMode("choice")} className="w-full text-zinc-500 text-sm hover:text-zinc-400">
                ← Back
              </button>
            </div>
          )}

          {/* How scoring works */}
          <div className="mt-8 bg-zinc-900/60 border border-zinc-800 rounded-xl p-5">
            <h3 className="font-bold text-white mb-3" style={{ color: GOLD }}>
              How Scoring Works
            </h3>
            <div className="space-y-2 text-sm text-zinc-400">
              <p>
                <span className="text-white font-medium">Odds-adjusted points:</span> Picking a longshot that wins earns more points.
                A 10% underdog = 10 points. A 50% favorite = 2 points.
              </p>
              <p>
                <span className="text-white font-medium">Confidence picks (3):</span> Mark up to 3 categories as your most confident for a 1.5x multiplier.
              </p>
              <p>
                <span className="text-white font-medium">Dark horse bonus:</span> Pick someone with {"<"}15% odds and they win? 2x points on top!
              </p>
              <p>
                <span className="text-white font-medium">Bonus questions:</span> Fun side bets about the ceremony itself for extra points.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ─── Pool View ──────────────────────────────────────────────────────────

  if (!poolData || !oscarsData) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="text-zinc-400 animate-pulse text-lg">Loading pool...</div>
      </div>
    );
  }

  const currentMember = poolData.members.find((m) => m.is_current_user);

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#1a1408] via-[#09090b] to-[#09090b]">
      <div className="max-w-2xl mx-auto px-4 py-6">
        {/* Pool Header */}
        <div className="text-center mb-6">
          <Link href="/oscars" className="text-zinc-500 text-sm hover:text-zinc-400 mb-2 inline-block">
            ← Oscars
          </Link>
          <h1 className="text-2xl font-bold text-white">{poolData.pool_name}</h1>
          <div className="flex items-center justify-center gap-3 mt-2">
            <span className="text-zinc-400 text-sm">
              {poolData.member_count} player{poolData.member_count !== 1 ? "s" : ""}
            </span>
            <span className="text-zinc-600">|</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(shareUrl);
                alert("Pool link copied!");
              }}
              className="text-sm hover:text-white transition-colors"
              style={{ color: GOLD }}
            >
              Share: {poolData.pool_code}
            </button>
          </div>
          {poolData.picks_locked && (
            <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 bg-red-500/10 border border-red-500/30 rounded-full text-red-400 text-xs font-bold">
              PICKS LOCKED
            </div>
          )}
          {/* Members strip */}
          <div className="flex items-center justify-center gap-2 mt-3">
            {poolData.members.map((m) => (
              <div
                key={m.id}
                className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                  m.is_current_user ? "bg-[#D4AF37]/20 border border-[#D4AF37]/40" : "bg-zinc-800"
                }`}
                title={m.display_name}
              >
                <span>{m.avatar_emoji}</span>
                <span className="text-zinc-300 max-w-[60px] truncate">{m.display_name}</span>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4 text-sm">
            {error}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-4 bg-zinc-900 rounded-lg p-1">
          {(["picks", "bonus", "leaderboard"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all ${
                activeTab === tab
                  ? "bg-[#D4AF37]/20 text-[#D4AF37]"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab === "picks" && `Awards (${picksCount}/${totalPossiblePicks})`}
              {tab === "bonus" && `Bonus (${Object.keys(bonusPicks).length}/${poolData.bonus_markets.length})`}
              {tab === "leaderboard" && `Leaderboard`}
            </button>
          ))}
        </div>

        {/* ─── Picks Tab ─────────────────────────────────────────────── */}
        {activeTab === "picks" && (
          <div className="space-y-3">
            {/* Progress + save */}
            {!poolData.picks_locked && (
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-zinc-400">
                  <span className="font-medium text-white">{confidencePicks.size}</span>/{MAX_CONFIDENCE_PICKS} confidence picks used
                </div>
                <div className="flex items-center gap-2">
                  {lastSaved && <span className="text-xs text-zinc-500">Saved {lastSaved}</span>}
                  <GoldButton onClick={handleSavePicks} disabled={saving || picksCount === 0} className="!py-2 !px-4 text-sm">
                    {saving ? "Saving..." : "Save Picks"}
                  </GoldButton>
                </div>
              </div>
            )}

            {/* Category cards */}
            {categoriesByOrder.map((category) => (
              <CategoryPickCard
                key={category.key}
                category={category}
                selectedNominee={picks[category.key]}
                isConfidencePick={confidencePicks.has(category.key)}
                onSelect={(nominee) => {
                  setPicks((prev) => ({ ...prev, [category.key]: nominee }));
                }}
                onToggleConfidence={() => {
                  setConfidencePicks((prev) => {
                    const next = new Set(prev);
                    if (next.has(category.key)) {
                      next.delete(category.key);
                    } else if (next.size < MAX_CONFIDENCE_PICKS) {
                      next.add(category.key);
                    }
                    return next;
                  });
                }}
                canAddConfidence={confidencePicks.size < MAX_CONFIDENCE_PICKS}
                locked={poolData.picks_locked}
                result={poolData.results[category.key]}
                ceremonyOrder={CEREMONY_ORDER.indexOf(category.key) + 1}
                nomineeImages={nomineeImages}
              />
            ))}
          </div>
        )}

        {/* ─── Bonus Tab ─────────────────────────────────────────────── */}
        {activeTab === "bonus" && (
          <div className="space-y-3">
            {!poolData.picks_locked && (
              <div className="flex justify-end mb-2">
                <GoldButton
                  onClick={handleSaveBonusPicks}
                  disabled={saving || Object.keys(bonusPicks).length === 0}
                  className="!py-2 !px-4 text-sm"
                >
                  {saving ? "Saving..." : "Save Bonus Picks"}
                </GoldButton>
              </div>
            )}

            {poolData.bonus_markets.map((bonus) => (
              <BonusMarketCard
                key={bonus.key}
                bonus={bonus}
                selectedOption={bonusPicks[bonus.key]}
                onSelect={(option) => setBonusPicks((prev) => ({ ...prev, [bonus.key]: option }))}
                locked={poolData.picks_locked}
                result={poolData.results[bonus.key]}
              />
            ))}
          </div>
        )}

        {/* ─── Leaderboard Tab ───────────────────────────────────────── */}
        {activeTab === "leaderboard" && (
          <div className="space-y-4">
            {/* Scoreboard */}
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-sm font-bold" style={{ color: GOLD }}>
                  Leaderboard
                </span>
                <span className="text-xs text-zinc-500">
                  {poolData.categories_revealed}/{poolData.total_categories} categories +{" "}
                  {poolData.bonus_revealed}/{poolData.bonus_markets.length} bonus
                </span>
              </div>

              {poolData.leaderboard.map((member, idx) => (
                <div
                  key={member.id}
                  className={`px-4 py-3 flex items-center gap-3 ${
                    idx < poolData.leaderboard.length - 1 ? "border-b border-zinc-800/50" : ""
                  } ${member.is_current_user ? "bg-[#D4AF37]/5" : ""}`}
                >
                  {/* Rank */}
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                      idx === 0
                        ? "bg-[#D4AF37]/20 text-[#D4AF37]"
                        : idx === 1
                        ? "bg-zinc-400/20 text-zinc-300"
                        : idx === 2
                        ? "bg-amber-700/20 text-amber-600"
                        : "bg-zinc-800 text-zinc-500"
                    }`}
                  >
                    {idx + 1}
                  </div>

                  {/* Name */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-lg">{member.avatar_emoji}</span>
                      <span className={`font-medium truncate ${member.is_current_user ? "text-[#D4AF37]" : "text-white"}`}>
                        {member.display_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-zinc-500">
                        {member.correct_count} correct
                      </span>
                      <BoldnessMeter boldness={member.boldness} />
                    </div>
                  </div>

                  {/* Points */}
                  <div className="text-right">
                    <div className="text-xl font-bold" style={{ color: member.total_points > 0 ? GOLD : "#71717a" }}>
                      {member.total_points.toFixed(1)}
                    </div>
                    <div className="text-xs text-zinc-500">pts</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Pick comparison (only after lock) */}
            {poolData.picks_locked && (
              <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4">
                <h3 className="text-sm font-bold mb-3" style={{ color: GOLD }}>
                  Pick Comparison
                </h3>
                <div className="space-y-4">
                  {categoriesByOrder.map((category) => {
                    const result = poolData.results[category.key];
                    return (
                      <div key={category.key} className="border-b border-zinc-800/50 pb-3 last:border-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-sm">{CATEGORY_EMOJI[category.key] || "🎬"}</span>
                          <span className="text-xs text-zinc-400">{CATEGORY_NAMES[category.key] || category.key}</span>
                          {result && (
                            <span className="ml-auto text-xs font-bold text-green-400">
                              Winner: {result}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {poolData.members.map((member) => {
                            const pick = member.picks.find((p) => p.category_key === category.key);
                            if (!pick) return null;
                            const isCorrect = result ? pick.is_correct : null;
                            return (
                              <div
                                key={member.id}
                                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
                                  isCorrect === true
                                    ? "bg-green-500/20 text-green-400"
                                    : isCorrect === false
                                    ? "bg-red-500/10 text-red-400/60"
                                    : "bg-zinc-800 text-zinc-300"
                                }`}
                                title={`${member.display_name}: ${pick.nominee_name}${pick.is_confidence_pick ? " (confidence)" : ""}`}
                              >
                                <span>{member.avatar_emoji}</span>
                                <span className="max-w-[80px] truncate">{pick.nominee_name}</span>
                                {pick.is_confidence_pick && <span style={{ color: GOLD }}>★</span>}
                                <PointsBadge points={pick.points_earned} isCorrect={isCorrect} />
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── Creator Controls ───────────────────────────────────────── */}
        {isCreator && (
          <div className="mt-6 bg-zinc-900/80 border border-zinc-800 rounded-xl p-4">
            <h3 className="text-sm font-bold text-zinc-300 mb-3">Pool Admin</h3>

            {!poolData.picks_locked && (
              <GoldButton onClick={handleLock} className="w-full mb-3 text-sm">
                Lock All Picks (Start the Show!)
              </GoldButton>
            )}

            {poolData.picks_locked && (
              <div className="space-y-3">
                <p className="text-xs text-zinc-400">
                  As each winner is announced, select the category and type the winner name:
                </p>
                <select
                  value={revealCategory}
                  onChange={(e) => {
                    setRevealCategory(e.target.value);
                    setRevealWinner("");
                    setRevealResult(null);
                  }}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#D4AF37]"
                >
                  <option value="">Select category...</option>
                  <optgroup label="Award Categories">
                    {categoriesByOrder.map((cat) => (
                      <option key={cat.key} value={cat.key} disabled={!!poolData.results[cat.key]}>
                        {poolData.results[cat.key] ? "✓ " : ""}
                        {CATEGORY_NAMES[cat.key] || cat.key}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Bonus Questions">
                    {poolData.bonus_markets.map((b) => (
                      <option key={b.key} value={b.key} disabled={!!poolData.results[b.key]}>
                        {poolData.results[b.key] ? "✓ " : ""}
                        {b.emoji} {b.question}
                      </option>
                    ))}
                  </optgroup>
                </select>

                {revealCategory && !revealCategory.startsWith("bonus_") && (
                  <div>
                    <label className="text-xs text-zinc-400 block mb-1">Winner:</label>
                    {/* Show nominees as buttons for easy selection */}
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {oscarsData?.categories
                        .find((c) => c.key === revealCategory)
                        ?.nominees.slice(0, 10)
                        .map((n) => (
                          <button
                            key={n.name}
                            onClick={() => setRevealWinner(n.name)}
                            className={`px-2 py-1 rounded text-xs transition-all ${
                              revealWinner === n.name
                                ? "bg-green-500/20 text-green-400 ring-1 ring-green-500"
                                : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                            }`}
                          >
                            {n.name}
                          </button>
                        ))}
                    </div>
                    <input
                      type="text"
                      value={revealWinner}
                      onChange={(e) => setRevealWinner(e.target.value)}
                      placeholder="Or type winner name..."
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#D4AF37]"
                    />
                  </div>
                )}

                {revealCategory && revealCategory.startsWith("bonus_") && (
                  <div>
                    <label className="text-xs text-zinc-400 block mb-1">Correct answer:</label>
                    <div className="flex flex-wrap gap-1.5">
                      {poolData.bonus_markets
                        .find((b) => b.key === revealCategory)
                        ?.options.map((opt) => (
                          <button
                            key={opt}
                            onClick={() => setRevealWinner(opt)}
                            className={`px-2 py-1 rounded text-xs transition-all ${
                              revealWinner === opt
                                ? "bg-green-500/20 text-green-400 ring-1 ring-green-500"
                                : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                            }`}
                          >
                            {opt}
                          </button>
                        ))}
                    </div>
                  </div>
                )}

                {revealWinner && (
                  <GoldButton onClick={handleReveal} className="w-full text-sm">
                    Reveal Winner
                  </GoldButton>
                )}

                {/* Reveal animation */}
                {revealResult && (
                  <div className="bg-zinc-800/50 rounded-lg p-3 mt-2 space-y-1.5">
                    {revealResult.scored_members.map((sm) => (
                      <div key={sm.display_name} className="flex items-center gap-2 text-sm">
                        <span>{sm.avatar_emoji}</span>
                        <span className="text-zinc-300">{sm.display_name}</span>
                        <span className="text-zinc-500">picked</span>
                        <span className={sm.is_correct ? "text-green-400 font-medium" : "text-red-400/60"}>
                          {sm.picked}
                        </span>
                        {sm.is_correct && (
                          <span className="ml-auto text-green-400 font-bold">
                            +{sm.points_earned.toFixed(1)}
                            {sm.was_confidence_pick && <span style={{ color: GOLD }}> ★</span>}
                            {sm.was_dark_horse && <span className="text-purple-400"> 🦄</span>}
                          </span>
                        )}
                        {!sm.is_correct && (
                          <span className="ml-auto text-red-400/40 text-xs">miss</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <button onClick={handleLeavePool} className="w-full mt-3 text-zinc-500 text-xs hover:text-red-400 transition-colors">
              Leave Pool
            </button>
          </div>
        )}

        {/* Non-creator leave button */}
        {!isCreator && (
          <div className="mt-6 text-center">
            <button onClick={handleLeavePool} className="text-zinc-500 text-xs hover:text-red-400 transition-colors">
              Leave Pool
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Category Pick Card ──────────────────────────────────────────────────────

function CategoryPickCard({
  category,
  selectedNominee,
  isConfidencePick,
  onSelect,
  onToggleConfidence,
  canAddConfidence,
  locked,
  result,
  ceremonyOrder,
  nomineeImages,
}: {
  category: OscarsCategory;
  selectedNominee?: string;
  isConfidencePick: boolean;
  onSelect: (nominee: string) => void;
  onToggleConfidence: () => void;
  canAddConfidence: boolean;
  locked: boolean;
  result?: string;
  ceremonyOrder: number;
  nomineeImages: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const isMajor = MAJOR_CATEGORIES.has(category.key);
  const emoji = CATEGORY_EMOJI[category.key] || "🎬";
  const hasResult = !!result;
  const isCorrect = hasResult && selectedNominee && result.toLowerCase() === selectedNominee.toLowerCase();

  // For major categories or if no pick yet, show expanded by default
  const showNominees = expanded || isMajor || (!locked && !selectedNominee);

  return (
    <div
      className={`bg-zinc-900/80 border rounded-xl overflow-hidden transition-all ${
        hasResult
          ? isCorrect
            ? "border-green-500/40"
            : "border-red-500/20"
          : isConfidencePick
          ? "border-[#D4AF37]/40"
          : "border-zinc-800"
      }`}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center gap-2 text-left"
      >
        <span className="text-zinc-500 text-xs font-mono w-5">#{ceremonyOrder}</span>
        <span className="text-base">{emoji}</span>
        <span className={`text-sm font-medium flex-1 ${isMajor ? "text-white" : "text-zinc-300"}`}>
          {CATEGORY_NAMES[category.key] || category.key}
        </span>

        {selectedNominee && !showNominees && (
          <span className="text-xs text-zinc-400 max-w-[120px] truncate">{selectedNominee}</span>
        )}
        {isConfidencePick && <span title="Confidence pick (1.5x)" style={{ color: GOLD }}>★</span>}
        {hasResult && (
          <span className={`text-xs font-bold ${isCorrect ? "text-green-400" : "text-red-400/60"}`}>
            {isCorrect ? "✓" : "✗"}
          </span>
        )}
        <span className="text-zinc-600 text-xs">{showNominees ? "▲" : "▼"}</span>
      </button>

      {/* Nominees */}
      {showNominees && (
        <div className="px-4 pb-3 space-y-1">
          {hasResult && (
            <div className="text-xs text-green-400 mb-2 font-medium">
              Winner: {result}
            </div>
          )}

          {category.nominees.slice(0, 10).map((nominee) => {
            const isSelected = selectedNominee === nominee.name;
            const isWinner = hasResult && result.toLowerCase() === nominee.name.toLowerCase();
            const pct = (nominee.probability * 100).toFixed(0);
            const imageKey = `${category.key}_${nominee.name}`;
            const imageUrl = nomineeImages[imageKey];

            return (
              <button
                key={nominee.name}
                onClick={() => !locked && onSelect(nominee.name)}
                disabled={locked}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                  isWinner
                    ? "bg-green-500/15 text-green-400"
                    : isSelected
                    ? "bg-[#D4AF37]/15 text-white ring-1 ring-[#D4AF37]/50"
                    : locked
                    ? "bg-zinc-800/50 text-zinc-500"
                    : "bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50"
                }`}
              >
                {/* Radio dot */}
                <div
                  className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                    isSelected ? "border-[#D4AF37]" : "border-zinc-600"
                  }`}
                >
                  {isSelected && <div className="w-2 h-2 rounded-full bg-[#D4AF37]" />}
                </div>

                {/* TMDB image (headshot or poster) */}
                {imageUrl ? (
                  <img
                    src={imageUrl}
                    alt={nominee.name}
                    className="w-8 h-8 rounded-full object-cover flex-shrink-0"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center flex-shrink-0 text-xs text-zinc-400">
                    {nominee.name.charAt(0)}
                  </div>
                )}

                <span className="flex-1 text-left truncate">{nominee.name}</span>

                {/* Probability bar */}
                <div className="w-20 flex items-center gap-1.5">
                  <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(nominee.probability * 100, 100)}%`,
                        backgroundColor: nominee.probability > 0.5 ? "#22c55e" : GOLD_DIM,
                      }}
                    />
                  </div>
                  <span className="text-[10px] text-zinc-500 w-7 text-right">{pct}%</span>
                </div>
              </button>
            );
          })}

          {/* Confidence toggle */}
          {!locked && selectedNominee && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleConfidence();
              }}
              disabled={!isConfidencePick && !canAddConfidence}
              className={`w-full mt-2 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isConfidencePick
                  ? "bg-[#D4AF37]/15 text-[#D4AF37] border border-[#D4AF37]/30"
                  : canAddConfidence
                  ? "bg-zinc-800 text-zinc-400 hover:text-[#D4AF37] border border-zinc-700"
                  : "bg-zinc-800/50 text-zinc-600 border border-zinc-800 cursor-not-allowed"
              }`}
            >
              {isConfidencePick ? "★ Confidence Pick (1.5x) — click to remove" : "★ Make this a confidence pick (1.5x)"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Bonus Market Card ───────────────────────────────────────────────────────

function BonusMarketCard({
  bonus,
  selectedOption,
  onSelect,
  locked,
  result,
}: {
  bonus: OscarsPoolBonusMarket;
  selectedOption?: string;
  onSelect: (option: string) => void;
  locked: boolean;
  result?: string;
}) {
  const hasResult = !!result;
  const isCorrect = hasResult && selectedOption?.toLowerCase() === result.toLowerCase();

  return (
    <div
      className={`bg-zinc-900/80 border rounded-xl p-4 transition-all ${
        hasResult
          ? isCorrect
            ? "border-green-500/40"
            : "border-red-500/20"
          : "border-zinc-800"
      }`}
    >
      <div className="flex items-start gap-2 mb-3">
        <span className="text-xl">{bonus.emoji}</span>
        <div className="flex-1">
          <p className="text-sm font-medium text-white">{bonus.question}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">{bonus.points_value} points if correct</p>
        </div>
        {hasResult && (
          <span className={`text-xs font-bold ${isCorrect ? "text-green-400" : "text-red-400/60"}`}>
            {isCorrect ? `+${bonus.points_value}` : "0"}
          </span>
        )}
      </div>

      {hasResult && (
        <div className="text-xs text-green-400 mb-2 font-medium">Answer: {result}</div>
      )}

      <div className="grid grid-cols-2 gap-1.5">
        {bonus.options.map((option) => {
          const isSelected = selectedOption === option;
          const isAnswer = hasResult && result === option;

          return (
            <button
              key={option}
              onClick={() => !locked && onSelect(option)}
              disabled={locked}
              className={`px-3 py-2 rounded-lg text-xs text-left transition-all ${
                isAnswer
                  ? "bg-green-500/15 text-green-400 font-medium"
                  : isSelected
                  ? "bg-[#D4AF37]/15 text-white ring-1 ring-[#D4AF37]/50"
                  : locked
                  ? "bg-zinc-800/50 text-zinc-500"
                  : "bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50"
              }`}
            >
              {isSelected && !hasResult && <span style={{ color: GOLD }}>● </span>}
              {isAnswer && <span className="text-green-400">✓ </span>}
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}
