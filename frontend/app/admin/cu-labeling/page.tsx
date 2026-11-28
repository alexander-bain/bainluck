"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";
import {
  buildSubmissionPayload,
  COMPARATOR_LABELS,
  COUNTRY_OPTIONS,
  DEFAULT_CLAIM_COMPARATORS,
  DEFAULT_CLAIM_HORIZON_KINDS,
  DEFAULT_CLAIM_MEASURES,
  emptyCuDraft,
  formatMeasureChoiceLabel,
  formatPayoutDateSentence,
  formatPeerClaimFrame,
  HORIZON_LABELS,
  MEASURE_GROUPS,
  MEASURE_LABELS,
  normalizeRaterName,
  RATER_STORAGE_KEY,
  type CuAgreementResponse,
  type CuFactLabelDraft,
  type CuQueueResponse,
  type CuRole,
  type CuScope,
  type CuSplit,
  type CuStructure,
  type CuSubjectMode,
} from "@/lib/cuLabeling";

const STRUCTURE_OPTIONS: Array<{ value: CuStructure; label: string; help: string }> = [
  { value: "ladder", label: "Ladder of one number", help: "Options are different cutoffs for the same number (like Above 100, Above 200)" },
  { value: "dated_bucket", label: "Set of dated options", help: "Options split the same event across different deadline dates" },
  { value: "neither", label: "Neither", help: "Plain Yes/No, a matchup, or a list of people/teams" },
];

const GEO_PRESETS: Array<{ value: "us" | "global" | "local"; label: string }> = [
  { value: "us", label: "US" },
  { value: "global", label: "Global / multi-country" },
  { value: "local", label: "Local / city / state district" },
];

const STAKES_ANCHORS: Array<{ score: number; label: string }> = [
  { score: 1, label: "1 — Local district race, city weather, or tiny niche stat" },
  { score: 2, label: "2 — Regular-season game or routine regional company metric" },
  { score: 3, label: "3 — Major national game, governor/senate race, or big earnings report" },
  { score: 4, label: "4 — Championship final, Fed decision, court ruling, or major treaty" },
  { score: 5, label: "5 — Presidential election, war/peace shift, or global shock" },
];

const BREADTH_ANCHORS: Array<{ score: number; label: string }> = [
  { score: 1, label: "1 — Only a few locals or niche fans follow this" },
  { score: 2, label: "2 — Fans of one team, state, or industry care" },
  { score: 3, label: "3 — Followed across a major sport, politics, or business audience" },
  { score: 4, label: "4 — Most people in a country or big sport pay attention" },
  { score: 5, label: "5 — Household-name story people follow around the world" },
];

const AGREEMENT_FIELD_LABELS: Record<string, string> = {
  subjects: "Named subjects",
  event_date: "Day of the event",
  geography: "Where",
  structure: "Market format",
  claim_frame: "Number and comparison",
  stakes: "How much it matters",
  breadth: "How many people care",
};

const ROLE_LABELS: Record<CuRole, string> = {
  primary: "First person",
  second: "Second person",
  tiebreak: "Tie-breaker",
};

const SPLIT_LABELS: Record<CuSplit, string> = {
  sealed: "Sealed test set",
  dev: "Practice set",
};

const SCOPE_LABELS: Record<CuScope, string> = {
  shared_100: "Shared 100",
  all: "Full set",
};

export default function CuFactLabelingPage() {
  usePageTracking({ pageType: "admin_grade", pageTitle: "Market Fact Check" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  const { secret } = useAdminAuth();

  const [raterInput, setRaterInput] = useState("");
  const [activeRater, setActiveRater] = useState("");
  const [split, setSplit] = useState<CuSplit>("sealed");
  const [role, setRole] = useState<CuRole>("primary");
  const [scope, setScope] = useState<CuScope>("shared_100");
  const [index, setIndex] = useState(0);

  const [queue, setQueue] = useState<CuQueueResponse | null>(null);
  const [agreement, setAgreement] = useState<CuAgreementResponse | null>(null);
  const [showAgreement, setShowAgreement] = useState(false);
  const [showGuidelines, setShowGuidelines] = useState(false);

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
    try {
      const q = await adminFetchJSON<CuQueueResponse>(
        `/api/admin/cu-labeling/queue?split=${split}&role=${role}&scope=${scope}&rater=${encodeURIComponent(activeRater)}`,
        secret
      );
      setQueue(q);
      setIndex(0);
      setDraft(emptyCuDraft());
      setGeoPreset("");
      setCountryInput("");

      const ag = await adminFetchJSON<CuAgreementResponse>(
        `/api/admin/cu-labeling/agreement?split=${split}`,
        secret
      );
      setAgreement(ag);
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
  const measures = useMemo(
    () => queue?.claim_vocabulary?.measures || [...DEFAULT_CLAIM_MEASURES],
    [queue]
  );
  const extraMeasures = useMemo(
    () => measures.filter((m) => !MEASURE_LABELS[m]),
    [measures]
  );
  const comparators = queue?.claim_vocabulary?.comparators || [...DEFAULT_CLAIM_COMPARATORS];
  const horizonKinds = queue?.claim_vocabulary?.horizon_kinds || [...DEFAULT_CLAIM_HORIZON_KINDS];
  const payoutDateSentence = useMemo(
    () => formatPayoutDateSentence(current?.resolution_date),
    [current?.resolution_date]
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
    setActiveRater(norm);
    try {
      window.localStorage.setItem(RATER_STORAGE_KEY, norm);
    } catch {
      // Non-fatal.
    }
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
    const built = buildSubmissionPayload({
      split,
      role,
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
      await adminFetchJSON("/api/admin/cu-labeling/label", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(built.payload),
      });
      setStatusMsg(`Saved your answers for market ${current.market_id}.`);
      setDraft(emptyCuDraft());
      setGeoPreset("");
      setCountryInput("");
      await loadData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save answers");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-5 text-text-primary">
      <div className="space-y-1">
        <h1 className="text-xl font-bold text-text-primary">Market Fact Check</h1>
        <p className="text-sm text-text-secondary">
          Read each market and mark the facts first, then rate how much it matters and how many people care.
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
          <button
            type="button"
            onClick={() => setShowGuidelines((v) => !v)}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-surface-border bg-surface-elevated text-text-secondary hover:text-text-primary"
          >
            {showGuidelines ? "Hide guide" : "Quick guide"}
          </button>
          <button
            type="button"
            onClick={() => setShowAgreement((v) => !v)}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-surface-border bg-surface-elevated text-text-secondary hover:text-text-primary"
          >
            {showAgreement ? "Hide agreement" : "Agreement report"}
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-secondary">Market set:</span>
            {(["sealed", "dev"] as const).map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setSplit(opt)}
                className={`px-2.5 py-1 rounded-md border ${
                  split === opt
                    ? "bg-accent-brand text-text-inverse border-accent-brand"
                    : "bg-surface-deep text-text-secondary border-surface-border"
                }`}
              >
                {SPLIT_LABELS[opt]}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-secondary">Queue:</span>
            {(["shared_100", "all"] as const).map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setScope(opt)}
                className={`px-2.5 py-1 rounded-md border ${
                  scope === opt
                    ? "bg-accent-brand text-text-inverse border-accent-brand"
                    : "bg-surface-deep text-text-secondary border-surface-border"
                }`}
              >
                {SCOPE_LABELS[opt]}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-secondary">Role:</span>
            {(["primary", "second", "tiebreak"] as const).map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setRole(opt)}
                className={`px-2.5 py-1 rounded-md border ${
                  role === opt
                    ? "bg-accent-brand text-text-inverse border-accent-brand"
                    : "bg-surface-deep text-text-secondary border-surface-border"
                }`}
              >
                {ROLE_LABELS[opt]}
              </button>
            ))}
          </div>

          {queue && queue.dataset_file_present && (
            <span className="ml-auto text-text-secondary">
              {queue.completed_by_rater} done / {queue.total_in_scope} in queue ({queue.remaining} left)
            </span>
          )}
        </div>
      </div>

      {showGuidelines && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-xs space-y-2 text-text-secondary">
          <div className="font-semibold text-text-primary text-sm">Quick Fact-Checking Rules</div>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong className="text-text-primary">Label on your own:</strong> Do not compare notes with the other labeler while working.</li>
            <li><strong className="text-text-primary">Named subjects:</strong> Pick the specific people, teams, bills, or things named. Pick Custom if missing, &quot;None of these&quot; for indexes/weather highs, or &quot;Not sure&quot;.</li>
            <li><strong className="text-text-primary">Day of the event:</strong> Enter the day the real event happens, not the site&apos;s payout timestamp; check &quot;No single day&quot; for season winners or multi-week deadlines.</li>
            <li><strong className="text-text-primary">Where:</strong> City, county, and state legislative districts are <code>Local</code>; cross-border tournaments like World Cup or UEFA Europa League are <code>Global</code>.</li>
            <li><strong className="text-text-primary">Format &amp; Claim:</strong> Check the option list before choosing Ladder or Dated options. Copy exact numbers from the title — do not pull 27 from &quot;2026-27&quot; or 7M from &quot;W7M&quot;.</li>
            <li><strong className="text-text-primary">Tie-breaker:</strong> Only reviews disagreements on facts using exact text evidence. Never tie-breaks the two 1–5 opinion ratings.</li>
          </ul>
        </div>
      )}

      {showAgreement && agreement && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-semibold">
              How often the two labelers agreed ({SPLIT_LABELS[split]})
            </span>
            <span className="text-xs text-text-secondary">
              Double-checked: {agreement.paired_markets} · Waiting for tie-breaker:{" "}
              {agreement.needs_tiebreak} · Resolved: {agreement.resolved_tiebreaks}
            </span>
          </div>
          <div className="overflow-x-auto">
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
                    <td className="py-1.5 pr-3 text-text-secondary">
                      {f.metric === "within_1" ? "Within 1 step" : "Exact match"}
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
                        <span className="text-text-secondary">
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
        <div className="px-4 py-2.5 rounded-lg border border-accent-brand bg-surface-card text-accent-brand text-sm">
          {statusMsg}
        </div>
      )}

      {!activeRater ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-secondary">
          Type your name above and click <strong>Start labeling</strong> to load your cards.
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
          <p className="text-text-secondary">
            {queue.dataset_file_missing_message ||
              "The frozen market list for this set is not loaded on this server yet, so there are no cards to check."}
          </p>
        </div>
      ) : !current ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-secondary">
          No remaining markets in this queue ({SPLIT_LABELS[split]} · {ROLE_LABELS[role]} · {SCOPE_LABELS[scope]}).
        </div>
      ) : (
        <div className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-5">
          {/* Market card */}
          <div className="border-b border-surface-border pb-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-secondary">
              <span>
                Market {current.market_id} · {current.source || "unknown"} · {current.category || "uncategorized"}
              </span>
              <span>
                Card {index + 1} of {items.length}
              </span>
            </div>
            <h2 className="text-lg font-semibold text-text-primary">{current.title}</h2>
            {payoutDateSentence && (
              <div className="text-sm text-text-primary">{payoutDateSentence}</div>
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
              </div>
            ) : (
              <div className="text-sm text-text-secondary pt-1">No options listed</div>
            )}
            {current.rules_text && (
              <p className="text-xs text-text-secondary bg-surface-deep p-3 rounded-lg border border-surface-border whitespace-pre-wrap">
                {current.rules_text}
              </p>
            )}
          </div>

          {/* Blind vs Tiebreak peer panel */}
          {role !== "tiebreak" ? (
            <div className="text-xs text-text-muted">
              Blind check active: neither labeler ever sees what the other answered.
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
                  <div key={`${peer.rater}-${peer.role}`} className="bg-surface-card border border-surface-border rounded-lg p-2.5 space-y-1">
                    <div className="font-semibold text-text-primary">
                      {peer.rater} ({ROLE_LABELS[peer.role]})
                    </div>
                    <div>Subjects: {JSON.stringify(peer.subjects_answer)}</div>
                    <div>Day: {peer.no_single_day ? "No single day" : peer.event_date_answer || "blank"}</div>
                    <div>Where: {peer.geography_answer || "blank"}</div>
                    <div>Format: {peer.structure_answer || "blank"}</div>
                    <div>
                      Number &amp; comparison:{" "}
                      {formatPeerClaimFrame(peer.claim_frame as Record<string, unknown> | null)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Question 1: Subjects */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">1. Who or what is it about?</div>
            <div className="flex flex-wrap gap-1.5">
              {current.subject_candidates.map((cand) => {
                const active = draft.subjectMode === "candidate" && draft.selectedCandidates.includes(cand);
                return (
                  <button
                    key={cand}
                    type="button"
                    onClick={() => toggleCandidate(cand)}
                    className={`px-2.5 py-1 text-xs rounded-md border ${
                      active
                        ? "bg-accent-brand text-text-inverse border-accent-brand"
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
                  onClick={() => setDraft((d) => ({ ...d, subjectMode: mode }))}
                  className={`px-2.5 py-1 text-xs rounded-md border ${
                    draft.subjectMode === mode
                      ? "bg-accent-brand text-text-inverse border-accent-brand"
                      : "bg-surface-elevated text-text-secondary border-surface-border"
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

          {/* Question 2: Event's own day */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">2. The event&apos;s own day</div>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="date"
                disabled={draft.noSingleDay}
                value={draft.eventDate}
                onChange={(e) => setDraft((d) => ({ ...d, eventDate: e.target.value, noSingleDay: false }))}
                className="px-3 py-1.5 text-sm bg-surface-deep border border-surface-border rounded-lg disabled:opacity-50"
              />
              <label className="flex items-center gap-2 text-xs font-medium text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={draft.noSingleDay}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      noSingleDay: e.target.checked,
                      eventDate: e.target.checked ? "" : d.eventDate,
                    }))
                  }
                />
                No single day
              </label>
            </div>
          </div>

          {/* Question 3: Geography */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">3. Where</div>
            <div className="flex flex-wrap items-center gap-2">
              {GEO_PRESETS.map((g) => (
                <button
                  key={g.value}
                  type="button"
                  onClick={() => setGeoPreset(g.value)}
                  className={`px-3 py-1 text-xs rounded-md border ${
                    geoPreset === g.value
                      ? "bg-accent-brand text-text-inverse border-accent-brand"
                      : "bg-surface-deep text-text-primary border-surface-border"
                  }`}
                >
                  {g.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setGeoPreset("country")}
                className={`px-3 py-1 text-xs rounded-md border ${
                  geoPreset === "country"
                    ? "bg-accent-brand text-text-inverse border-accent-brand"
                    : "bg-surface-deep text-text-primary border-surface-border"
                }`}
              >
                One country
              </button>
              {geoPreset === "country" && (
                <select
                  aria-label="Country"
                  value={countryInput}
                  onChange={(e) => setCountryInput(e.target.value)}
                  className="px-3 py-1.5 text-sm bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                >
                  <option value="">Choose a country...</option>
                  {COUNTRY_OPTIONS.map((c) => (
                    <option key={c.code} value={`country:${c.code}`}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Question 4: Market format */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">4. Market format</div>
            <div className="grid sm:grid-cols-3 gap-2">
              {STRUCTURE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setDraft((d) => ({ ...d, structure: opt.value }))}
                  className={`p-3 text-left rounded-lg border text-sm ${
                    draft.structure === opt.value
                      ? "bg-accent-brand text-text-inverse border-accent-brand"
                      : "bg-surface-deep text-text-primary border-surface-border"
                  }`}
                >
                  <div className="font-semibold">{opt.label}</div>
                  <div
                    className={`mt-1 text-sm ${
                      draft.structure === opt.value ? "text-text-inverse" : "text-text-primary"
                    }`}
                  >
                    {opt.help}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Question 5: Number and comparison (6 fixed writer slots) */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">
              5. Number and comparison (if the title states a specific figure; otherwise leave blank)
            </div>
            <p className="text-xs text-text-secondary">
              Put currency signs ($, £, €) or % in Unit, and the plain number in Exact number.
            </p>
            <div className="grid sm:grid-cols-3 gap-2.5">
              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">What is measured</label>
                <select
                  value={draft.claim.measure}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, measure: e.target.value } }))
                  }
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                >
                  <option value="">Blank (no numeric claim)</option>
                  <option value="none_of_these">None of these</option>
                  {MEASURE_GROUPS.map((grp) => (
                    <optgroup key={grp.group} label={grp.group}>
                      {grp.options
                        .filter((opt) => measures.includes(opt.value))
                        .map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                    </optgroup>
                  ))}
                  {extraMeasures.length > 0 && (
                    <optgroup label="Other">
                      {extraMeasures.map((m) => (
                        <option key={m} value={m}>
                          {formatMeasureChoiceLabel(m)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>

              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">Comparison</label>
                <select
                  value={draft.claim.comparator}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, comparator: e.target.value } }))
                  }
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                >
                  <option value="">Blank</option>
                  <option value="none_of_these">None of these</option>
                  {comparators.map((cmp) => (
                    <option key={cmp} value={cmp}>
                      {COMPARATOR_LABELS[cmp] || cmp}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">Exact number (verbatim from title)</label>
                <input
                  type="text"
                  value={draft.claim.value}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, value: e.target.value } }))
                  }
                  placeholder="e.g. 50000 or 13M"
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">Unit (verbatim from title)</label>
                <input
                  type="text"
                  value={draft.claim.unit}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, unit: e.target.value } }))
                  }
                  placeholder="e.g. $, %, goals, subscribers"
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg"
                />
              </div>

              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">Kind of deadline</label>
                <select
                  value={draft.claim.horizon_kind}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, horizon_kind: e.target.value } }))
                  }
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg text-text-primary"
                >
                  <option value="">Blank</option>
                  <option value="none_of_these">None of these</option>
                  {horizonKinds.map((hk) => (
                    <option key={hk} value={hk}>
                      {HORIZON_LABELS[hk] || hk}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="block text-xs text-text-secondary">Written deadline date in title</label>
                <input
                  type="text"
                  value={draft.claim.window_date}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, window_date: e.target.value } }))
                  }
                  placeholder="e.g. December 31, 2027"
                  className="w-full px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg"
                />
              </div>
            </div>
          </div>

          {/* Question 6: How much it matters & how many people care (asked last, hidden in tiebreak) */}
          {role !== "tiebreak" ? (
            <div className="space-y-4 pt-2 border-t border-surface-border">
              <div className="text-sm font-semibold">
                6. How much it matters and how many people care (answer last)
              </div>
              <div className="grid md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-text-primary">How much this matters</div>
                  <div className="flex gap-1.5">
                    {STAKES_ANCHORS.map((item) => (
                      <button
                        key={item.score}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, stakes: item.score }))}
                        className={`w-8 h-8 text-xs font-semibold rounded-md border ${
                          draft.stakes === item.score
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {item.score}
                      </button>
                    ))}
                  </div>
                  <ul className="space-y-1 text-sm text-text-primary">
                    {STAKES_ANCHORS.map((item) => (
                      <li key={item.score}>{item.label}</li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-text-primary">How many people care</div>
                  <div className="flex gap-1.5">
                    {BREADTH_ANCHORS.map((item) => (
                      <button
                        key={item.score}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, breadth: item.score }))}
                        className={`w-8 h-8 text-xs font-semibold rounded-md border ${
                          draft.breadth === item.score
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {item.score}
                      </button>
                    ))}
                  </div>
                  <ul className="space-y-1 text-sm text-text-primary">
                    {BREADTH_ANCHORS.map((item) => (
                      <li key={item.score}>{item.label}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-2 pt-2 border-t border-surface-border">
              <div className="text-sm font-semibold">Written evidence note (required for tie-break)</div>
              <textarea
                rows={3}
                value={draft.evidenceNote}
                onChange={(e) => setDraft((d) => ({ ...d, evidenceNote: e.target.value }))}
                placeholder="Quote the exact phrase in the title, options, or rules showing which fact answer holds."
                className="w-full px-3 py-2 text-sm bg-surface-deep border border-surface-border rounded-lg"
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="flex gap-2">
              <button
                type="button"
                disabled={index <= 0}
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                className="px-3 py-1.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-secondary disabled:opacity-40"
              >
                Prev
              </button>
              <button
                type="button"
                disabled={index >= items.length - 1}
                onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}
                className="px-3 py-1.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-secondary disabled:opacity-40"
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
              {submitting ? "Saving..." : role === "tiebreak" ? "Save fact tie-break" : "Save answers"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
