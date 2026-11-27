"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";
import {
  buildSubmissionPayload,
  emptyCuDraft,
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
  { value: "ladder", label: "Ladder of one number", help: "Above/below thresholds of one underlying value" },
  { value: "dated_bucket", label: "Set of dated options", help: "Different deadline dates for one outcome" },
  { value: "neither", label: "Neither", help: "Plain binary, matchup, or candidate field" },
];

const GEO_PRESETS = ["us", "global", "local"] as const;
const SCALE_STEPS = [1, 2, 3, 4, 5] as const;

export default function CuFactLabelingPage() {
  usePageTracking({ pageType: "admin_grade", pageTitle: "CU Fact Pass" });
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
      setErrorMsg("Enter a labeler name (1-64 characters).");
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
      setStatusMsg(`Saved label for market #${current.market_id}.`);
      setDraft(emptyCuDraft());
      setGeoPreset("");
      setCountryInput("");
      await loadData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save label");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-5 text-text-primary">
      <div className="space-y-1">
        <h1 className="text-xl font-bold text-text-primary">CU Fact Labeling Pass</h1>
        <p className="text-sm text-text-secondary">
          Blind dual-rater facts first, taste last, plus evidence-based fact tiebreak (#13900).
        </p>
      </div>

      {/* Typed labeler identity & queue controls */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-4">
        <form onSubmit={applyTypedName} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-semibold uppercase tracking-wide text-text-secondary mb-1">
              Labeler name (typed, stored in your session)
            </label>
            <input
              type="text"
              value={raterInput}
              onChange={(e) => setRaterInput(e.target.value)}
              placeholder="Type your name or handle"
              maxLength={64}
              className="w-full px-3 py-2 text-sm bg-surface-deep border border-surface-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-brand"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-brand text-text-inverse hover:opacity-90 transition-opacity"
          >
            Set labeler
          </button>
          <button
            type="button"
            onClick={() => setShowGuidelines((v) => !v)}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-surface-border bg-surface-elevated text-text-secondary hover:text-text-primary"
          >
            {showGuidelines ? "Hide guidelines" : "1-page guidelines"}
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
            <span className="font-semibold text-text-secondary">Split:</span>
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
                {opt}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-secondary">Scope:</span>
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
                {opt === "shared_100" ? "Shared 100" : "All"}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-secondary">Pass:</span>
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
                {opt}
              </button>
            ))}
          </div>

          {queue && (
            <span className="ml-auto text-text-secondary">
              {queue.completed_by_rater} done / {queue.total_in_scope} in scope ({queue.remaining} left)
            </span>
          )}
        </div>
      </div>

      {showGuidelines && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-xs space-y-2 text-text-secondary">
          <div className="font-semibold text-text-primary text-sm">Quick Fact-Labeling Rules (#1809 Rounds 1–5)</div>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong className="text-text-primary">Subjects:</strong> Name the specific team/person/asset; choose custom if absent from chips, &quot;none of these&quot; for indexes/temps, or &quot;not sure&quot;.</li>
            <li><strong className="text-text-primary">Event day:</strong> Use the event&apos;s real calendar day, not the exchange settlement timestamp; mark &quot;No single day&quot; for open-ended deadlines or season winners.</li>
            <li><strong className="text-text-primary">Where:</strong> State legislative seats and municipal races are <code>local</code> (and stakes=1, breadth=1); cross-border tournaments (Europa/UCL/World Cup) are <code>global</code>.</li>
            <li><strong className="text-text-primary">Structure &amp; Claim:</strong> Check options before picking <code>ladder</code> / <code>dated_bucket</code> / <code>neither</code>. Copy claim value/unit verbatim from title — never parse &quot;2026-27&quot; or &quot;W7M&quot; as numbers.</li>
            <li><strong className="text-text-primary">Tiebreak:</strong> Applies to fact fields only with required written evidence. <code>stakes</code> and <code>breadth</code> are never tie-broken.</li>
          </ul>
        </div>
      )}

      {showAgreement && agreement && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-semibold">Dual-Rater Agreement ({agreement.split})</span>
            <span className="text-xs text-text-secondary">
              Paired: {agreement.paired_markets} · Needs tiebreak: {agreement.needs_tiebreak} · Resolved tiebreaks: {agreement.resolved_tiebreaks}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-surface-border text-text-secondary text-left">
                  <th className="py-1.5 pr-3">Field</th>
                  <th className="py-1.5 pr-3">Rule</th>
                  <th className="py-1.5 pr-3">Agreed</th>
                  <th className="py-1.5 pr-3">Total</th>
                  <th className="py-1.5 pr-3">Rate</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {agreement.fields.map((f) => (
                  <tr key={f.field} className="border-b border-surface-border">
                    <td className="py-1.5 pr-3 font-medium text-text-primary">{f.field}</td>
                    <td className="py-1.5 pr-3 text-text-secondary">{f.metric}</td>
                    <td className="py-1.5 pr-3">{f.agreed}</td>
                    <td className="py-1.5 pr-3">{f.total}</td>
                    <td className="py-1.5 pr-3">
                      {f.agreement_rate === null ? "—" : `${(f.agreement_rate * 100).toFixed(1)}%`}
                    </td>
                    <td className="py-1.5">
                      {f.below_80_pct ? (
                        <span className="text-accent-danger font-semibold">Below 80% — send to Alex</span>
                      ) : (
                        <span className="text-text-secondary">{f.tiebreak_allowed ? "Fact" : "Taste (Alex owns)"}</span>
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
          Type your labeler name above and click <strong>Set labeler</strong> to load your blind queue.
        </div>
      ) : loading ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted animate-pulse">
          Loading {split} queue...
        </div>
      ) : !current ? (
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-secondary">
          No remaining markets in this queue ({split} · {role} · {scope}).
        </div>
      ) : (
        <div className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-5">
          {/* Market card */}
          <div className="border-b border-surface-border pb-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-secondary">
              <span>
                Market #{current.market_id} · {current.source || "unknown"} · {current.category || "uncategorized"}
              </span>
              <span>
                Card {index + 1} of {items.length}
              </span>
            </div>
            <h2 className="text-lg font-semibold text-text-primary">{current.title}</h2>
            {current.resolution_date && (
              <div className="text-xs text-text-muted">
                Source settlement timestamp: {current.resolution_date}
              </div>
            )}
            {current.outcomes.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {current.outcomes.slice(0, 16).map((o, idx) => (
                  <span
                    key={`${o.name}-${idx}`}
                    className="px-2 py-0.5 text-xs rounded-md bg-surface-elevated border border-surface-border text-text-primary"
                  >
                    {o.name}
                    {typeof o.prob === "number" ? ` (${Math.round(o.prob * 100)}%)` : ""}
                  </span>
                ))}
              </div>
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
              Blind mode active: peer answers remain hidden until both primary and second finish.
            </div>
          ) : (
            <div className="bg-surface-elevated border border-surface-border rounded-lg p-3 space-y-2 text-xs">
              <div className="font-semibold text-text-primary">
                Disagreeing fact fields: {current.disagreeing_fact_fields.join(", ")} (taste excluded)
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                {current.peer_labels.map((peer) => (
                  <div key={`${peer.rater}-${peer.role}`} className="bg-surface-card border border-surface-border rounded-lg p-2.5 space-y-1">
                    <div className="font-semibold text-text-primary">
                      {peer.rater} ({peer.role})
                    </div>
                    <div>Subjects: {JSON.stringify(peer.subjects_answer)}</div>
                    <div>Day: {peer.no_single_day ? "No single day" : peer.event_date_answer || "blank"}</div>
                    <div>Where: {peer.geography_answer || "blank"}</div>
                    <div>Structure: {peer.structure_answer || "blank"}</div>
                    <div>Claim: {peer.claim_frame ? JSON.stringify(peer.claim_frame) : "blank"}</div>
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
                placeholder="Comma-separated subjects from the text"
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
                  key={g}
                  type="button"
                  onClick={() => setGeoPreset(g)}
                  className={`px-3 py-1 text-xs rounded-md border ${
                    geoPreset === g
                      ? "bg-accent-brand text-text-inverse border-accent-brand"
                      : "bg-surface-deep text-text-primary border-surface-border"
                  }`}
                >
                  {g}
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
                Country
              </button>
              {geoPreset === "country" && (
                <input
                  type="text"
                  value={countryInput}
                  onChange={(e) => setCountryInput(e.target.value)}
                  placeholder="e.g. country:GB or Canada"
                  className="px-3 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg"
                />
              )}
            </div>
          </div>

          {/* Question 4: Structure */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">4. Structure</div>
            <div className="grid sm:grid-cols-3 gap-2">
              {STRUCTURE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setDraft((d) => ({ ...d, structure: opt.value }))}
                  className={`p-2.5 text-left rounded-lg border text-xs ${
                    draft.structure === opt.value
                      ? "bg-accent-brand text-text-inverse border-accent-brand"
                      : "bg-surface-deep text-text-primary border-surface-border"
                  }`}
                >
                  <div className="font-semibold">{opt.label}</div>
                  <div className={draft.structure === opt.value ? "opacity-90" : "text-text-secondary"}>
                    {opt.help}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Question 5: Claim */}
          <div className="space-y-2">
            <div className="text-sm font-semibold">5. The claim (copied verbatim from text, or blank)</div>
            <div className="grid sm:grid-cols-5 gap-2">
              {(["measure", "comparison", "value", "unit", "deadline"] as const).map((slot) => (
                <input
                  key={slot}
                  type="text"
                  value={draft.claim[slot]}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, claim: { ...d.claim, [slot]: e.target.value } }))
                  }
                  placeholder={slot}
                  className="px-2.5 py-1.5 text-xs bg-surface-deep border border-surface-border rounded-lg"
                />
              ))}
            </div>
          </div>

          {/* Question 6: Stakes and breadth (hidden in tiebreak) OR required tiebreak evidence */}
          {role !== "tiebreak" ? (
            <div className="space-y-3 pt-2 border-t border-surface-border">
              <div className="text-sm font-semibold">6. Stakes and breadth (1–5, asked last)</div>
              <div className="flex flex-wrap gap-6">
                <div className="space-y-1">
                  <div className="text-xs font-medium text-text-secondary">Stakes (1–5)</div>
                  <div className="flex gap-1.5">
                    {SCALE_STEPS.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, stakes: n }))}
                        className={`w-8 h-8 text-xs font-semibold rounded-md border ${
                          draft.stakes === n
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-xs font-medium text-text-secondary">Breadth (1–5)</div>
                  <div className="flex gap-1.5">
                    {SCALE_STEPS.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, breadth: n }))}
                        className={`w-8 h-8 text-xs font-semibold rounded-md border ${
                          draft.breadth === n
                            ? "bg-accent-brand text-text-inverse border-accent-brand"
                            : "bg-surface-deep text-text-primary border-surface-border"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-2 pt-2 border-t border-surface-border">
              <div className="text-sm font-semibold">Written evidence note (required for tiebreak)</div>
              <textarea
                rows={3}
                value={draft.evidenceNote}
                onChange={(e) => setDraft((d) => ({ ...d, evidenceNote: e.target.value }))}
                placeholder="Quote the exact phrase in title/options/rules proving which fact answer holds."
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
              {submitting ? "Saving..." : role === "tiebreak" ? "Save fact tiebreak" : "Save label"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
