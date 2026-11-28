"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";
import {
  buildSubmissionPayload,
  COUNTRY_OPTIONS,
  emptyCuDraft,
  formatEventStartSentence,
  formatPayoutDateSentence,
  formatPeerEventDate,
  normalizeRaterName,
  RATER_STORAGE_KEY,
  type CuAgreementResponse,
  type CuFactLabelDraft,
  type CuLabelSubmitResponse,
  type CuPracticeFeedback,
  type CuPracticeStatus,
  type CuQueueResponse,
  type CuRole,
  type CuScope,
  type CuSplit,
  type CuSubjectMode,
} from "@/lib/cuLabeling";

const EVENT_DAY_CHOICES: ReadonlyArray<{
  mode: "date" | "no_single_day" | "cannot_tell";
  label: string;
  description: string;
}> = [
  {
    mode: "date",
    label: "Specific day",
    description: "Happens on one known calendar day (pick YYYY-MM-DD below).",
  },
  {
    mode: "no_single_day",
    label: "No single day",
    description: "Spans weeks, months, or a 'by / before / through' deadline where it could happen on any day.",
  },
  {
    mode: "cannot_tell",
    label: "Cannot tell from this card",
    description: "Date is unclear or missing here, even if a site payout date is listed.",
  },
];

const WHERE_CHOICES: ReadonlyArray<{
  preset: "local" | "us" | "country" | "global";
  label: string;
  belongs: string;
  example: string;
}> = [
  {
    preset: "local",
    label: "Local",
    belongs: "One city, county, metro area, or US state house / state senate district — never nationwide US.",
    example: "Highest temperature in Denver, NYC mayor, or Vermont House Orleans-3.",
  },
  {
    preset: "us",
    label: "US (nationwide)",
    belongs: "Federal US politics, US-wide business or macro markets, or US national leagues — not one city or state district.",
    example: "Fed rate move, Amazon stock close, or NFL / NBA / NHL games.",
  },
  {
    preset: "country",
    label: "One country (outside the US)",
    belongs: "National politics, economy, weather, or a domestic league inside one single country other than the US.",
    example: "China birth limits (CN), France credit rating (FR), or Premier League (GB).",
  },
  {
    preset: "global",
    label: "Global (multiple countries)",
    belongs: "Cross-border contests, wars or treaties between nations, or worldwide awards and tech across multiple countries.",
    example: "Israel–Iran ceasefire, Eurovision, World Cup, or global AI releases.",
  },
];

const STAKES_ANCHORS: ReadonlyArray<{ score: number; label: string }> = [
  { score: 1, label: "1 — Local seat, city weather, or tiny niche stat" },
  { score: 2, label: "2 — Regular-season game or routine regional company metric" },
  { score: 3, label: "3 — Major national game, governor/senate race, or big earnings report" },
  { score: 4, label: "4 — Championship final, Fed decision, court ruling, or major treaty" },
  { score: 5, label: "5 — Presidential election, war/peace shift, or global shock" },
];

const BREADTH_ANCHORS: ReadonlyArray<{ score: number; label: string }> = [
  { score: 1, label: "1 — Only a few locals or niche fans follow this" },
  { score: 2, label: "2 — Fans of one team, state, or industry care" },
  { score: 3, label: "3 — Followed across a major sport, politics, or business audience" },
  { score: 4, label: "4 — Most people in a country or big sport pay attention" },
  { score: 5, label: "5 — Household-name story people follow around the world" },
];

const AGREEMENT_FIELD_LABELS: Record<string, string> = {
  subjects: "Who or what is it about?",
  event_date: "The event's own day",
  geography: "Where",
  stakes: "How much this matters",
  breadth: "How many people care",
};

const ROLE_LABELS: Record<CuRole, string> = {
  primary: "First person",
  second: "Second person",
  tiebreak: "Tie-breaker",
};

const SPLIT_LABELS: Record<CuSplit, string> = {
  practice: "Practice round (5 cards)",
  sealed: "Sealed test set",
  dev: "Extra practice set (200)",
};

const SCOPE_LABELS: Record<CuScope, string> = {
  shared_100: "Shared 100",
  all: "Full set",
};

function formatSourceLabel(rawSource: string | null | undefined): string {
  const s = (rawSource || "").trim().toLowerCase();
  if (s === "polymarket") return "Polymarket";
  if (s === "kalshi") return "Kalshi";
  if (s === "odds_api") return "Odds API";
  if (s === "datagolf") return "DataGolf";
  return rawSource || "Unknown source";
}

export default function CuFactLabelingPage() {
  usePageTracking({ pageType: "admin_grade", pageTitle: "Market Fact Check" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  const { secret } = useAdminAuth();

  const [raterInput, setRaterInput] = useState("");
  const [activeRater, setActiveRater] = useState("");
  const [split, setSplit] = useState<CuSplit>("practice");
  const [role, setRole] = useState<CuRole>("primary");
  const [scope, setScope] = useState<CuScope>("shared_100");
  const [index, setIndex] = useState(0);

  const [queue, setQueue] = useState<CuQueueResponse | null>(null);
  const [practiceStatus, setPracticeStatus] = useState<CuPracticeStatus | null>(null);
  const [practiceFeedback, setPracticeFeedback] = useState<CuPracticeFeedback | null>(null);
  const [agreement, setAgreement] = useState<CuAgreementResponse | null>(null);
  const [showAgreement, setShowAgreement] = useState(false);

  const [draft, setDraft] = useState<CuFactLabelDraft>(emptyCuDraft);
  const [geoPreset, setGeoPreset] = useState<string>("");
  const [countryInput, setCountryInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(RATER_STORAGE_KEY) || "";
      const norm = normalizeRaterName(saved);
      if (norm) {
        setRaterInput(norm);
        setActiveRater(norm);
      }
    } catch {
      // Ignore storage failures in restricted contexts.
    }
  }, []);

  const loadData = useCallback(async () => {
    if (!secret || !activeRater) return;
    setLoading(true);
    setErrorMsg(null);
    setPracticeFeedback(null);
    try {
      const effectiveRole: CuRole = split === "practice" ? "primary" : role;
      const q = await adminFetchJSON<CuQueueResponse>(
        `/api/admin/cu-labeling/queue?split=${split}&role=${effectiveRole}&scope=${scope}&rater=${encodeURIComponent(activeRater)}`,
        secret
      );
      setQueue(q);
      setPracticeStatus(q.practice_status);
      setIndex(0);
      setDraft(emptyCuDraft());
      setGeoPreset("");
      setCountryInput("");

      if (split !== "practice") {
        const ag = await adminFetchJSON<CuAgreementResponse>(
          `/api/admin/cu-labeling/agreement?split=${split}`,
          secret
        );
        setAgreement(ag);
      } else {
        setAgreement(null);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, [secret, activeRater, split, role, scope]);

  useEffect(() => {
    if (secret && activeRater) {
      void loadData();
    }
  }, [secret, activeRater, loadData]);

  const items = queue?.items || [];
  const current = items[index] || null;
  const unlockedSealed = Boolean(practiceStatus?.unlocked_sealed ?? queue?.practice_status?.unlocked_sealed);
  const practiceDone = practiceStatus?.completed ?? queue?.practice_status?.completed ?? 0;
  const practiceRequired = practiceStatus?.required ?? queue?.practice_status?.required ?? 5;
  const practiceCardIndex = current
    ? (practiceStatus?.practice_card_ids ?? queue?.practice_status?.practice_card_ids ?? []).indexOf(
        current.market_id
      )
    : -1;
  const practiceCardNumber = practiceCardIndex >= 0 ? practiceCardIndex + 1 : index + 1;

  const payoutDateSentence = useMemo(
    () => formatPayoutDateSentence(current?.resolution_date),
    [current?.resolution_date]
  );
  const eventStartSentence = useMemo(
    () => formatEventStartSentence(current?.linked_start),
    [current?.linked_start]
  );

  const currentGeography = useMemo(() => {
    if (geoPreset === "country") {
      return countryInput.trim();
    }
    return geoPreset;
  }, [geoPreset, countryInput]);

  useEffect(() => {
    setDraft((d) => ({ ...d, geography: currentGeography }));
  }, [currentGeography]);

  const applyTypedName = (e: React.FormEvent) => {
    e.preventDefault();
    const norm = normalizeRaterName(raterInput);
    if (!norm || norm.length > 64) {
      setErrorMsg("Enter your name (1-64 characters).");
      return;
    }
    setErrorMsg(null);
    setStatusMsg(null);
    setActiveRater(norm);
    try {
      window.localStorage.setItem(RATER_STORAGE_KEY, norm);
    } catch {
      // Non-fatal.
    }
  };

  const handleSelectSplit = (nextSplit: CuSplit) => {
    if (nextSplit === "sealed" && activeRater && !unlockedSealed) {
      setErrorMsg(
        `Finish the 5-card practice round first (${practiceDone}/${practiceRequired} completed) to open the Sealed test set.`
      );
      return;
    }
    setErrorMsg(null);
    setStatusMsg(null);
    setPracticeFeedback(null);
    setSplit(nextSplit);
  };

  const toggleCandidate = (candidate: string) => {
    setDraft((prev) => {
      const exists = prev.selectedCandidates.includes(candidate);
      const next = exists
        ? prev.selectedCandidates.filter((c) => c !== candidate)
        : [...prev.selectedCandidates, candidate];
      return { ...prev, subjectMode: "candidate", selectedCandidates: next };
    });
  };

  const handleSubmit = async () => {
    if (!current || !secret || !activeRater) return;
    setErrorMsg(null);
    setStatusMsg(null);
    const effectiveRole: CuRole = split === "practice" ? "primary" : role;
    const built = buildSubmissionPayload({
      split,
      role: effectiveRole,
      rater: activeRater,
      marketId: current.market_id,
      draft,
    });
    if (!built.ok) {
      setErrorMsg(built.error);
      return;
    }

    setSubmitting(true);
    try {
      const resp = await adminFetchJSON<CuLabelSubmitResponse>("/api/admin/cu-labeling/label", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(built.payload),
      });
      if (resp.practice_status) {
        setPracticeStatus(resp.practice_status);
      }
      if (split === "practice" && resp.practice_feedback) {
        setPracticeFeedback(resp.practice_feedback);
        setStatusMsg(`Saved practice card (${resp.practice_status?.completed ?? practiceDone + 1}/${practiceRequired}).`);
      } else {
        setStatusMsg(`Saved your answers for market ${current.market_id}.`);
        setDraft(emptyCuDraft());
        setGeoPreset("");
        setCountryInput("");
        await loadData();
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save answers");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAdvanceAfterPracticeFeedback = async () => {
    setPracticeFeedback(null);
    setStatusMsg(null);
    if (unlockedSealed && practiceDone >= practiceRequired && items.length <= 1) {
      setSplit("sealed");
      return;
    }
    await loadData();
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-3 sm:px-4 pb-10 space-y-5 text-text-primary">
      <div className="space-y-1">
        <h1 className="text-xl font-bold text-text-primary">Market Fact Check</h1>
        <p className="text-sm text-text-secondary-strong">
          Start with the 5-card practice round to see right answers after each card, then label the sealed set independently.
        </p>
      </div>

      {/* Typed labeler identity & queue controls */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-4">
        <form onSubmit={applyTypedName} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-semibold uppercase tracking-wide text-text-secondary mb-1">
              Your name
            </label>
            <input
              type="text"
              value={raterInput}
              onChange={(e) => setRaterInput(e.target.value)}
              placeholder="Type your name"
              maxLength={64}
              className="w-full px-3 py-2 text-sm bg-surface-deep border border-surface-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-brand text-text-inverse hover:opacity-90 transition-opacity"
          >
            Start labeling
          </button>
          {split !== "practice" && (
            <button
              type="button"
              onClick={() => setShowAgreement((v) => !v)}
              className="px-3 py-2 text-xs font-medium rounded-lg border border-surface-border bg-surface-elevated text-text-secondary-strong hover:text-text-primary"
            >
              {showAgreement ? "Hide agreement" : "Agreement report"}
            </button>
          )}
        </form>

        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-text-secondary-strong">Market set:</span>
            <button
              type="button"
              onClick={() => handleSelectSplit("practice")}
              className={`px-2.5 py-1 rounded-md border ${
                split === "practice"
                  ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                  : "bg-surface-deep text-text-primary border-surface-border"
              }`}
            >
              Practice round ({practiceDone}/{practiceRequired})
            </button>
            <button
              type="button"
              onClick={() => handleSelectSplit("sealed")}
              aria-disabled={Boolean(activeRater && !unlockedSealed)}
              className={`px-2.5 py-1 rounded-md border ${
                split === "sealed"
                  ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                  : activeRater && !unlockedSealed
                    ? "bg-surface-elevated text-text-secondary border-surface-border opacity-75"
                    : "bg-surface-deep text-text-primary border-surface-border"
              }`}
            >
              {activeRater && !unlockedSealed ? "Sealed test set (Locked)" : "Sealed test set"}
            </button>
            <button
              type="button"
              onClick={() => handleSelectSplit("dev")}
              className={`px-2.5 py-1 rounded-md border ${
                split === "dev"
                  ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                  : "bg-surface-deep text-text-primary border-surface-border"
              }`}
            >
              {SPLIT_LABELS.dev}
            </button>
          </div>

          {split !== "practice" && (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold text-text-secondary-strong">Queue:</span>
                {(["shared_100", "all"] as const).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setScope(opt)}
                    className={`px-2.5 py-1 rounded-md border ${
                      scope === opt
                        ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                        : "bg-surface-deep text-text-primary border-surface-border"
                    }`}
                  >
                    {SCOPE_LABELS[opt]}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold text-text-secondary-strong">Role:</span>
                {(["primary", "second", "tiebreak"] as const).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setRole(opt)}
                    className={`px-2.5 py-1 rounded-md border ${
                      role === opt
                        ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                        : "bg-surface-deep text-text-primary border-surface-border"
                    }`}
                  >
                    {ROLE_LABELS[opt]}
                  </button>
                ))}
              </div>
            </>
          )}

          {queue && queue.dataset_file_present && !queue.sealed_locked && (
            <span className="sm:ml-auto text-text-secondary-strong">
              {queue.completed_by_rater} done / {queue.total_in_scope} in queue ({queue.remaining} left)
            </span>
          )}
        </div>
      </div>

      {showAgreement && agreement && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-semibold">
              How often the two labelers agreed ({SPLIT_LABELS[split]})
            </span>
            <span className="text-xs text-text-secondary-strong">
              Double-checked: {agreement.paired_markets} · Waiting for tie-breaker:{" "}
              {agreement.needs_tiebreak} · Resolved: {agreement.resolved_tiebreaks}
            </span>
          </div>
          <div className="overflow-x-auto max-w-full">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-surface-border text-text-secondary text-left">
                  <th className="py-1.5 pr-3">Question</th>
                  <th className="py-1.5 pr-3">Rule</th>
                  <th className="py-1.5 pr-3">Agreed</th>
                  <th className="py-1.5 pr-3">Checked</th>
                  <th className="py-1.5 pr-3">Rate</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {agreement.fields.map((f) => (
                  <tr key={f.field} className="border-b border-surface-border">
                    <td className="py-1.5 pr-3 font-medium text-text-primary">
                      {AGREEMENT_FIELD_LABELS[f.field] || f.field}
                    </td>
                    <td className="py-1.5 pr-3 text-text-secondary-strong">
                      {f.metric === "within_1"
                        ? "Within 1 step"
                        : f.field === "subjects"
                          ? "Same names"
                          : "Exact match"}
                    </td>
                    <td className="py-1.5 pr-3">{f.agreed}</td>
                    <td className="py-1.5 pr-3">{f.total}</td>
                    <td className="py-1.5 pr-3">
                      {f.agreement_rate === null ? "—" : `${(f.agreement_rate * 100).toFixed(1)}%`}
                    </td>
                    <td className="py-1.5">
                      {f.below_80_pct ? (
                        <span className="text-accent-danger font-semibold">
                          Below 80% — held back for Alex
                        </span>
                      ) : (
                        <span className="text-text-secondary-strong">
                          {f.tiebreak_allowed ? "Fact (tie-breaker allowed)" : "Opinion (Alex decides)"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {errorMsg && (
        <div className="px-4 py-2.5 rounded-lg border border-accent-danger bg-surface-card text-accent-danger text-sm">
          {errorMsg}
        </div>
      )}
      {statusMsg && (
        <div className="px-4 py-2.5 rounded-lg border border-accent-brand bg-surface-card text-text-primary text-sm">
          {statusMsg}
        </div>
      )}

      {!activeRater ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-secondary-strong">
          Type your name above and click <strong>Start labeling</strong> to begin the 5-card practice round.
        </div>
      ) : loading ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted animate-pulse">
          Loading cards...
        </div>
      ) : queue && !queue.dataset_file_present ? (
        <div
          data-testid="cu-labeling-missing-dataset"
          className="bg-surface-card border border-accent-warning rounded-xl p-6 space-y-2 text-sm"
        >
          <div className="font-semibold text-text-primary">Market file not loaded yet</div>
          <p className="text-text-secondary-strong">
            {queue.dataset_file_missing_message ||
              "The frozen market list for this set is not loaded on this server yet, so there are no cards to check."}
          </p>
        </div>
      ) : queue && queue.sealed_locked ? (
        <div
          data-testid="cu-labeling-sealed-locked"
          className="bg-surface-card border border-accent-warning rounded-xl p-6 space-y-3 text-sm"
        >
          <div className="font-semibold text-text-primary">
            Complete the 5-card practice round first
          </div>
          <p className="text-text-secondary-strong">
            You have completed <strong>{practiceDone} of {practiceRequired}</strong> practice cards.
            Finish the practice round so you can check your answers before the Sealed test set opens.
          </p>
          <button
            type="button"
            onClick={() => setSplit("practice")}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-accent-brand text-text-inverse hover:opacity-90"
          >
            Go to Practice round
          </button>
        </div>
      ) : practiceFeedback ? (
        <div
          data-testid="cu-practice-feedback"
          className="bg-surface-card border border-accent-brand rounded-xl p-5 space-y-4"
        >
          <div className="space-y-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
              Practice answer check · {practiceDone} of {practiceRequired} done
            </div>
            <h2 className="text-lg font-bold text-text-primary">
              {practiceFeedback.all_facts_matched
                ? "Nice — all three facts matched the answer key."
                : "Review the answer key below before the next card."}
            </h2>
            <p className="text-sm text-text-secondary-strong">{practiceFeedback.explanation}</p>
          </div>

          <div className="space-y-2">
            {practiceFeedback.fields.map((f) => (
              <div
                key={f.field}
                className="p-3 rounded-lg border border-surface-border bg-surface-deep flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-sm"
              >
                <div className="space-y-0.5 min-w-0">
                  <div className="font-semibold text-text-primary">{f.label}</div>
                  <div className="text-xs text-text-secondary-strong">
                    Your answer: <strong className="text-text-primary">{f.your_answer}</strong> · Right answer:{" "}
                    <strong className="text-text-primary">{f.right_answer}</strong>
                  </div>
                </div>
                <span
                  className={`self-start sm:self-center px-2.5 py-0.5 text-xs font-semibold rounded-full border ${
                    f.matched
                      ? "border-accent-brand text-accent-brand bg-surface-card"
                      : "border-accent-warning text-accent-warning bg-surface-card"
                  }`}
                >
                  {f.matched ? "Match" : "Review"}
                </span>
              </div>
            ))}
          </div>

          <div className="text-xs text-text-secondary-strong">
            Opinion ratings (1–5) are never marked wrong — typical range for this card: matters{" "}
            {practiceFeedback.typical_stakes[0]}–{practiceFeedback.typical_stakes[1]}, audience{" "}
            {practiceFeedback.typical_breadth[0]}–{practiceFeedback.typical_breadth[1]}.
          </div>

          <div className="flex flex-wrap items-center justify-end gap-3 pt-1">
            {unlockedSealed ? (
              <button
                type="button"
                onClick={() => handleSelectSplit("sealed")}
                className="px-5 py-2 text-sm font-semibold rounded-lg bg-accent-brand text-text-inverse hover:opacity-90"
              >
                Open Sealed test set →
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleAdvanceAfterPracticeFeedback()}
                className="px-5 py-2 text-sm font-semibold rounded-lg bg-accent-brand text-text-inverse hover:opacity-90"
              >
                Next practice card →
              </button>
            )}
          </div>
        </div>
      ) : !current ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-3 text-sm text-text-secondary-strong">
          <div>
            No remaining cards in this queue ({SPLIT_LABELS[split]}).
          </div>
          {split === "practice" && unlockedSealed && (
            <button
              type="button"
              onClick={() => handleSelectSplit("sealed")}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-accent-brand text-text-inverse hover:opacity-90"
            >
              Open Sealed test set →
            </button>
          )}
        </div>
      ) : (
        <div
          data-testid="cu-labeling-card"
          data-market-id={current.market_id}
          className="bg-surface-card border border-surface-border rounded-xl p-4 sm:p-5 space-y-5 min-w-0"
        >
          {/* Market card header */}
          <div className="border-b border-surface-border pb-4 space-y-2.5 min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-secondary">
              <span>
                Market {current.market_id} · {formatSourceLabel(current.source)} · {current.category || "uncategorized"}
              </span>
              <span>
                {split === "practice"
                  ? `Card ${practiceCardNumber} of ${practiceRequired}`
                  : `Card ${index + 1} of ${items.length}`}
              </span>
            </div>

            <h2 className="text-lg font-semibold text-text-primary break-words">{current.title}</h2>

            {eventStartSentence && (
              <div className="text-sm font-medium text-text-primary">{eventStartSentence}</div>
            )}

            {payoutDateSentence && (
              <div className="text-sm text-text-secondary-strong">{payoutDateSentence}</div>
            )}

            {current.outcomes.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {current.outcomes.slice(0, 16).map((o, idx) => (
                  <span
                    key={`${o.name}-${idx}`}
                    className="px-2 py-0.5 text-xs rounded-md bg-surface-elevated border border-surface-border text-text-primary"
                  >
                    {o.name}
                  </span>
                ))}
                {current.outcomes.length > 16 && (
                  <span className="px-2 py-0.5 text-xs text-text-secondary">
                    +{current.outcomes.length - 16} more
                  </span>
                )}
              </div>
            ) : (
              <div className="text-sm text-text-secondary-strong pt-1">No options listed</div>
            )}

            {current.rules_text && (
              <p className="text-xs text-text-secondary-strong bg-surface-deep p-3 rounded-lg border border-surface-border whitespace-pre-wrap break-words">
                {current.rules_text}
              </p>
            )}

            {/* Venue link on every card so labelers can open the original market rules */}
            <div className="flex flex-wrap items-center gap-2.5 pt-1">
              <a
                href={current.venue_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-surface-border bg-surface-elevated text-text-primary hover:border-accent-brand transition-colors"
              >
                {current.venue_link_label} ↗
              </a>
              <span className="text-xs text-text-secondary-strong">
                Read the full rules on the original market page if the card text is not enough.
              </span>
            </div>
          </div>

          {/* Blind vs Tiebreak peer panel */}
          {split === "practice" ? (
            <div className="text-xs text-text-secondary-strong">
              Practice card {practiceCardNumber} of {practiceRequired}: save your answers to see the right answers and explanation.
            </div>
          ) : role !== "tiebreak" ? (
            <div className="text-xs text-text-secondary">
              Blind check active: label on your own — neither labeler ever sees what the other answered.
            </div>
          ) : (
            <div className="bg-surface-elevated border border-surface-border rounded-lg p-3 space-y-2 text-xs">
              <div className="font-semibold text-text-primary">
                Disagreeing fact fields:{" "}
                {current.disagreeing_fact_fields
                  .map((f) => AGREEMENT_FIELD_LABELS[f] || f)
                  .join(", ")}{" "}
                (1–5 opinion ratings excluded)
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                {current.peer_labels.map((peer) => (
                  <div
                    key={`${peer.rater}-${peer.role}`}
                    className="bg-surface-card border border-surface-border rounded-lg p-2.5 space-y-1"
                  >
                    <div className="font-semibold text-text-primary">
                      {peer.rater} ({ROLE_LABELS[peer.role]})
                    </div>
                    <div>
                      Who or what:{" "}
                      {peer.subjects_answer?.selection_kind === "none_of_these"
                        ? "None of these"
                        : peer.subjects_answer?.selection_kind === "not_sure"
                          ? "Not sure"
                          : (peer.subjects_answer?.selected || []).join(", ") || "blank"}
                    </div>
                    <div>Day: {formatPeerEventDate(peer.event_date_answer, peer.no_single_day)}</div>
                    <div>Where: {peer.geography_answer || "blank"}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Question 1: Who or what is it about? */}
          <div className="space-y-2.5">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-text-primary">1. Who or what is it about?</div>
              <p className="text-xs text-text-secondary-strong">
                Pick every specific person, team, company, bill, tournament, or country the outcome turns on — pick None of these for city weather forecasts, market indexes, or unnamed groups.
              </p>
              <p className="text-xs text-text-secondary">
                <strong>Example:</strong> &quot;Israel x Iran ceasefire&quot; → pick <strong>Israel</strong> and <strong>Iran</strong> · &quot;Highest temperature in Denver&quot; → <strong>None of these</strong> · &quot;Amazon (AMZN)&quot; → pick <strong>Amazon</strong>.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {current.subject_candidates.map((cand) => {
                const active = draft.subjectMode === "candidate" && draft.selectedCandidates.includes(cand);
                return (
                  <button
                    key={cand}
                    type="button"
                    onClick={() => toggleCandidate(cand)}
                    className={`px-2.5 py-1.5 text-xs rounded-md border transition-colors ${
                      active
                        ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                        : "bg-surface-deep text-text-primary border-surface-border"
                    }`}
                  >
                    {cand}
                  </button>
                );
              })}
              {(["custom", "none_of_these", "not_sure"] as CuSubjectMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() =>
                    setDraft((d) => ({
                      ...d,
                      subjectMode: mode,
                      selectedCandidates: mode === "candidate" ? d.selectedCandidates : [],
                    }))
                  }
                  className={`px-2.5 py-1.5 text-xs rounded-md border transition-colors ${
                    draft.subjectMode === mode
                      ? "bg-accent-brand text-text-inverse border-accent-brand font-semibold"
                      : "bg-surface-elevated text-text-primary border-surface-border"
                  }`}
                >
                  {mode === "custom" ? "Custom" : mode === "none_of_these" ? "None of these" : "Not sure"}
                </button>
              ))}
            </div>
            {draft.subjectMode === "custom" && (
              <input
                type="text"
                value={draft.customSubject}
                onChange={(e) => setDraft((d) => ({ ...d, customSubject: e.target.value }))}
                placeholder="Comma-separated names from the text"
                className="w-full px-3 py-2 text-sm bg-surface-deep border border-surface-border rounded-lg"
              />
            )}
          </div>

          {/* Question 2: The event's own day */}
          <div className="space-y-2.5 pt-2 border-t border-surface-border">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-text-primary">2. The event&apos;s own day</div>
              <p className="text-xs text-text-secondary-strong">
                The real-world calendar day the event happens — not the site&apos;s payout timestamp, and not a &quot;by / before / through&quot; deadline where it could happen on any day up to then.
              </p>
              <p className="text-xs text-text-secondary">
                <strong>Example:</strong> Nov 7 election paying out next May → <strong>2028-11-07</strong> · &quot;through November 30&quot; → <strong>No single day</strong> · &quot;Beat quarterly earnings?&quot; (no date on card) → <strong>Cannot tell from this card</strong>.
              </p>
            </div>
            <div className="grid sm:grid-cols-3 gap-2">
              {EVENT_DAY_CHOICES.map((opt) => {
                const selected = draft.eventDateMode === opt.mode;
                return (
                  <button
                    key={opt.mode}
                    type="button"
                    onClick={() =>
                      setDraft((d) => ({
                        ...d,
                        eventDateMode: opt.mode,
                        eventDate: opt.mode === "date" ? d.eventDate : "",
                      }))
                    }
                    className={`p-3 text-left rounded-lg border transition-colors ${
                      selected
                        ? "border-2 border-accent-brand bg-surface-elevated text-text-primary ring-1 ring-accent-brand"
                        : "border-surface-border bg-surface-deep text-text-primary"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold">{opt.label}</span>
                      {selected && (
                        <span className="text-[11px] font-semibold text-accent-brand">Selected</span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-text-secondary-strong">{opt.description}</p>
                  </button>
                );
              })}
            </div>
            {draft.eventDateMode === "date" && (
              <div className="pt-1 flex flex-wrap items-center gap-2">
                <label className="text-xs font-medium text-text-secondary-strong">
                  Calendar day (YYYY-MM-DD):
                </label>
                <input
                  type="date"
                  value={draft.eventDate}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, eventDateMode: "date", eventDate: e.target.value }))
                  }
                  className="px-3 py-1.5 text-sm bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                />
              </div>
            )}
          </div>

          {/* Question 3: Where (non-overlapping choices, each with rule + example) */}
          <div className="space-y-2.5 pt-2 border-t border-surface-border">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-text-primary">3. Where</div>
              <p className="text-xs text-text-secondary-strong">
                Pick the single smallest region where the event takes place or applies — these four choices do not overlap.
              </p>
              <p className="text-xs text-text-secondary">
                <strong>Example:</strong> State house race or city weather → <strong>Local</strong> · NFL or US federal politics → <strong>US (nationwide)</strong> · France policy → <strong>One country (outside the US)</strong> · Two nations or World Cup → <strong>Global</strong>.
              </p>
            </div>
            <div className="grid sm:grid-cols-2 gap-2.5">
              {WHERE_CHOICES.map((opt) => {
                const selected = geoPreset === opt.preset;
                return (
                  <button
                    key={opt.preset}
                    type="button"
                    onClick={() => setGeoPreset(opt.preset)}
                    className={`p-3 text-left rounded-lg border transition-colors ${
                      selected
                        ? "border-2 border-accent-brand bg-surface-elevated text-text-primary ring-1 ring-accent-brand"
                        : "border-surface-border bg-surface-deep text-text-primary"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold">{opt.label}</span>
                      {selected && (
                        <span className="text-[11px] font-semibold text-accent-brand">Selected</span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-text-secondary-strong">{opt.belongs}</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      <strong>Example:</strong> {opt.example}
                    </p>
                  </button>
                );
              })}
            </div>
            {geoPreset === "country" && (
              <div className="pt-1">
                <select
                  aria-label="Country"
                  value={countryInput}
                  onChange={(e) => setCountryInput(e.target.value)}
                  className="w-full sm:w-auto px-3 py-1.5 text-sm bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                >
                  <option value="">Choose a country outside the US...</option>
                  {COUNTRY_OPTIONS.map((c) => (
                    <option key={c.code} value={`country:${c.code}`}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Questions 4 & 5: How much this matters & How many people care (asked last, hidden in tiebreak) */}
          {(role !== "tiebreak" || split === "practice") ? (
            <div className="space-y-4 pt-2 border-t border-surface-border">
              <div className="grid md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <div className="text-sm font-semibold text-text-primary">
                      4. How much this matters (1–5)
                    </div>
                    <p className="text-xs text-text-secondary-strong">
                      Your own judgment of the real-world impact if this happens (answered last, never sent to a tie-breaker).
                    </p>
                    <p className="text-xs text-text-secondary">
                      <strong>Example:</strong> City weather is <strong>1</strong> · regular-season game is <strong>2</strong> · Fed rate decision is <strong>4</strong>.
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    {STAKES_ANCHORS.map((item) => (
                      <button
                        key={item.score}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, stakes: item.score }))}
                        className={`w-9 h-9 text-xs font-semibold rounded-md border transition-colors ${
                          draft.stakes === item.score
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {item.score}
                      </button>
                    ))}
                  </div>
                  <ul className="space-y-0.5 text-xs text-text-secondary-strong">
                    {STAKES_ANCHORS.map((item) => (
                      <li key={item.score}>{item.label}</li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-2">
                  <div className="space-y-1">
                    <div className="text-sm font-semibold text-text-primary">
                      5. How many people care (1–5)
                    </div>
                    <p className="text-xs text-text-secondary-strong">
                      Your own judgment of how wide the audience following this story is (never sent to a tie-breaker).
                    </p>
                    <p className="text-xs text-text-secondary">
                      <strong>Example:</strong> Local district race is <strong>1</strong> · one US sport is <strong>3</strong> · global celebrity or war news is <strong>5</strong>.
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    {BREADTH_ANCHORS.map((item) => (
                      <button
                        key={item.score}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, breadth: item.score }))}
                        className={`w-9 h-9 text-xs font-semibold rounded-md border transition-colors ${
                          draft.breadth === item.score
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {item.score}
                      </button>
                    ))}
                  </div>
                  <ul className="space-y-0.5 text-xs text-text-secondary-strong">
                    {BREADTH_ANCHORS.map((item) => (
                      <li key={item.score}>{item.label}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-2 pt-2 border-t border-surface-border">
              <div className="text-sm font-semibold text-text-primary">
                4. Written evidence note (required for tie-break)
              </div>
              <p className="text-xs text-text-secondary-strong">
                Open the venue link above if needed, then quote the phrase or rule that settles the fact disagreement.
              </p>
              <p className="text-xs text-text-secondary">
                <strong>Example:</strong> &quot;Venue rules say quarterly earnings release is Dec 3, 2026 → 2026-12-03.&quot;
              </p>
              <textarea
                rows={3}
                value={draft.evidenceNote}
                onChange={(e) => setDraft((d) => ({ ...d, evidenceNote: e.target.value }))}
                placeholder="Quote the exact phrase in the title, options, or venue rules."
                className="w-full px-3 py-2 text-sm bg-surface-deep border border-surface-border rounded-lg"
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-surface-border">
            <div className="flex gap-2">
              <button
                type="button"
                disabled={index <= 0}
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                className="px-3 py-1.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-secondary-strong disabled:opacity-40"
              >
                Prev
              </button>
              <button
                type="button"
                disabled={index >= items.length - 1}
                onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}
                className="px-3 py-1.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-secondary-strong disabled:opacity-40"
              >
                Skip / Next
              </button>
            </div>
            <button
              type="button"
              disabled={submitting}
              onClick={handleSubmit}
              className="px-5 py-2 text-sm font-semibold rounded-lg bg-accent-brand text-text-inverse hover:opacity-90 disabled:opacity-50"
            >
              {submitting
                ? "Saving..."
                : split === "practice"
                  ? "Check practice answer"
                  : role === "tiebreak"
                    ? "Save fact tie-break"
                    : "Save answers"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
