"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * #13550 (363: A) — /grade/forms: blind pile sort for the 14 Discover card forms.
 * Supports desktop drag-and-drop and phone tap-then-tap, starts with Pile 1 visible,
 * includes Start over, and filters out pre-fix rows without deleting them.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import formsDeckRaw from "@/data/forms_blind_deck_public_2026_11_23.json";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  addEmptyPile,
  buildCardToPileMap,
  computeSha256Hex,
  createInitialEmptyPiles,
  createPileWithCard,
  isPostFixFormsJudgmentRow,
  moveCardToPilePreservingEmpty,
  pruneEmptyPilesForSave,
  removeCardPreservingEmptyPiles,
  shuffleBlindForms,
  type BlindFormCardItem,
  type BlindFormsPublicDeck,
  type PileBucket,
} from "@/lib/ranking/blindDeckGrade363a";

const FORMS_DECK = formsDeckRaw as BlindFormsPublicDeck;
const LEGACY_DRAFT_STORAGE_KEY = "bainluck_363a_forms_pile_draft_v1";
const DRAFT_STORAGE_KEY = "bainluck_363a_forms_pile_draft_v2";
const RESET_AFTER_STORAGE_KEY = "bainluck_363a_forms_reset_after_v2";

interface SavedJudgmentRow {
  surface?: string;
  label_metadata?: {
    ui_version?: number;
    piles?: PileBucket[];
    timestamp?: string;
    seed?: number;
  };
  created_at?: string;
}

export default function GradeFormsDeckPage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  useEffect(() => {
    setDiscoverLearningGate(() => false);
    return () => setDiscoverLearningGate(null);
  }, []);

  return (
    <AdminAuthProvider>
      <FormsPileSortSession />
    </AdminAuthProvider>
  );
}

function WorkedExampleBox() {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-elevated p-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
        Worked example · Same look → same pile
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2.5">
        <div className="rounded-lg border border-surface-border bg-surface-card p-2">
          <div className="text-[10px] font-bold text-accent-brand">Pile 1 · Bars &amp; rows</div>
          <div className="mt-1.5 space-y-1.5">
            {[0, 1].map((cardIdx) => (
              <div
                key={`ex-bar-${cardIdx}`}
                className="rounded border border-surface-border bg-surface-deep p-1.5 space-y-1"
              >
                <div className="h-1.5 w-3/4 rounded bg-text-primary/25" />
                <div className="h-1.5 w-full rounded bg-accent-brand/60" />
                <div className="h-1.5 w-2/3 rounded bg-accent-brand/40" />
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-surface-border bg-surface-card p-2">
          <div className="text-[10px] font-bold text-text-primary">Pile 2 · Calendar grid</div>
          <div className="mt-1.5 rounded border border-surface-border bg-surface-deep p-1.5 space-y-1">
            <div className="h-1.5 w-2/3 rounded bg-text-primary/25" />
            <div className="grid grid-cols-4 gap-1 pt-0.5">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((tileIdx) => (
                <div
                  key={`ex-tile-${tileIdx}`}
                  className={`h-2.5 rounded-sm border border-surface-border ${
                    tileIdx === 2 || tileIdx === 6 ? "bg-accent-brand/50" : "bg-surface-card"
                  }`}
                />
              ))}
            </div>
          </div>
          <p className="mt-1.5 text-[10px] leading-snug text-text-secondary">
            Different layout → start a new pile.
          </p>
        </div>
      </div>
    </div>
  );
}

function FormsPileSortSession() {
  const { secret, clearSecret } = useAdminAuth();
  const orderedForms = useMemo(
    () => shuffleBlindForms(FORMS_DECK.forms, FORMS_DECK.seed),
    [],
  );
  const byId = useMemo(() => {
    const m: Record<string, BlindFormCardItem> = {};
    for (const f of FORMS_DECK.forms) m[f.item_id] = f;
    return m;
  }, []);

  const [piles, setPiles] = useState<PileBucket[]>(() => createInitialEmptyPiles());
  const [selectedCardId, setSelectedCardId] = useState<string | null>(
    () => orderedForms[0]?.item_id ?? null,
  );
  const [draggedCardId, setDraggedCardId] = useState<string | null>(null);
  const [dragOverTarget, setDragOverTarget] = useState<string | null>(null);
  const [zoomCardId, setZoomCardId] = useState<string | null>(null);
  const [resetAfterIso, setResetAfterIso] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [pilesSha256, setPilesSha256] = useState<string | null>(null);

  useEffect(() => {
    try {
      // Clear any pre-fix draft state from Alex's earlier broken session.
      localStorage.removeItem(LEGACY_DRAFT_STORAGE_KEY);
      const storedReset = localStorage.getItem(RESET_AFTER_STORAGE_KEY);
      if (storedReset) setResetAfterIso(storedReset);

      const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as { piles?: PileBucket[]; savedAt?: string };
        if (Array.isArray(parsed.piles) && parsed.piles.length > 0) {
          setPiles(parsed.piles);
          if (parsed.savedAt) setSavedAt(parsed.savedAt);
        }
      }
    } catch {
      // storage unavailable
    }
  }, []);

  useEffect(() => {
    if (!secret) return;
    let cancelled = false;
    (async () => {
      try {
        let activeResetAfter = resetAfterIso;
        try {
          activeResetAfter = localStorage.getItem(RESET_AFTER_STORAGE_KEY) || resetAfterIso;
        } catch {
          // ignore
        }
        const res = await adminFetchJSON<{ judgments?: SavedJudgmentRow[] }>(
          "/api/admin/ranking-judgments?surface=grade_forms_deck&limit=20",
          secret,
        );
        if (cancelled) return;
        const latest = (res.judgments || []).find((j) =>
          isPostFixFormsJudgmentRow(j, activeResetAfter),
        );
        if (latest?.label_metadata?.piles && latest.label_metadata.piles.length > 0) {
          setPiles(latest.label_metadata.piles);
          setSavedAt(latest.label_metadata.timestamp || latest.created_at || null);
        }
      } catch {
        // draft fallback remains active
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [secret, resetAfterIso]);

  const cardToPile = useMemo(() => buildCardToPileMap(piles), [piles]);
  const unsortedCards = useMemo(
    () => orderedForms.filter((f) => !cardToPile[f.item_id]),
    [orderedForms, cardToPile],
  );
  const sortedCount = orderedForms.length - unsortedCards.length;
  const nonEmptyPilesCount = useMemo(
    () => piles.filter((p) => p.item_ids.length > 0).length,
    [piles],
  );
  const allPlaced = sortedCount === orderedForms.length && orderedForms.length > 0;

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ piles, savedAt }));
    } catch {
      // ignore
    }
    const cleanForHash = pruneEmptyPilesForSave(piles);
    const payload = JSON.stringify({
      deck_id: FORMS_DECK.deck_id,
      seed: FORMS_DECK.seed,
      piles: cleanForHash.map((p) => ({ pile_id: p.pile_id, item_ids: p.item_ids })),
    });
    void computeSha256Hex(payload).then((hex) => setPilesSha256(hex));
  }, [piles, savedAt]);

  const selectNextUnsorted = useCallback(
    (nextPiles: PileBucket[]) => {
      const nextMap = buildCardToPileMap(nextPiles);
      const nextCard = orderedForms.find((f) => !nextMap[f.item_id]);
      setSelectedCardId(nextCard?.item_id ?? null);
    },
    [orderedForms],
  );

  const placeCardIntoPile = useCallback(
    (itemId: string, pileId: string) => {
      const next = moveCardToPilePreservingEmpty(piles, itemId, pileId);
      setPiles(next);
      setStatusMsg(null);
      setErrorMsg(null);
      selectNextUnsorted(next);
    },
    [piles, selectNextUnsorted],
  );

  const placeCardIntoNewPile = useCallback(
    (itemId: string) => {
      const cleaned = removeCardPreservingEmptyPiles(piles, itemId);
      const next = createPileWithCard(cleaned, itemId);
      setPiles(next);
      setStatusMsg(null);
      setErrorMsg(null);
      selectNextUnsorted(next);
    },
    [piles, selectNextUnsorted],
  );

  const handleAddEmptyPile = () => {
    setPiles((prev) => addEmptyPile(prev));
    setStatusMsg(null);
  };

  const handleReturnUnsorted = (itemId: string) => {
    const next = removeCardPreservingEmptyPiles(piles, itemId);
    setPiles(next);
    setSelectedCardId(itemId);
    setStatusMsg(null);
  };

  const handleStartOver = () => {
    const freshTs = new Date().toISOString();
    const initial = createInitialEmptyPiles();
    setPiles(initial);
    setSelectedCardId(orderedForms[0]?.item_id ?? null);
    setDraggedCardId(null);
    setDragOverTarget(null);
    setSavedAt(null);
    setStatusMsg(null);
    setErrorMsg(null);
    setResetAfterIso(freshTs);
    try {
      localStorage.removeItem(LEGACY_DRAFT_STORAGE_KEY);
      localStorage.setItem(RESET_AFTER_STORAGE_KEY, freshTs);
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ piles: initial, savedAt: null }));
    } catch {
      // ignore storage failure
    }
  };

  const handleSave = async () => {
    if (saving || sortedCount === 0) return;
    setSaving(true);
    setErrorMsg(null);
    setStatusMsg(null);
    const ts = new Date().toISOString();
    const finalPiles = pruneEmptyPilesForSave(piles);
    const finalCardMap = buildCardToPileMap(finalPiles);
    try {
      const res = await adminFetch("/api/admin/ranking-judgments", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          surface: "grade_forms_deck",
          item_type: "forms_pile_sort",
          market_name: FORMS_DECK.deck_id,
          label: allPlaced ? "pile_sort_complete" : "pile_sort_draft",
          reviewer: "alex",
          notes: `${sortedCount}/${orderedForms.length} cards in ${finalPiles.length} piles`,
          label_metadata: {
            ui_version: 2,
            deck_id: FORMS_DECK.deck_id,
            seed: FORMS_DECK.seed,
            timestamp: ts,
            pile_count: finalPiles.length,
            piles: finalPiles,
            card_to_pile: finalCardMap,
          },
        }),
      });
      if (res.status === 401 || res.status === 403) {
        clearSecret({ rejected: true });
        return;
      }
      if (!res.ok) {
        setErrorMsg(`Save failed (${res.status})`);
        return;
      }
      setPiles(finalPiles.length > 0 ? finalPiles : createInitialEmptyPiles());
      setSavedAt(ts);
      setStatusMsg(
        `Saved ${sortedCount}/${orderedForms.length} cards across ${finalPiles.length} ${
          finalPiles.length === 1 ? "pile" : "piles"
        }.`,
      );
    } catch {
      setErrorMsg("Network error saving pile sort.");
    } finally {
      setSaving(false);
    }
  };

  const selectedCard = selectedCardId ? byId[selectedCardId] : null;
  const zoomCard = zoomCardId ? byId[zoomCardId] : null;

  return (
    <main className="min-h-screen bg-surface-deep px-3 py-4 text-text-primary sm:px-6">
      <div className="mx-auto w-full max-w-5xl space-y-4">
        {/* Top instruction + worked example header */}
        <header className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
            <Link href="/grade" className="font-semibold text-accent-brand hover:underline">
              ← Grade home
            </Link>
            <div className="flex items-center gap-3">
              <span>Seed {FORMS_DECK.seed}</span>
              <button
                type="button"
                data-testid="start-over-btn"
                onClick={handleStartOver}
                className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-semibold text-text-primary hover:border-accent-danger"
              >
                Start over
              </button>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-12 lg:items-start">
            <div className="space-y-2 lg:col-span-7">
              <h1 className="text-lg font-bold text-text-primary">
                Forms deck · Sort card looks (363: A)
              </h1>
              <p className="text-sm font-medium leading-relaxed text-text-primary">
                Put cards that look like the same kind of card in the same pile. We are counting how many different looks a reader sees.
              </p>
              <p className="text-xs leading-relaxed text-text-secondary">
                On a computer, drag any card onto a pile on the right (or start a new pile). On a phone, tap a card, then tap the pile where it belongs.
              </p>
            </div>
            <div className="lg:col-span-5">
              <WorkedExampleBox />
            </div>
          </div>
        </header>

        {/* Mobile quick-placement strip when a card is selected */}
        <section className="sticky top-2 z-20 rounded-xl border border-surface-border bg-surface-card p-3 shadow-sm lg:hidden">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-text-primary">
              {selectedCard
                ? `Selected card (${orderedForms.findIndex((c) => c.item_id === selectedCard.item_id) + 1} of ${orderedForms.length})`
                : allPlaced
                ? `All ${orderedForms.length} placed · save below`
                : "Tap any card to place it"}
            </span>
            <button
              type="button"
              onClick={handleAddEmptyPile}
              className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-semibold text-accent-brand"
            >
              + New pile
            </button>
          </div>
          {selectedCard && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {piles.map((pile, idx) => (
                <button
                  key={`quick-${pile.pile_id}`}
                  type="button"
                  data-testid={`quick-place-${pile.pile_id}`}
                  onClick={() => placeCardIntoPile(selectedCard.item_id, pile.pile_id)}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs font-semibold text-text-primary hover:border-accent-brand"
                >
                  Put in Pile {idx + 1} ({pile.item_ids.length})
                </button>
              ))}
              <button
                type="button"
                data-testid="quick-place-new-pile"
                onClick={() => placeCardIntoNewPile(selectedCard.item_id)}
                className="rounded-lg bg-accent-brand px-2.5 py-1.5 text-xs font-semibold text-text-inverse"
              >
                + Start Pile {piles.length + 1}
              </button>
            </div>
          )}
        </section>

        {/* Responsive two-column desktop / single-column mobile workspace */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:items-start">
          {/* Unsorted cards column */}
          <section className="space-y-3 lg:col-span-6">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-xs font-bold uppercase tracking-wide text-text-muted">
                Unsorted cards ({unsortedCards.length} left)
              </h2>
              <span className="text-xs font-semibold text-text-secondary">
                {sortedCount} of {orderedForms.length} placed
              </span>
            </div>

            {unsortedCards.length === 0 ? (
              <div className="rounded-xl border border-accent-brand/40 bg-surface-card p-6 text-center space-y-1.5">
                <p className="text-sm font-bold text-accent-brand">
                  All {orderedForms.length} cards placed in {nonEmptyPilesCount}{" "}
                  {nonEmptyPilesCount === 1 ? "pile" : "piles"}
                </p>
                <p className="text-xs text-text-secondary">
                  Review your piles or use Save in the top bar of Your piles.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1">
                {unsortedCards.map((card) => {
                  const isSelected = selectedCardId === card.item_id;
                  const cardNum =
                    orderedForms.findIndex((c) => c.item_id === card.item_id) + 1;
                  return (
                    <div
                      key={card.item_id}
                      draggable
                      data-testid={`unsorted-card-${card.item_id}`}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", card.item_id);
                        e.dataTransfer.effectAllowed = "move";
                        setDraggedCardId(card.item_id);
                        setSelectedCardId(card.item_id);
                      }}
                      onDragEnd={() => {
                        setDraggedCardId(null);
                        setDragOverTarget(null);
                      }}
                      className={`overflow-hidden rounded-xl border bg-surface-card p-2.5 transition-colors cursor-grab active:cursor-grabbing ${
                        isSelected
                          ? "border-accent-brand ring-2 ring-accent-brand"
                          : "border-surface-border hover:border-text-muted"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedCardId(card.item_id)}
                        className="block w-full text-left"
                        aria-label={`Select card ${cardNum}`}
                      >
                        <img
                          src={card.image_url}
                          alt={`Blind card ${cardNum}`}
                          draggable={false}
                          className="mx-auto block h-auto w-full max-w-[390px] rounded-lg border border-surface-border bg-surface-base"
                          loading="eager"
                        />
                      </button>
                      <div className="mt-2 flex items-center justify-between px-1">
                        <button
                          type="button"
                          onClick={() => setSelectedCardId(card.item_id)}
                          className="text-xs font-semibold text-accent-brand"
                        >
                          {isSelected
                            ? `Card ${cardNum} selected · pick or drop in a pile`
                            : `Card ${cardNum} · drag or tap to place`}
                        </button>
                        <button
                          type="button"
                          onClick={() => setZoomCardId(card.item_id)}
                          className="text-xs text-text-muted hover:underline"
                        >
                          Zoom
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Piles column (stays bounded inside desktop viewport alongside any card) */}
          <section className="space-y-3 lg:sticky lg:top-4 lg:col-span-6 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:pr-1">
            {/* Consistent save / progress slot */}
            <div
              data-testid="save-panel"
              className="rounded-xl border border-surface-border bg-surface-card p-3.5 shadow-sm space-y-2.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-bold uppercase tracking-wide text-text-muted">
                    Your piles ({piles.length})
                  </div>
                  <div
                    data-testid="progress-summary"
                    className={`text-sm font-bold ${
                      allPlaced ? "text-accent-brand" : "text-text-primary"
                    }`}
                  >
                    {allPlaced
                      ? `All ${orderedForms.length} cards placed across ${nonEmptyPilesCount} ${
                          nonEmptyPilesCount === 1 ? "pile" : "piles"
                        } — ready to save`
                      : `${sortedCount} of ${orderedForms.length} placed · ${nonEmptyPilesCount} ${
                          nonEmptyPilesCount === 1 ? "pile" : "piles"
                        } used`}
                  </div>
                </div>
                <button
                  type="button"
                  data-testid="add-empty-pile-btn"
                  onClick={handleAddEmptyPile}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs font-semibold text-text-primary hover:border-accent-brand"
                >
                  + Add pile
                </button>
              </div>

              <button
                type="button"
                data-testid="save-piles-btn"
                disabled={saving || sortedCount === 0}
                onClick={() => void handleSave()}
                className="w-full rounded-xl bg-accent-brand px-4 py-2.5 text-sm font-bold text-text-inverse disabled:opacity-45"
              >
                {saving
                  ? "Saving piles…"
                  : allPlaced
                  ? "Save finished pile sort"
                  : `Save progress (${sortedCount}/${orderedForms.length})`}
              </button>

              {statusMsg && (
                <p data-testid="save-status-msg" className="text-xs font-semibold text-accent-live">
                  {statusMsg}
                </p>
              )}
              {errorMsg && (
                <p className="text-xs font-semibold text-accent-danger">{errorMsg}</p>
              )}
              {savedAt && (
                <p className="text-[11px] text-text-muted">Last saved: {savedAt}</p>
              )}
              {pilesSha256 && allPlaced && (
                <div className="rounded-lg border border-surface-border bg-surface-elevated p-2 text-[11px] text-text-secondary break-all">
                  Freeze SHA-256: <span className="font-mono">{pilesSha256}</span>
                </div>
              )}
            </div>

            {/* Drag-to-new-pile target (kept near top so it stays reachable from any card) */}
            <div
              data-testid="new-pile-dropzone"
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (dragOverTarget !== "__new__") setDragOverTarget("__new__");
              }}
              onDragLeave={() => {
                if (dragOverTarget === "__new__") setDragOverTarget(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                const droppedId = e.dataTransfer.getData("text/plain") || draggedCardId;
                setDragOverTarget(null);
                setDraggedCardId(null);
                if (droppedId) placeCardIntoNewPile(droppedId);
              }}
              className={`rounded-xl border border-dashed p-3 text-center text-xs font-semibold transition-colors ${
                dragOverTarget === "__new__"
                  ? "border-accent-brand bg-accent-brand/10 text-accent-brand"
                  : "border-surface-border bg-surface-card text-text-muted"
              }`}
            >
              + Drop card here to start a new pile (Pile {piles.length + 1})
            </div>

            {/* Existing piles (Pile 1 visible from start even when empty) */}
            <div className="space-y-3">
              {piles.map((pile, idx) => {
                const isDropActive = dragOverTarget === pile.pile_id;
                return (
                  <div
                    key={pile.pile_id}
                    data-testid={`pile-bucket-${pile.pile_id}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      if (dragOverTarget !== pile.pile_id) setDragOverTarget(pile.pile_id);
                    }}
                    onDragLeave={() => {
                      if (dragOverTarget === pile.pile_id) setDragOverTarget(null);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      const droppedId = e.dataTransfer.getData("text/plain") || draggedCardId;
                      setDragOverTarget(null);
                      setDraggedCardId(null);
                      if (droppedId) placeCardIntoPile(droppedId, pile.pile_id);
                    }}
                    className={`rounded-xl border p-3 transition-colors ${
                      isDropActive
                        ? "border-accent-brand bg-accent-brand/10 ring-2 ring-accent-brand"
                        : "border-surface-border bg-surface-card"
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-sm font-bold text-text-primary">
                        Pile {idx + 1} · {pile.item_ids.length}{" "}
                        {pile.item_ids.length === 1 ? "card" : "cards"}
                      </span>
                      {selectedCard && (
                        <button
                          type="button"
                          data-testid={`place-in-${pile.pile_id}`}
                          onClick={() => placeCardIntoPile(selectedCard.item_id, pile.pile_id)}
                          className="rounded-md border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-semibold text-accent-brand hover:border-accent-brand"
                        >
                          Put selected here
                        </button>
                      )}
                    </div>

                    {pile.item_ids.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-surface-border bg-surface-deep px-3 py-5 text-center text-xs text-text-muted">
                        Drag a card here or tap a card and press &ldquo;Put selected here&rdquo;.
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {pile.item_ids.map((id) => {
                          const card = byId[id];
                          if (!card) return null;
                          return (
                            <div
                              key={id}
                              draggable
                              data-testid={`placed-card-${id}`}
                              onDragStart={(e) => {
                                e.dataTransfer.setData("text/plain", id);
                                e.dataTransfer.effectAllowed = "move";
                                setDraggedCardId(id);
                              }}
                              onDragEnd={() => {
                                setDraggedCardId(null);
                                setDragOverTarget(null);
                              }}
                              className="rounded-lg border border-surface-border bg-surface-elevated p-1.5 cursor-grab active:cursor-grabbing"
                            >
                              <button
                                type="button"
                                onClick={() => setSelectedCardId(id)}
                                className="block w-full"
                                aria-label={`Select placed card ${id}`}
                              >
                                <img
                                  src={card.image_url}
                                  alt="Grouped blind card"
                                  draggable={false}
                                  className="block max-h-28 w-full rounded border border-surface-border bg-surface-card object-contain"
                                />
                              </button>
                              <div className="mt-1.5 flex items-center justify-between text-[11px]">
                                <button
                                  type="button"
                                  onClick={() => setZoomCardId(id)}
                                  className="font-medium text-accent-brand"
                                >
                                  Zoom
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleReturnUnsorted(id)}
                                  className="text-text-muted hover:text-text-primary"
                                >
                                  Unsort
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        {zoomCard && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface-deep/90 p-3">
            <div className="max-h-[92vh] w-full max-w-[390px] overflow-y-auto rounded-xl border border-surface-border bg-surface-card p-3">
              <div className="mb-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => setZoomCardId(null)}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-1 text-xs font-semibold text-text-primary"
                >
                  Close
                </button>
              </div>
              <img
                src={zoomCard.image_url}
                alt="Inspect blind card"
                className="block h-auto w-full rounded-lg border border-surface-border"
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
