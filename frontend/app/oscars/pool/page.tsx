"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { CATEGORY_EMOJI, CEREMONY_ORDER, MAJOR_CATEGORIES, PERSON_CATEGORIES, NOMINEES_98TH } from "@/lib/oscarsData";
import { searchMovie, searchPerson, posterUrl, headshotUrl } from "@/lib/tmdb";

// ─── Constants ──────────────────────────────────────────────────────────────

const STORAGE_KEY = "bainluck_oscars_pool_v2";
const MAX_CONFIDENCE_PICKS = 3;
const GOLD = "#D4AF37";
const GOLD_DIM = "#B8962E";

const AVATAR_EMOJIS = ["🎬", "🍿", "⭐", "🎭", "🏆", "🎪", "🎯", "🎲", "👑", "🎸", "🌟", "🎩", "💎", "🦋", "🔮"];

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

// ─── Types ──────────────────────────────────────────────────────────────────

interface PlayerData {
  name: string;
  avatar: string;
  picks: Record<string, string>;        // category_key -> nominee_name
  confidencePicks: string[];             // category_keys
  timestamp: number;
}

interface PoolData {
  poolName: string;
  players: PlayerData[];
  results: Record<string, string>;       // category_key -> winner_name (for reveal)
  createdAt: number;
}

interface NomineeInfo {
  name: string;
  probability: number;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function loadPool(): PoolData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function savePool(pool: PoolData) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pool));
}

function computeBoldness(picks: Record<string, string>): number {
  const probs: number[] = [];
  for (const [catKey, nomName] of Object.entries(picks)) {
    const nominees = NOMINEES_98TH[catKey];
    if (!nominees) continue;
    const nom = nominees.find(n => n.name === nomName);
    if (nom) probs.push(nom.probability);
  }
  if (probs.length === 0) return 0;
  const avgUnderdog = probs.reduce((sum, p) => sum + (1 - p), 0) / probs.length;
  return Math.round(avgUnderdog * 100);
}

function computePoints(picks: Record<string, string>, confidencePicks: string[], results: Record<string, string>): { total: number; correct: number } {
  let total = 0;
  let correct = 0;
  for (const [catKey, winner] of Object.entries(results)) {
    const pick = picks[catKey];
    if (pick && pick.toLowerCase() === winner.toLowerCase()) {
      correct++;
      const nominees = NOMINEES_98TH[catKey];
      const nom = nominees?.find(n => n.name === pick);
      const prob = nom?.probability ?? 0.5;
      let pts = prob > 0 ? 1 / prob : 1;
      if (confidencePicks.includes(catKey)) pts *= 1.5;
      total += pts;
    }
  }
  return { total: Math.round(total * 10) / 10, correct };
}

// ─── Helper Components ──────────────────────────────────────────────────────

function GoldButton({ onClick, disabled, children, className = "" }: {
  onClick?: () => void; disabled?: boolean; children: React.ReactNode; className?: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`px-6 py-3 rounded-lg font-bold text-black transition-all ${
        disabled ? "bg-zinc-600 text-zinc-400 cursor-not-allowed"
          : "bg-gradient-to-r from-[#D4AF37] to-[#F4D03F] hover:from-[#F4D03F] hover:to-[#D4AF37] shadow-lg hover:shadow-xl"
      } ${className}`}
    >{children}</button>
  );
}

function BoldnessMeter({ boldness }: { boldness: number }) {
  const label = boldness >= 80 ? "Wildcard" : boldness >= 60 ? "Bold" : boldness >= 40 ? "Balanced" : "Playing it safe";
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <div className="w-16 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all"
          style={{ width: `${boldness}%`, background: `linear-gradient(to right, #22c55e, ${GOLD}, #ef4444)` }} />
      </div>
      <span>{label}</span>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function OscarsPoolPage() {
  usePageTracking({ pageType: "oscars_pool", pageTitle: "Oscars Pool" });
  useScrollDepth({ pageType: "oscars_pool" });
  useEngagementTime({ pageType: "oscars_pool" });

  const [phase, setPhase] = useState<"loading" | "join" | "pool">("loading");
  const [pool, setPool] = useState<PoolData | null>(null);
  const [currentPlayerIdx, setCurrentPlayerIdx] = useState<number>(-1);
  const [error, setError] = useState("");

  // Join form
  const [inputName, setInputName] = useState("");
  const [selectedEmoji, setSelectedEmoji] = useState("🎬");

  // Pick state
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [confidencePicks, setConfidencePicks] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<"picks" | "leaderboard">("picks");
  const [lastSaved, setLastSaved] = useState("");

  // TMDB images
  const [nomineeImages, setNomineeImages] = useState<Record<string, string>>({});

  // Reveal state
  const [revealCategory, setRevealCategory] = useState("");
  const [revealWinner, setRevealWinner] = useState("");

  // ─── Init ───────────────────────────────────────────────────────────────

  useEffect(() => {
    const existing = loadPool();
    if (existing) {
      setPool(existing);
      // Check if we have a saved player index
      const savedIdx = localStorage.getItem(STORAGE_KEY + "_player");
      if (savedIdx !== null) {
        const idx = parseInt(savedIdx, 10);
        if (idx >= 0 && idx < existing.players.length) {
          setCurrentPlayerIdx(idx);
          const player = existing.players[idx];
          setPicks({ ...player.picks });
          setConfidencePicks(new Set(player.confidencePicks));
          setPhase("pool");
          return;
        }
      }
    }
    setPhase("join");
  }, []);

  // ─── TMDB enrichment ──────────────────────────────────────────────────

  useEffect(() => {
    if (phase !== "pool") return;
    let cancelled = false;

    async function enrichImages() {
      const images: Record<string, string> = {};
      for (const [catKey, nominees] of Object.entries(NOMINEES_98TH)) {
        const isPerson = PERSON_CATEGORIES.has(catKey);
        for (const nom of nominees.slice(0, 5)) {
          const imageKey = `${catKey}_${nom.name}`;
          if (nomineeImages[imageKey]) continue;
          try {
            if (isPerson) {
              const person = await searchPerson(nom.name);
              const url = headshotUrl(person?.profile_path ?? null);
              if (url) images[imageKey] = url;
            } else {
              const filmName = nom.name.split(" - ")[0].trim();
              const movie = await searchMovie(filmName);
              const url = posterUrl(movie?.poster_path ?? null);
              if (url) images[imageKey] = url;
            }
          } catch { /* skip */ }
        }
      }
      if (!cancelled && Object.keys(images).length > 0) {
        setNomineeImages(prev => ({ ...prev, ...images }));
      }
    }

    enrichImages();
    return () => { cancelled = true; };
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Actions ──────────────────────────────────────────────────────────

  const handleJoin = () => {
    if (!inputName.trim()) { setError("Enter your name"); return; }
    setError("");

    let currentPool = pool;
    if (!currentPool) {
      // First player creates the pool
      currentPool = {
        poolName: "Bain Family Oscars Pool",
        players: [],
        results: {},
        createdAt: Date.now(),
      };
    }

    // Check for duplicate name
    if (currentPool.players.some(p => p.name.toLowerCase() === inputName.trim().toLowerCase())) {
      // Rejoin as existing player
      const idx = currentPool.players.findIndex(p => p.name.toLowerCase() === inputName.trim().toLowerCase());
      setCurrentPlayerIdx(idx);
      localStorage.setItem(STORAGE_KEY + "_player", String(idx));
      const player = currentPool.players[idx];
      setPicks({ ...player.picks });
      setConfidencePicks(new Set(player.confidencePicks));
      setPool(currentPool);
      setPhase("pool");
      return;
    }

    // New player
    const newPlayer: PlayerData = {
      name: inputName.trim(),
      avatar: selectedEmoji,
      picks: {},
      confidencePicks: [],
      timestamp: Date.now(),
    };
    currentPool.players.push(newPlayer);
    const idx = currentPool.players.length - 1;

    savePool(currentPool);
    setPool(currentPool);
    setCurrentPlayerIdx(idx);
    localStorage.setItem(STORAGE_KEY + "_player", String(idx));
    setPhase("pool");
  };

  const handleSavePicks = () => {
    if (!pool || currentPlayerIdx < 0) return;
    const updated = { ...pool };
    updated.players[currentPlayerIdx] = {
      ...updated.players[currentPlayerIdx],
      picks: { ...picks },
      confidencePicks: Array.from(confidencePicks),
      timestamp: Date.now(),
    };
    savePool(updated);
    setPool(updated);
    setLastSaved(new Date().toLocaleTimeString());
  };

  const handleReveal = () => {
    if (!pool || !revealCategory || !revealWinner.trim()) return;
    const updated = { ...pool };
    updated.results[revealCategory] = revealWinner.trim();
    savePool(updated);
    setPool(updated);
    setRevealCategory("");
    setRevealWinner("");
  };

  // ─── Computed ─────────────────────────────────────────────────────────

  const categoriesByOrder = useMemo(() => {
    return Object.entries(NOMINEES_98TH)
      .map(([key, nominees]) => ({ key, nominees }))
      .sort((a, b) => {
        const oa = CEREMONY_ORDER.indexOf(a.key);
        const ob = CEREMONY_ORDER.indexOf(b.key);
        return (oa === -1 ? 99 : oa) - (ob === -1 ? 99 : ob);
      });
  }, []);

  const totalCategories = categoriesByOrder.length;
  const picksCount = Object.keys(picks).length;
  const currentPlayer = pool?.players[currentPlayerIdx];

  const leaderboard = useMemo(() => {
    if (!pool) return [];
    return pool.players
      .map((p, idx) => {
        const { total, correct } = computePoints(p.picks, p.confidencePicks, pool.results);
        return { ...p, idx, total, correct, boldness: computeBoldness(p.picks), picksCount: Object.keys(p.picks).length };
      })
      .sort((a, b) => b.total - a.total || b.correct - a.correct);
  }, [pool]);

  // ─── Render: Loading ──────────────────────────────────────────────────

  if (phase === "loading") {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="text-zinc-400 animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  // ─── Render: Join ─────────────────────────────────────────────────────

  if (phase === "join") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#1a1408] via-[#09090b] to-[#09090b]">
        <div className="max-w-md mx-auto px-4 py-8">
          <div className="text-center mb-8">
            <Link href="/oscars" className="text-zinc-500 text-sm hover:text-zinc-400 mb-2 inline-block">
              ← Back to Oscars
            </Link>
            <h1 className="text-3xl font-bold mt-2" style={{ color: GOLD }}>Oscars Pool</h1>
            <p className="text-zinc-400 mt-2">Pick winners. Earn points. Bragging rights forever.</p>
            <p className="text-zinc-500 text-sm mt-1">
              Longshot picks earn more points. Choose {MAX_CONFIDENCE_PICKS} confidence picks for 1.5x bonus.
            </p>
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4 text-sm">
              {error}
            </div>
          )}

          {pool && pool.players.length > 0 && (
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 mb-4">
              <div className="text-xs text-zinc-500 mb-2">Already playing:</div>
              <div className="flex flex-wrap gap-2">
                {pool.players.map((p, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-zinc-800 rounded-full text-xs text-zinc-300">
                    {p.avatar} {p.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1">Your Name</label>
              <input
                value={inputName}
                onChange={(e) => setInputName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleJoin()}
                placeholder="e.g., Alex"
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-[#D4AF37]/50"
              />
            </div>

            <div>
              <label className="block text-sm text-zinc-400 mb-2">Pick your avatar</label>
              <div className="flex flex-wrap gap-2">
                {AVATAR_EMOJIS.map((emoji) => (
                  <button
                    key={emoji}
                    onClick={() => setSelectedEmoji(emoji)}
                    className={`w-11 h-11 rounded-lg text-xl flex items-center justify-center transition-all ${
                      selectedEmoji === emoji
                        ? "bg-[#D4AF37]/20 ring-2 ring-[#D4AF37]"
                        : "bg-zinc-800 hover:bg-zinc-700"
                    }`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>

            <GoldButton onClick={handleJoin} className="w-full text-lg" disabled={!inputName.trim()}>
              {pool && pool.players.length > 0 ? "Join Pool" : "Start Pool"}
            </GoldButton>
          </div>
        </div>
      </div>
    );
  }

  // ─── Render: Pool ─────────────────────────────────────────────────────

  if (!pool || !currentPlayer) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="text-zinc-400">Something went wrong. <button onClick={() => setPhase("join")} className="underline" style={{ color: GOLD }}>Start over</button></div>
      </div>
    );
  }

  const resultsCount = Object.keys(pool.results).length;

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#1a1408] via-[#09090b] to-[#09090b]">
      <div className="max-w-2xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="text-center mb-6">
          <Link href="/oscars" className="text-zinc-500 text-sm hover:text-zinc-400 mb-2 inline-block">← Oscars</Link>
          <h1 className="text-2xl font-bold text-white">{pool.poolName}</h1>
          <div className="flex items-center justify-center gap-3 mt-2">
            <span className="text-zinc-400 text-sm">{pool.players.length} player{pool.players.length !== 1 ? "s" : ""}</span>
            {resultsCount > 0 && (
              <>
                <span className="text-zinc-600">|</span>
                <span className="text-zinc-400 text-sm">{resultsCount}/{totalCategories} revealed</span>
              </>
            )}
          </div>
          {/* Players strip */}
          <div className="flex items-center justify-center gap-2 mt-3 flex-wrap">
            {pool.players.map((p, i) => (
              <div key={i} className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                i === currentPlayerIdx ? "bg-[#D4AF37]/20 border border-[#D4AF37]/40" : "bg-zinc-800"
              }`}>
                <span>{p.avatar}</span>
                <span className="text-zinc-300 max-w-[60px] truncate">{p.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 bg-zinc-900 rounded-lg p-1">
          {(["picks", "leaderboard"] as const).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all ${
                activeTab === tab ? "bg-[#D4AF37]/20 text-[#D4AF37]" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab === "picks" && `Picks (${picksCount}/${totalCategories})`}
              {tab === "leaderboard" && "Leaderboard"}
            </button>
          ))}
        </div>

        {/* ─── Picks Tab ─────────────────────────────────────────────── */}
        {activeTab === "picks" && (
          <div className="space-y-3">
            {/* Progress + save */}
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-zinc-400">
                <span className="font-medium text-white">{confidencePicks.size}</span>/{MAX_CONFIDENCE_PICKS} confidence picks
              </div>
              <div className="flex items-center gap-2">
                {lastSaved && <span className="text-xs text-zinc-500">Saved {lastSaved}</span>}
                <GoldButton onClick={handleSavePicks} disabled={picksCount === 0} className="!py-2 !px-4 text-sm">
                  Save Picks
                </GoldButton>
              </div>
            </div>

            {/* Category cards */}
            {categoriesByOrder.map(({ key, nominees }) => (
              <CategoryPickCard
                key={key}
                categoryKey={key}
                nominees={nominees}
                selectedNominee={picks[key]}
                isConfidencePick={confidencePicks.has(key)}
                onSelect={(nominee) => setPicks(prev => ({ ...prev, [key]: nominee }))}
                onToggleConfidence={() => {
                  setConfidencePicks(prev => {
                    const next = new Set(prev);
                    if (next.has(key)) next.delete(key);
                    else if (next.size < MAX_CONFIDENCE_PICKS) next.add(key);
                    return next;
                  });
                }}
                canAddConfidence={confidencePicks.size < MAX_CONFIDENCE_PICKS}
                result={pool.results[key]}
                ceremonyOrder={CEREMONY_ORDER.indexOf(key) + 1}
                nomineeImages={nomineeImages}
              />
            ))}

            {/* Save at bottom too */}
            <div className="pt-2">
              <GoldButton onClick={handleSavePicks} disabled={picksCount === 0} className="w-full">
                Save All Picks
              </GoldButton>
            </div>

            {/* Reveal section (for the host) */}
            <div className="mt-6 pt-4 border-t border-zinc-800">
              <h3 className="text-sm font-bold text-zinc-400 mb-3">Reveal Winner (host only)</h3>
              <div className="flex gap-2">
                <select value={revealCategory} onChange={e => {
                  setRevealCategory(e.target.value);
                  setRevealWinner("");
                }}
                  className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none"
                >
                  <option value="">Select category...</option>
                  {categoriesByOrder.map(({ key }) => (
                    <option key={key} value={key}>
                      {pool.results[key] ? "✓ " : ""}{CATEGORY_NAMES[key] || key}
                    </option>
                  ))}
                </select>
              </div>
              {revealCategory && (
                <div className="mt-2 space-y-1">
                  {NOMINEES_98TH[revealCategory]?.map(nom => (
                    <button key={nom.name} onClick={() => setRevealWinner(nom.name)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all ${
                        revealWinner === nom.name ? "bg-green-500/20 text-green-400 ring-1 ring-green-500/50" : "bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50"
                      }`}
                    >
                      {nom.name}
                    </button>
                  ))}
                  <GoldButton onClick={handleReveal} disabled={!revealWinner} className="w-full !py-2 text-sm mt-2">
                    Reveal: {revealWinner || "..."}
                  </GoldButton>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── Leaderboard Tab ───────────────────────────────────────── */}
        {activeTab === "leaderboard" && (
          <div className="space-y-4">
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-sm font-bold" style={{ color: GOLD }}>Leaderboard</span>
                <span className="text-xs text-zinc-500">{resultsCount}/{totalCategories} revealed</span>
              </div>

              {leaderboard.map((player, idx) => (
                <div key={player.idx}
                  className={`px-4 py-3 flex items-center gap-3 ${
                    idx < leaderboard.length - 1 ? "border-b border-zinc-800/50" : ""
                  } ${player.idx === currentPlayerIdx ? "bg-[#D4AF37]/5" : ""}`}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                    idx === 0 ? "bg-[#D4AF37]/20 text-[#D4AF37]"
                      : idx === 1 ? "bg-zinc-400/20 text-zinc-300"
                      : idx === 2 ? "bg-amber-700/20 text-amber-600"
                      : "bg-zinc-800 text-zinc-500"
                  }`}>
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-base">{player.avatar}</span>
                      <span className="text-sm font-medium text-white truncate">{player.name}</span>
                      {player.idx === currentPlayerIdx && <span className="text-[10px] text-zinc-500">(you)</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-zinc-500">{player.picksCount}/{totalCategories} picks</span>
                      <span className="text-xs text-zinc-500">{player.correct}/{resultsCount} correct</span>
                      <BoldnessMeter boldness={player.boldness} />
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold" style={{ color: GOLD }}>{player.total}</div>
                    <div className="text-[10px] text-zinc-500">pts</div>
                  </div>
                </div>
              ))}

              {leaderboard.length === 0 && (
                <div className="px-4 py-8 text-center text-zinc-500 text-sm">No players yet</div>
              )}
            </div>

            {/* Per-category results breakdown */}
            {resultsCount > 0 && (
              <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-zinc-800">
                  <span className="text-sm font-bold text-zinc-300">Results by Category</span>
                </div>
                {categoriesByOrder.filter(({ key }) => pool.results[key]).map(({ key }) => {
                  const winner = pool.results[key];
                  return (
                    <div key={key} className="px-4 py-2 border-b border-zinc-800/50 last:border-0">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-xs text-zinc-500">{CATEGORY_EMOJI[key] || "🎬"} {CATEGORY_NAMES[key]}</span>
                          <div className="text-sm text-green-400 font-medium">{winner}</div>
                        </div>
                        <div className="flex gap-1">
                          {pool.players.map((p, i) => {
                            const got = p.picks[key]?.toLowerCase() === winner.toLowerCase();
                            return (
                              <span key={i} title={`${p.name}: ${p.picks[key] || "no pick"}`}
                                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${
                                  got ? "bg-green-500/20 text-green-400" : "bg-zinc-800 text-zinc-600"
                                }`}
                              >
                                {got ? "✓" : p.avatar}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Switch player */}
            <div className="pt-2">
              <button onClick={() => {
                localStorage.removeItem(STORAGE_KEY + "_player");
                setPhase("join");
              }} className="w-full px-4 py-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors">
                Switch Player
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Category Pick Card ─────────────────────────────────────────────────────

function CategoryPickCard({
  categoryKey,
  nominees,
  selectedNominee,
  isConfidencePick,
  onSelect,
  onToggleConfidence,
  canAddConfidence,
  result,
  ceremonyOrder,
  nomineeImages,
}: {
  categoryKey: string;
  nominees: NomineeInfo[];
  selectedNominee?: string;
  isConfidencePick: boolean;
  onSelect: (nominee: string) => void;
  onToggleConfidence: () => void;
  canAddConfidence: boolean;
  result?: string;
  ceremonyOrder: number;
  nomineeImages: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const isMajor = MAJOR_CATEGORIES.has(categoryKey);
  const emoji = CATEGORY_EMOJI[categoryKey] || "🎬";
  const hasResult = !!result;
  const isCorrect = hasResult && selectedNominee && result.toLowerCase() === selectedNominee.toLowerCase();
  const showNominees = expanded || isMajor || !selectedNominee;

  return (
    <div className={`bg-zinc-900/80 border rounded-xl overflow-hidden transition-all ${
      hasResult ? (isCorrect ? "border-green-500/40" : "border-red-500/20")
        : isConfidencePick ? "border-[#D4AF37]/40" : "border-zinc-800"
    }`}>
      <button onClick={() => setExpanded(!expanded)} className="w-full px-4 py-3 flex items-center gap-2 text-left">
        <span className="text-zinc-500 text-xs font-mono w-5">#{ceremonyOrder}</span>
        <span className="text-base">{emoji}</span>
        <span className={`text-sm font-medium flex-1 ${isMajor ? "text-white" : "text-zinc-300"}`}>
          {CATEGORY_NAMES[categoryKey] || categoryKey}
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

      {showNominees && (
        <div className="px-4 pb-3 space-y-1">
          {hasResult && (
            <div className="text-xs text-green-400 mb-2 font-medium">Winner: {result}</div>
          )}

          {nominees.map((nominee) => {
            const isSelected = selectedNominee === nominee.name;
            const isWinner = hasResult && result.toLowerCase() === nominee.name.toLowerCase();
            const pct = (nominee.probability * 100).toFixed(0);
            const imageKey = `${categoryKey}_${nominee.name}`;
            const imageUrl = nomineeImages[imageKey];

            return (
              <button key={nominee.name} onClick={() => onSelect(nominee.name)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                  isWinner ? "bg-green-500/15 text-green-400"
                    : isSelected ? "bg-[#D4AF37]/15 text-white ring-1 ring-[#D4AF37]/50"
                    : "bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50"
                }`}
              >
                <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                  isSelected ? "border-[#D4AF37]" : "border-zinc-600"
                }`}>
                  {isSelected && <div className="w-2 h-2 rounded-full bg-[#D4AF37]" />}
                </div>

                {imageUrl ? (
                  <img src={imageUrl} alt={nominee.name}
                    className="w-8 h-8 rounded-full object-cover flex-shrink-0" loading="lazy" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center flex-shrink-0 text-xs text-zinc-400">
                    {nominee.name.charAt(0)}
                  </div>
                )}

                <span className="flex-1 text-left truncate">{nominee.name}</span>

                <div className="w-20 flex items-center gap-1.5">
                  <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                    <div className="h-full rounded-full"
                      style={{ width: `${Math.min(nominee.probability * 100, 100)}%`, backgroundColor: nominee.probability > 0.5 ? "#22c55e" : GOLD_DIM }} />
                  </div>
                  <span className="text-[10px] text-zinc-500 w-7 text-right">{pct}%</span>
                </div>
              </button>
            );
          })}

          {/* Confidence toggle */}
          {selectedNominee && !hasResult && (
            <button onClick={onToggleConfidence}
              disabled={!isConfidencePick && !canAddConfidence}
              className={`w-full mt-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isConfidencePick ? "bg-[#D4AF37]/15 text-[#D4AF37] border border-[#D4AF37]/30"
                  : canAddConfidence ? "bg-zinc-800/50 text-zinc-400 hover:text-zinc-300 border border-zinc-700"
                  : "bg-zinc-800/30 text-zinc-600 border border-zinc-800 cursor-not-allowed"
              }`}
            >
              {isConfidencePick ? "★ Confidence Pick (1.5x) — Remove" : "☆ Make Confidence Pick (1.5x)"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
