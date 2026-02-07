"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface PropChoice {
  [choice: string]: number; // choice → probability
}

interface PropStatus {
  id: string;
  question: string;
  category: string;
  choices: PropChoice;
  resolved: boolean;
  correct_answer: string | null;
  resolved_at: string | null;
  has_other: boolean;
  other_probability: number;
  is_tiebreaker?: boolean;
}

interface PendingPick {
  prop_id: string;
  question: string;
  pick: string;
  probability: number;
}

interface KeyProp {
  prop_id: string;
  question: string;
  pick: string;
  probability: number;
  impact_score: number;
  uniqueness: number;
}

interface EntrantData {
  rank: number;
  name: string;
  actual_points: number;
  forecasted_points: number;
  max_possible: number;
  correct_picks: { prop_id: string; question: string; pick: string }[];
  incorrect_picks: {
    prop_id: string;
    question: string;
    pick: string;
    correct_answer: string;
  }[];
  pending_picks: PendingPick[];
  key_props: KeyProp[];
  best_possible_finish: number;
  can_still_win: boolean;
  eliminated: boolean;
  tiebreaker: number | null;
  total_picks: number;
}

interface Summary {
  total_props: number;
  resolved_count: number;
  open_count: number;
  entrant_count: number;
  categories: Record<string, string>;
  category_order: string[];
}

interface LeaderboardResponse {
  leaderboard: EntrantData[];
  props: PropStatus[];
  summary: Summary;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POLL_INTERVAL = 20_000; // 20 seconds
const COMMENTARY_INTERVAL = 90_000; // 90 seconds

const SEAHAWKS_PRIMARY = "#002244";
const SEAHAWKS_SECONDARY = "#69BE28";
const PATRIOTS_PRIMARY = "#002244";
const PATRIOTS_SECONDARY = "#C60C30";

const CATEGORY_EMOJI: Record<string, string> = {
  pregame: "",
  first_quarter: "1",
  second_quarter: "2",
  halftime: "",
  game: "",
  postgame: "",
};

// ---------------------------------------------------------------------------
// Confetti Component (fires when props resolve)
// ---------------------------------------------------------------------------
function ResolvedConfetti({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const colors = [
      SEAHAWKS_SECONDARY,
      PATRIOTS_SECONDARY,
      "#FFD700",
      "#FF6B35",
      "#00D4FF",
      "#FF1493",
      "#7CFC00",
    ];

    interface Particle {
      x: number;
      y: number;
      vx: number;
      vy: number;
      size: number;
      color: string;
      rotation: number;
      rotSpeed: number;
      life: number;
    }

    const particles: Particle[] = [];
    for (let i = 0; i < 150; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: -20 - Math.random() * 200,
        vx: (Math.random() - 0.5) * 8,
        vy: Math.random() * 4 + 2,
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * 360,
        rotSpeed: (Math.random() - 0.5) * 10,
        life: 1,
      });
    }

    let frameId: number;
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      let alive = false;

      for (const p of particles) {
        if (p.life <= 0) continue;
        alive = true;

        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.1;
        p.rotation += p.rotSpeed;
        p.life -= 0.005;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }

      if (alive) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [active]);

  if (!active) return null;

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 9999 }}
    />
  );
}

// ---------------------------------------------------------------------------
// Resolution Notification Banner
// ---------------------------------------------------------------------------
function ResolutionBanner({
  notifications,
}: {
  notifications: {
    question: string;
    correct_answer: string;
    resolved_at: string;
  }[];
}) {
  if (notifications.length === 0) return null;

  return (
    <div className="space-y-2 mb-4">
      {notifications.map((n, i) => (
        <div
          key={i}
          className="rounded-xl px-5 py-3 text-white font-bold text-center animate-pulse"
          style={{
            background: `linear-gradient(135deg, ${SEAHAWKS_SECONDARY}, ${PATRIOTS_SECONDARY})`,
            animation: "pulse 2s ease-in-out infinite",
          }}
        >
          <div className="text-lg">PROP RESOLVED!</div>
          <div className="text-sm font-normal opacity-90 mt-1">
            {n.question}
          </div>
          <div className="text-xl mt-1">{n.correct_answer}</div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Leaderboard Table
// ---------------------------------------------------------------------------
function LeaderboardTable({
  leaderboard,
  expandedName,
  onToggle,
}: {
  leaderboard: EntrantData[];
  expandedName: string | null;
  onToggle: (name: string) => void;
}) {
  return (
    <div className="space-y-2">
      {leaderboard.map((entry, index) => {
        const isExpanded = expandedName === entry.name;
        const isTop3 = entry.rank <= 3;
        const medalColors = ["#FFD700", "#C0C0C0", "#CD7F32"];

        return (
          <div key={entry.name}>
            {/* Main row */}
            <button
              onClick={() => onToggle(entry.name)}
              className={`w-full text-left rounded-xl p-4 transition-all ${
                isExpanded
                  ? "bg-white shadow-lg ring-2 ring-blue-200"
                  : "bg-white shadow-card hover:shadow-card-hover"
              } ${entry.eliminated ? "opacity-60" : ""}`}
            >
              <div className="flex items-center gap-3">
                {/* Rank */}
                <div
                  className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg"
                  style={{
                    background: isTop3
                      ? medalColors[entry.rank - 1]
                      : "#E5E7EB",
                    color: isTop3 ? "#fff" : "#6B7280",
                  }}
                >
                  {entry.rank}
                </div>

                {/* Name + status */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-graphite truncate">
                      {entry.name}
                    </span>
                    {entry.can_still_win && entry.rank > 1 && (
                      <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full font-medium">
                        Can win!
                      </span>
                    )}
                    {entry.eliminated && (
                      <span className="text-xs px-2 py-0.5 bg-red-100 text-red-600 rounded-full font-medium">
                        Eliminated
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate mt-0.5">
                    {entry.correct_picks.length} correct &middot;{" "}
                    {entry.incorrect_picks.length} wrong &middot;{" "}
                    {entry.pending_picks.length} pending
                  </div>
                </div>

                {/* Points */}
                <div className="text-right flex-shrink-0">
                  <div className="text-2xl font-bold text-graphite">
                    {entry.forecasted_points}
                  </div>
                  <div className="text-xs text-slate">
                    {entry.actual_points} locked &middot; best #{entry.best_possible_finish}
                  </div>
                </div>

                {/* Expand chevron */}
                <svg
                  className={`w-5 h-5 text-slate transition-transform ${isExpanded ? "rotate-180" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </div>
            </button>

            {/* Expanded detail */}
            {isExpanded && (
              <div className="bg-white rounded-b-xl px-4 pb-4 -mt-1 shadow-lg space-y-3">
                {/* Key props */}
                {entry.key_props.length > 0 && (
                  <div>
                    <div className="text-xs font-bold text-graphite uppercase tracking-wide mb-1">
                      Props That Matter Most
                    </div>
                    {entry.key_props.map((kp) => (
                      <div
                        key={kp.prop_id}
                        className="flex items-center gap-2 text-sm py-1"
                      >
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            background:
                              kp.probability > 0.5
                                ? SEAHAWKS_SECONDARY
                                : PATRIOTS_SECONDARY,
                          }}
                        />
                        <span className="text-slate flex-1 truncate">
                          {kp.question}
                        </span>
                        <span className="font-mono font-bold">
                          &ldquo;{kp.pick}&rdquo;
                        </span>
                        <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-mono">
                          {Math.round(kp.probability * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Correct picks */}
                {entry.correct_picks.length > 0 && (
                  <div>
                    <div className="text-xs font-bold text-emerald uppercase tracking-wide mb-1">
                      Correct
                    </div>
                    {entry.correct_picks.map((p) => (
                      <div key={p.prop_id} className="text-sm py-0.5 text-slate">
                        {p.question}: <span className="text-emerald font-medium">{p.pick}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Incorrect picks */}
                {entry.incorrect_picks.length > 0 && (
                  <div>
                    <div className="text-xs font-bold text-rust uppercase tracking-wide mb-1">
                      Incorrect
                    </div>
                    {entry.incorrect_picks.map((p) => (
                      <div key={p.prop_id} className="text-sm py-0.5 text-slate">
                        {p.question}:{" "}
                        <span className="line-through text-red-400">{p.pick}</span>{" "}
                        <span className="text-emerald font-medium">({p.correct_answer})</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Pending picks */}
                {entry.pending_picks.length > 0 && (
                  <div>
                    <div className="text-xs font-bold text-amber uppercase tracking-wide mb-1">
                      Pending
                    </div>
                    {entry.pending_picks.map((p) => (
                      <div
                        key={p.prop_id}
                        className="flex items-center gap-2 text-sm py-0.5"
                      >
                        <span className="text-slate flex-1 truncate">
                          {p.question}
                        </span>
                        <span className="font-medium">{p.pick}</span>
                        <span className="text-xs font-mono text-slate">
                          {Math.round(p.probability * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tiebreaker */}
                {entry.tiebreaker !== null && (
                  <div className="text-xs text-slate">
                    Tiebreaker guess: {entry.tiebreaker} total points
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props Grid
// ---------------------------------------------------------------------------
function PropsGrid({ props }: { props: PropStatus[] }) {
  const grouped: Record<string, PropStatus[]> = {};
  for (const p of props) {
    if (!grouped[p.category]) grouped[p.category] = [];
    grouped[p.category].push(p);
  }

  const categoryOrder = [
    "pregame",
    "first_quarter",
    "second_quarter",
    "halftime",
    "game",
    "postgame",
  ];

  const categoryLabels: Record<string, string> = {
    pregame: "Pre-Game",
    first_quarter: "1st Quarter",
    second_quarter: "2nd Quarter",
    halftime: "Halftime",
    game: "Full Game",
    postgame: "Post-Game",
  };

  return (
    <div className="space-y-4">
      {categoryOrder.map((cat) => {
        const catProps = grouped[cat];
        if (!catProps || catProps.length === 0) return null;

        return (
          <div key={cat}>
            <div className="text-xs font-bold text-slate uppercase tracking-wide mb-2">
              {CATEGORY_EMOJI[cat]} {categoryLabels[cat]}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {catProps.map((prop) => (
                <PropCard key={prop.id} prop={prop} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PropCard({ prop }: { prop: PropStatus }) {
  if (prop.is_tiebreaker) return null;

  const maxProb = Math.max(...Object.values(prop.choices));

  return (
    <div
      className={`rounded-lg p-3 text-sm ${
        prop.resolved
          ? "bg-emerald-50 border border-emerald-200"
          : "bg-white shadow-card"
      }`}
    >
      <div className="font-medium text-graphite mb-2 leading-tight text-xs">
        {prop.question}
      </div>
      <div className="space-y-1">
        {Object.entries(prop.choices).map(([choice, prob]) => {
          const isCorrect =
            prop.resolved &&
            choice.toLowerCase().trim() ===
              (prop.correct_answer || "").toLowerCase().trim();
          const isWrong = prop.resolved && !isCorrect;
          const barWidth = Math.max(prob * 100, 2);

          return (
            <div key={choice} className="flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1">
                  {isCorrect && (
                    <span className="text-emerald font-bold text-xs flex-shrink-0">
                      &#10003;
                    </span>
                  )}
                  <span
                    className={`truncate text-xs ${
                      isCorrect
                        ? "font-bold text-emerald"
                        : isWrong
                          ? "text-slate line-through"
                          : "text-graphite"
                    }`}
                  >
                    {choice}
                  </span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full mt-0.5 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${barWidth}%`,
                      background: isCorrect
                        ? SEAHAWKS_SECONDARY
                        : prop.resolved
                          ? "#D1D5DB"
                          : prob === maxProb
                            ? "#3B82F6"
                            : "#93C5FD",
                    }}
                  />
                </div>
              </div>
              <span
                className={`text-xs font-mono flex-shrink-0 w-10 text-right ${
                  isCorrect ? "font-bold text-emerald" : "text-slate"
                }`}
              >
                {Math.round(prob * 100)}%
              </span>
            </div>
          );
        })}
        {prop.has_other && !prop.resolved && (
          <div className="flex items-center gap-2">
            <div className="flex-1 min-w-0">
              <span className="text-xs text-slate">Other</span>
              <div className="h-1.5 bg-gray-100 rounded-full mt-0.5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gray-300"
                  style={{ width: `${Math.max(prop.other_probability * 100, 2)}%` }}
                />
              </div>
            </div>
            <span className="text-xs font-mono text-slate w-10 text-right">
              {Math.round(prop.other_probability * 100)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Commentary
// ---------------------------------------------------------------------------
function CommentaryBar({ text }: { text: string }) {
  if (!text) return null;

  return (
    <div
      className="rounded-xl p-4 text-white text-center"
      style={{
        background: `linear-gradient(135deg, ${SEAHAWKS_PRIMARY}, ${PATRIOTS_PRIMARY} 50%, ${PATRIOTS_SECONDARY})`,
      }}
    >
      <div className="text-xs font-bold uppercase tracking-wider opacity-70 mb-1">
        AI Commentator
      </div>
      <div className="text-sm leading-relaxed font-medium">{text}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress Ring
// ---------------------------------------------------------------------------
function ProgressRing({
  resolved,
  total,
}: {
  resolved: number;
  total: number;
}) {
  const pct = total > 0 ? resolved / total : 0;
  const r = 40;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - pct);

  return (
    <div className="relative w-24 h-24">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth="8"
        />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={SEAHAWKS_SECONDARY}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold text-graphite">{resolved}</span>
        <span className="text-xs text-slate">of {total}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function ContestPage() {
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [commentary, setCommentary] = useState("");
  const [expandedName, setExpandedName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showQR, setShowQR] = useState(false);
  const [confettiActive, setConfettiActive] = useState(false);
  const [recentNotifications, setRecentNotifications] = useState<
    { question: string; correct_answer: string; resolved_at: string }[]
  >([]);
  const [activeTab, setActiveTab] = useState<"leaderboard" | "props">(
    "leaderboard"
  );

  const prevResolvedRef = useRef<Set<string>>(new Set());

  const fetchData = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/contest/leaderboard`);
      if (!resp.ok) throw new Error(`API error: ${resp.status}`);
      const result: LeaderboardResponse = await resp.json();
      setData(result);
      setError(null);

      // Detect newly resolved props
      const currentResolved = new Set(
        result.props.filter((p) => p.resolved).map((p) => p.id)
      );
      const newlyResolved = Array.from(currentResolved).filter(
        (id) => !prevResolvedRef.current.has(id)
      );

      if (newlyResolved.length > 0 && prevResolvedRef.current.size > 0) {
        // Trigger confetti
        setConfettiActive(true);
        setTimeout(() => setConfettiActive(false), 4000);

        // Add notifications
        const newNotifs = newlyResolved
          .map((id) => {
            const prop = result.props.find((p) => p.id === id);
            if (!prop) return null;
            return {
              question: prop.question,
              correct_answer: prop.correct_answer || "",
              resolved_at: prop.resolved_at || "",
            };
          })
          .filter(Boolean) as {
          question: string;
          correct_answer: string;
          resolved_at: string;
        }[];

        setRecentNotifications((prev) => [...newNotifs, ...prev].slice(0, 5));

        // Auto-clear notifications after 15s
        setTimeout(() => {
          setRecentNotifications((prev) =>
            prev.filter(
              (n) => !newNotifs.some((nn) => nn.question === n.question)
            )
          );
        }, 15000);
      }

      prevResolvedRef.current = currentResolved;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCommentary = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/contest/commentary`);
      if (!resp.ok) return;
      const result = await resp.json();
      setCommentary(result.commentary);
    } catch {
      // Silently ignore commentary failures
    }
  }, []);

  // Initial load + polling
  useEffect(() => {
    fetchData();
    const dataInterval = setInterval(fetchData, POLL_INTERVAL);
    return () => clearInterval(dataInterval);
  }, [fetchData]);

  // Commentary polling (slower)
  useEffect(() => {
    fetchCommentary();
    const commentaryInterval = setInterval(fetchCommentary, COMMENTARY_INTERVAL);
    return () => clearInterval(commentaryInterval);
  }, [fetchCommentary]);

  // --- Render ---

  if (loading) {
    return (
      <div className="min-h-screen bg-snow flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
          <div className="text-slate">Loading contest data...</div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-snow flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">&#127944;</div>
          <div className="text-xl font-bold text-graphite mb-2">
            Contest Loading...
          </div>
          <div className="text-slate text-sm mb-4">
            {error || "Waiting for data from the Google Sheet."}
          </div>
          <div className="text-xs text-slate">
            Make sure the Google Sheet is published to the web and the backend
            can reach it.
          </div>
          <button
            onClick={fetchData}
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const { leaderboard, props, summary } = data;

  return (
    <div className="min-h-screen bg-snow">
      <ResolvedConfetti active={confettiActive} />

      {/* Header */}
      <div
        className="text-white py-6 px-4"
        style={{
          background: `linear-gradient(135deg, ${SEAHAWKS_PRIMARY} 0%, #0B3D2E 25%, #1a1a2e 50%, #1a1a2e 50%, #2D1B30 75%, ${PATRIOTS_SECONDARY} 100%)`,
        }}
      >
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                Super Bowl LX
              </h1>
              <div className="text-sm opacity-80 mt-1">
                Prop Bet Contest &middot; Seahawks vs Patriots
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowQR(!showQR)}
                className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                title="Show QR code to join"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
                </svg>
              </button>
              <ProgressRing
                resolved={summary.resolved_count}
                total={summary.total_props}
              />
            </div>
          </div>

          {/* QR Code overlay */}
          {showQR && (
            <div className="mt-4 flex flex-col items-center bg-white rounded-xl p-6 text-graphite">
              <div className="text-lg font-bold mb-2">
                Scan to Join the Contest!
              </div>
              <Image
                src="/sb-contest-qr.png"
                alt="QR Code - Scan to join the Super Bowl prop bet contest"
                width={200}
                height={200}
                className="rounded-lg"
              />
              <div className="text-xs text-slate mt-2">
                Fill out the form, then your picks will appear here automatically
              </div>
            </div>
          )}

          {/* Summary stats */}
          <div className="flex gap-4 mt-3 text-sm">
            <div className="bg-white/10 rounded-lg px-3 py-1.5">
              <span className="font-bold">{summary.entrant_count}</span>{" "}
              <span className="opacity-70">players</span>
            </div>
            <div className="bg-white/10 rounded-lg px-3 py-1.5">
              <span className="font-bold">{summary.resolved_count}</span>
              <span className="opacity-70">/{summary.total_props} resolved</span>
            </div>
            <div className="bg-white/10 rounded-lg px-3 py-1.5">
              <span className="font-bold">{summary.open_count}</span>{" "}
              <span className="opacity-70">remaining</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="max-w-4xl mx-auto px-4 py-4">
        {/* Resolution notifications */}
        <ResolutionBanner notifications={recentNotifications} />

        {/* AI Commentary */}
        {commentary && <div className="mb-4"><CommentaryBar text={commentary} /></div>}

        {/* Tab switcher */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveTab("leaderboard")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "leaderboard"
                ? "bg-graphite text-white"
                : "bg-white text-slate hover:bg-gray-50 shadow-card"
            }`}
          >
            Leaderboard
          </button>
          <button
            onClick={() => setActiveTab("props")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "props"
                ? "bg-graphite text-white"
                : "bg-white text-slate hover:bg-gray-50 shadow-card"
            }`}
          >
            All Props
          </button>
        </div>

        {/* Leaderboard tab */}
        {activeTab === "leaderboard" && (
          <LeaderboardTable
            leaderboard={leaderboard}
            expandedName={expandedName}
            onToggle={(name) =>
              setExpandedName(expandedName === name ? null : name)
            }
          />
        )}

        {/* Props tab */}
        {activeTab === "props" && <PropsGrid props={props} />}

        {/* Footer */}
        <div className="text-center text-xs text-slate mt-8 mb-4">
          Odds sourced from DraftKings, FanDuel, BetMGM, and historical data
          &middot; Updated live &middot; Powered by{" "}
          <a
            href="https://odds.alexbain.com"
            className="underline hover:text-graphite"
          >
            OddsTracker
          </a>
        </div>
      </div>
    </div>
  );
}
