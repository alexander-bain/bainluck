"use client";

/**
 * #12373 (Epic #12288, Plan #12221 row 6) — /grade/groupings: a private page,
 * behind admin sign-in, showing each proposed grouping card beside its best
 * single member.
 *
 * A grader answers one question: is the card worth more than the single?
 * (`amazing` / `fine` / `no`). Kid graders are pseudonyms only (`kid1`..`kid4`),
 * never names.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import {
  VisualFormLookSheetGallery,
  renderVisualLookSheetDeckItem,
} from "@/components/discover/forms/VisualFormLookSheet";
import { RoundupCard } from "@/components/discover/roundup/RoundupCard";
import { buildRoundupCardModel } from "@/lib/discover/roundupCard";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  GROUPING_GRADES,
  GROUPING_GRADE_LABELS,
  KID_PSEUDONYMS,
  buildRoundupContractForProposedCard,
  formatTally,
  handleGradeDeckReadError,
  resolveGroupingGraderId,
  type GroupingGrade,
  type GroupingGradeDeck,
  type GroupingGradeSummary,
  type KidPseudonym,
  type TallyEntry,
} from "@/lib/ranking/groupingGradeSession";
import { saveWithOneRetry } from "@/lib/ranking/gradeSession";
import { useRetryNotice } from "@/lib/ranking/useRetryNotice";

const GRADER_KEY = "bainluck_grouping_grader_name";
const KID_KEY = "bainluck_grouping_grader_kid";
const KID_SLOT_KEY = "bainluck_grouping_grader_kid_slot";

export default function GroupingGradePage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <GroupingGradeSession />
    </AdminAuthProvider>
  );
}

function GroupingGradeSession() {
  const { secret, clearSecret } = useAdminAuth();
  const [deck, setDeck] = useState<GroupingGradeDeck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [kid, setKid] = useState(false);
  const [kidSlot, setKidSlot] = useState<KidPseudonym>("kid1");
  const [grader, setGrader] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const [graded, setGraded] = useState(0);
  const [saving, setSaving] = useState(false);
  const [tally, setTally] = useState<TallyEntry[]>([]);
  const [summary, setSummary] = useState<GroupingGradeSummary | null>(null);
  const [existingGrades, setExistingGrades] = useState<
    Array<{ grader: string; item_key: string; grade?: GroupingGrade }>
  >([]);
  const [savingItemKey, setSavingItemKey] = useState<string | null>(null);
  const { notice, startWait, clearNotice } = useRetryNotice();
  const [selectedSlate, setSelectedSlate] = useState<string>(() => {
    if (typeof window !== "undefined") {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get("view") === "look-sheet") {
        return "visual-forms-look-sheet-2026-11";
      }
      return sp.get("slate") || sp.get("slate_id") || "grouping-candidates-2026-11";
    }
    return "grouping-candidates-2026-11";
  });

  useEffect(() => {
    try {
      setNameInput(localStorage.getItem(GRADER_KEY) || "");
      setKid(localStorage.getItem(KID_KEY) === "1");
      const savedSlot = localStorage.getItem(KID_SLOT_KEY) as KidPseudonym | null;
      if (savedSlot && KID_PSEUDONYMS.includes(savedSlot)) {
        setKidSlot(savedSlot);
      }
    } catch {
      // storage unavailable
    }
  }, []);

  const loadTallyAndSummary = useCallback(
    async (slateId: string) => {
      try {
        const res = await adminFetchJSON<{
          grades?: Array<{ grader: string; item_key: string }>;
          tally: TallyEntry[];
          summary: GroupingGradeSummary;
        }>(
          `/api/admin/ranking/grouping-grades?slate_id=${encodeURIComponent(slateId)}&days=30`,
          secret,
        );
        setExistingGrades(res.grades || []);
        setTally(res.tally || []);
        setSummary(res.summary || null);
      } catch {
        // non-blocking
      }
    },
    [secret],
  );

  useEffect(() => {
    let cancelled = false;
    const deckUrl =
      selectedSlate && selectedSlate !== "grouping-candidates-2026-11"
        ? `/api/admin/ranking/grouping-deck?slate_id=${encodeURIComponent(selectedSlate)}`
        : "/api/admin/ranking/grouping-deck";
    adminFetchJSON<GroupingGradeDeck>(deckUrl, secret)
      .then((d) => {
        if (cancelled) return;
        setDeck(d);
        void loadTallyAndSummary(d.slate_id);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        handleGradeDeckReadError(e, "Could not load proposed grouping cards", {
          clearSecret,
          setError,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [secret, selectedSlate, loadTallyAndSummary, clearSecret]);

  const resolvedGrader = resolveGroupingGraderId(nameInput, kid, kidSlot);

  const start = () => {
    if (!resolvedGrader) return;
    try {
      if (!kid) {
        localStorage.setItem(GRADER_KEY, resolvedGrader);
      } else {
        localStorage.removeItem(GRADER_KEY);
        localStorage.setItem(KID_SLOT_KEY, kidSlot);
      }
      localStorage.setItem(KID_KEY, kid ? "1" : "0");
    } catch {
      // storage unavailable
    }
    setGrader(resolvedGrader);
    const graderLower = resolvedGrader.toLowerCase();
    const gradedKeys = new Set(
      existingGrades
        .filter((g) => (g.grader || "").toLowerCase() === graderLower)
        .map((g) => g.item_key),
    );
    const firstUngradedIdx = deck
      ? deck.items.findIndex((it) => !gradedKeys.has(it.item_key))
      : 0;
    setIndex(firstUngradedIdx >= 0 ? firstUngradedIdx : 0);
    setGraded(0);
  };

  const submit = async (grade: GroupingGrade) => {
    if (!deck || !grader || saving) return;
    const item = deck.items[index];
    setSaving(true);
    setError(null);
    try {
      const body = JSON.stringify({
        slate_id: deck.slate_id,
        grader,
        kid,
        position: item.position,
        item_key: item.item_key,
        grade,
        note: note.trim() || null,
      });
      // #11937: a rate-limited save waits what the server asks and goes again once.
      const res = await saveWithOneRetry(
        () => adminFetch("/api/admin/ranking/grouping-grades", secret, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        }),
        (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        startWait,
      );
      clearNotice();
      if (!res.ok) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      setGraded((n) => n + 1);
      setNote("");
      setIndex((i) => i + 1);
      void loadTallyAndSummary(deck.slate_id);
    } catch {
      clearNotice();
      setError("Not saved: the network dropped. Try that card again.");
    } finally {
      setSaving(false);
    }
  };

  const tallyLine = formatTally(tally);
  // #11937: the wait line and any "Not saved" line, under the deck or the look
  // sheet (whose saves showed nothing at all when they failed).
  const saveStatus = (
    <>
      {notice && <p className="mt-2 text-sm text-text-muted" role="status">{notice}</p>}
      {error && <p className="mt-2 text-sm text-text-secondary">{error}</p>}
    </>
  );
  const isLookSheetSlate = selectedSlate === "visual-forms-look-sheet-2026-11";
  const activeGraderForLookSheet = grader || resolvedGrader || null;
  const existingGradesByItemKey: Record<string, GroupingGrade> = {};
  if (activeGraderForLookSheet) {
    const gLower = activeGraderForLookSheet.toLowerCase();
    for (const g of existingGrades) {
      if ((g.grader || "").toLowerCase() === gLower && g.grade) {
        existingGradesByItemKey[g.item_key] = g.grade;
      }
    }
  }

  const submitLookSheetItemGrade = async (
    position: number,
    itemKey: string,
    grade: GroupingGrade,
    itemNote: string,
  ) => {
    const targetGrader = grader || resolvedGrader;
    if (!targetGrader || savingItemKey) return;
    setSavingItemKey(itemKey);
    setError(null);
    try {
      const body = JSON.stringify({
        slate_id: "visual-forms-look-sheet-2026-11",
        grader: targetGrader,
        kid,
        position,
        item_key: itemKey,
        grade,
        note: itemNote.trim() || null,
      });
      const res = await saveWithOneRetry(
        () => adminFetch("/api/admin/ranking/grouping-grades", secret, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        }),
        (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        startWait,
      );
      clearNotice();
      if (!res.ok) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      setGraded((n) => n + 1);
      setExistingGrades((prev) => [
        ...prev.filter(
          (x) =>
            !(
              (x.grader || "").toLowerCase() === targetGrader.toLowerCase() &&
              x.item_key === itemKey
            ),
        ),
        { grader: targetGrader, item_key: itemKey, grade },
      ]);
      void loadTallyAndSummary("visual-forms-look-sheet-2026-11");
    } catch {
      clearNotice();
      setError("Not saved: the network dropped. Try that card again.");
    } finally {
      setSavingItemKey(null);
    }
  };

  if (error && !deck && !isLookSheetSlate) {
    return (
      <Shell>
        <p className="text-sm text-text-secondary">{error}</p>
      </Shell>
    );
  }
  if (!deck && !isLookSheetSlate) {
    return (
      <Shell>
        <p className="text-sm text-text-muted animate-pulse">Loading proposed grouping cards…</p>
      </Shell>
    );
  }

  if (!grader) {
    const cardCount = isLookSheetSlate ? 15 : (deck?.items.length ?? 0);
    return (
      <Shell tally={tallyLine} summary={summary}>
        <h1 className="text-xl font-semibold text-text-primary">Who&apos;s grading proposed cards?</h1>
        <p className="mt-1 text-sm text-text-secondary">
          {cardCount} proposed grouping cards shown beside each card&apos;s best single member.
          One question per pair: is the card worth more than the single?
        </p>

        <div className="mt-3 flex flex-wrap gap-2" data-testid="grouping-slate-selector">
          {[
            { id: "grouping-candidates-2026-11", label: "Proposed candidates (32)" },
            { id: "sibling-family-exam-test-2026-11", label: "Sibling-family exam (20)" },
            { id: "new-kinds-exam-test-2026-11", label: "New-kinds exam (20)" },
            { id: "visual-forms-look-sheet-2026-11", label: "Visual forms look sheet (15)" },
          ].map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setSelectedSlate(opt.id)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                selectedSlate === opt.id
                  ? "border-accent-brand bg-accent-brand text-text-inverse"
                  : "border-surface-border bg-surface-card text-text-primary"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm font-medium text-text-secondary">
          <input
            type="checkbox"
            checked={kid}
            onChange={(e) => {
              setKid(e.target.checked);
              if (e.target.checked) {
                setNameInput("");
              }
            }}
          />
          Kid grader (uses pseudonym only — names are never stored)
        </label>

        {kid ? (
          <div className="mt-3">
            <div className="text-xs font-medium text-text-muted">Choose kid pseudonym</div>
            <div className="mt-2 grid grid-cols-4 gap-2">
              {KID_PSEUDONYMS.map((slot) => (
                <button
                  key={slot}
                  type="button"
                  onClick={() => setKidSlot(slot)}
                  className={`rounded-lg border px-3 py-2 text-sm font-semibold ${
                    kidSlot === slot
                      ? "border-accent-brand bg-accent-brand text-text-inverse"
                      : "border-surface-border bg-surface-card text-text-primary"
                  }`}
                >
                  {slot}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <input
            className="mt-3 w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-text-primary"
            placeholder="Your name (adults/friends)"
            value={nameInput}
            maxLength={40}
            onChange={(e) => setNameInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") start();
            }}
          />
        )}

        <button
          className="mt-4 w-full rounded-lg bg-accent-brand px-4 py-2 font-semibold text-text-inverse disabled:opacity-50"
          disabled={!resolvedGrader || !deck}
          onClick={start}
        >
          Start ({cardCount} cards)
        </button>

        {isLookSheetSlate && (
          <div className="mt-6 border-t border-surface-border pt-6">
            <VisualFormLookSheetGallery
              kidSurface={kid}
              grader={activeGraderForLookSheet}
              existingGradesByItemKey={existingGradesByItemKey}
              pairedMetricSets={deck?.paired_metric_sets ?? null}
              onGradeItem={submitLookSheetItemGrade}
              savingItemKey={savingItemKey}
            />
            {saveStatus}
          </div>
        )}
      </Shell>
    );
  }

  if (!deck) {
    return (
      <Shell tally={tallyLine} summary={summary}>
        <VisualFormLookSheetGallery
          kidSurface={kid}
          grader={activeGraderForLookSheet}
          existingGradesByItemKey={existingGradesByItemKey}
          pairedMetricSets={null}
          onGradeItem={submitLookSheetItemGrade}
          savingItemKey={savingItemKey}
        />
        {saveStatus}
      </Shell>
    );
  }

  if (index >= deck.items.length) {
    return (
      <Shell tally={tallyLine} summary={summary}>
        <h1 className="text-xl font-semibold text-text-primary">
          All {deck.items.length} proposed cards graded. Thanks, {grader}!
        </h1>
        <button
          className="mt-4 text-sm font-semibold text-accent-brand hover:underline"
          onClick={() => setGrader(null)}
        >
          Next grader
        </button>
      </Shell>
    );
  }

  const item = deck.items[index];
  const card = item.proposed_card;
  const single = item.best_single;
  const lookSheetCustomNode = renderVisualLookSheetDeckItem(item.item_key, {
    kidSurface: kid,
    pairedMetricSet: item.paired_metric_set ?? null,
    pairedMetricSets: deck.paired_metric_sets ?? null,
  });
  const roundupContract = buildRoundupContractForProposedCard(card);
  const canRenderRoundupCard =
    buildRoundupCardModel(card.title, roundupContract).model !== null;

  return (
    <Shell tally={tallyLine} summary={summary}>
      <div className="flex items-baseline justify-between text-sm text-text-secondary">
        <span>
          {grader}
          {kid ? " (kid pseudonym)" : ""} · card {index + 1} of {deck.items.length}
        </span>
        <span>{graded} graded</span>
      </div>

      <p className="mt-2 text-base font-semibold text-text-primary">
        Is this grouping card worth more than its best single member?
      </p>

      <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Left: Proposed Grouping Card */}
        <div
          className="space-y-2"
          aria-label="Proposed grouping card"
        >
          <div className="flex items-center justify-between px-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>
              Proposed Grouping Card
              {item.proposed_kind && item.proposed_kind !== "sibling_family"
                ? ` · New Kind (${item.proposed_kind})`
                : ""}
            </span>
            <span>
              {item.proposed_kind && item.proposed_kind !== "sibling_family"
                ? "Kind: PROPOSED · not licensed"
                : item.kind_verdict === "serve"
                  ? "Kind: SERVE"
                  : `Kind: REFUSE (${item.refusal_reasons.join(", ")})`}
            </span>
          </div>
          {(item.as_of_label || card.as_of_label) && (
            <div className="px-1 text-xs font-medium text-text-secondary" data-testid="card-as-of-label">
              Snapshot {item.as_of_label || card.as_of_label}
            </div>
          )}
          {lookSheetCustomNode ? (
            <div className="pointer-events-none">{lookSheetCustomNode}</div>
          ) : canRenderRoundupCard ? (
            <div className="pointer-events-none">
              <RoundupCard
                title={card.title}
                contract={roundupContract}
                collectionRef={null}
                items={[]}
                bundleId={`grade:${item.item_key}`}
                previewOnly
              />
            </div>
          ) : (
            <div className="rounded-xl border border-surface-border bg-surface-card p-4">
              <h2 className="mt-1.5 text-lg font-semibold text-text-primary">{card.title}</h2>
              <div className="mt-3 divide-y divide-surface-border">
                {card.rows.map((row) => (
                  <div key={`${row.market_id}-${row.label}`} className="flex items-center justify-between py-2 text-sm">
                    <span className="font-medium text-text-primary">{row.label}</span>
                    <span className="font-semibold tabular-nums text-text-primary">{row.value}</span>
                  </div>
                ))}
              </div>
              {card.count_line && (
                <p className="mt-2 text-xs text-text-secondary">{card.count_line}</p>
              )}
              <p className="mt-1.5 text-xs text-text-muted">{card.footer}</p>
            </div>
          )}
        </div>

        {/* Right: Best Single Member */}
        <div
          className="rounded-xl border border-surface-border bg-surface-card p-4"
          aria-label="Best single member"
        >
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>Best Single Member · {single.category.toUpperCase()}</span>
            <span>Single market #{single.id}</span>
          </div>
          <h2 className="mt-1.5 text-lg font-semibold text-text-primary">{single.name}</h2>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums text-text-primary">
              {single.rendered_percent != null ? `${single.rendered_percent}%` : "No number yet"}
            </span>
            {single.rendered_percent != null && (
              <span className="text-sm text-text-secondary">chance</span>
            )}
          </div>
          {single.rule_quote && (
            <p className="mt-3 text-xs text-text-secondary">
              Rule quote: &ldquo;{single.rule_quote}&rdquo;
            </p>
          )}
        </div>
      </div>

      <input
        className="mt-4 w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary"
        placeholder="Note (optional)"
        value={note}
        maxLength={300}
        onChange={(e) => setNote(e.target.value)}
      />

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {GROUPING_GRADES.map((g) => (
          <button
            key={g}
            className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-3 text-sm font-semibold text-text-primary disabled:opacity-50"
            disabled={saving}
            onClick={() => void submit(g)}
          >
            {GROUPING_GRADE_LABELS[g]}
          </button>
        ))}
      </div>
      {saveStatus}
    </Shell>
  );
}

function Shell({
  tally,
  summary,
  children,
}: {
  tally?: string;
  summary?: GroupingGradeSummary | null;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-3 flex items-center justify-between text-xs text-text-muted">
        <Link href="/grade" className="hover:underline">
          ← Opening ten grading (/grade)
        </Link>
        {tally && <span>{tally}</span>}
      </div>
      {summary && summary.total_grades > 0 && (
        <div className="mb-4 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs text-text-secondary">
          <span>
            Total: {summary.total_grades} grades across {summary.distinct_cards_graded} cards ({summary.distinct_graders} graders)
            {" · "}Amazing {summary.by_grade.amazing} · Fine {summary.by_grade.fine} · No {summary.by_grade.no}
          </span>
        </div>
      )}
      {children}
    </main>
  );
}
