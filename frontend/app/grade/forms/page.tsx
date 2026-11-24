"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * #13550 (363: A) — /grade/forms: 390px blind pile sort for the 14 Discover card forms.
 * Same look -> same pile; different look -> new pile. Saves via POST /api/admin/ranking-judgments.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import formsDeckRaw from "@/data/forms_blind_deck_public_2026_11_23.json";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { setDiscoverLearningGate } from "@/lib/discoverInteractions";
import {
  assignCardToPile,
  buildCardToPileMap,
  computeSha256Hex,
  createPileWithCard,
  removeCardFromPiles,
  shuffleBlindForms,
  type BlindFormCardItem,
  type BlindFormsPublicDeck,
  type PileBucket,
} from "@/lib/ranking/blindDeckGrade363a";

const FORMS_DECK = formsDeckRaw as BlindFormsPublicDeck;
const DRAFT_STORAGE_KEY = "bainluck_363a_forms_pile_draft_v1";

interface SavedJudgmentRow {
  surface?: string;
  label_metadata?: {
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

  const [piles, setPiles] = useState<PileBucket[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(
    () => orderedForms[0]?.item_id ?? null,
  );
  const [zoomCardId, setZoomCardId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [pilesSha256, setPilesSha256] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as { piles?: PileBucket[]; savedAt?: string };
        if (Array.isArray(parsed.piles)) {
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
        const res = await adminFetchJSON<{ judgments?: SavedJudgmentRow[] }>(
          "/api/admin/ranking-judgments?surface=grade_forms_deck&limit=10",
          secret,
        );
        if (cancelled) return;
        const latest = (res.judgments || []).find((j) => Array.isArray(j.label_metadata?.piles));
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
  }, [secret]);

  const cardToPile = useMemo(() => buildCardToPileMap(piles), [piles]);
  const unsortedCards = useMemo(
    () => orderedForms.filter((f) => !cardToPile[f.item_id]),
    [orderedForms, cardToPile],
  );
  const sortedCount = orderedForms.length - unsortedCards.length;

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ piles, savedAt }));
    } catch {
      // ignore
    }
    const payload = JSON.stringify({
      deck_id: FORMS_DECK.deck_id,
      seed: FORMS_DECK.seed,
      piles: piles.map((p) => ({ pile_id: p.pile_id, item_ids: p.item_ids })),
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

  const handleAssignExistingPile = (pileId: string) => {
    if (!selectedCardId) return;
    const next = assignCardToPile(piles, selectedCardId, pileId);
    setPiles(next);
    setStatusMsg(null);
    selectNextUnsorted(next);
  };

  const handleCreateNewPile = () => {
    if (!selectedCardId) return;
    const next = createPileWithCard(piles, selectedCardId);
    setPiles(next);
    setStatusMsg(null);
    selectNextUnsorted(next);
  };

  const handleReturnUnsorted = (itemId: string) => {
    const next = removeCardFromPiles(piles, itemId);
    setPiles(next);
    setSelectedCardId(itemId);
    setStatusMsg(null);
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    setErrorMsg(null);
    setStatusMsg(null);
    const ts = new Date().toISOString();
    try {
      const res = await adminFetch("/api/admin/ranking-judgments", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          surface: "grade_forms_deck",
          item_type: "forms_pile_sort",
          market_name: FORMS_DECK.deck_id,
          label: sortedCount === orderedForms.length ? "pile_sort_complete" : "pile_sort_draft",
          reviewer: "alex",
          notes: `${sortedCount}/${orderedForms.length} cards in ${piles.length} piles`,
          label_metadata: {
            deck_id: FORMS_DECK.deck_id,
            seed: FORMS_DECK.seed,
            timestamp: ts,
            pile_count: piles.length,
            piles,
            card_to_pile: cardToPile,
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
      setSavedAt(ts);
      setStatusMsg(`Saved ${sortedCount}/${orderedForms.length} cards across ${piles.length} piles.`);
    } catch {
      setErrorMsg("Network error saving pile sort.");
    } finally {
      setSaving(false);
    }
  };

  const selectedCard = selectedCardId ? byId[selectedCardId] : null;
  const zoomCard = zoomCardId ? byId[zoomCardId] : null;

  return (
    <main className="min-h-screen bg-surface-deep px-3 py-4 text-text-primary">
      <div className="mx-auto w-full max-w-[390px] space-y-4">
        <header className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between gap-2 text-xs text-text-muted">
            <Link href="/grade" className="font-semibold text-accent-brand hover:underline">
              ← Grade home
            </Link>
            <span>Seed {FORMS_DECK.seed}</span>
          </div>
          <h1 className="mt-1.5 text-lg font-bold text-text-primary">
            Forms deck · Pile sort (363: A)
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Unlabeled cards in random order. Tap a card, then tap a pile if it reads as the same look, or start a new pile.
          </p>
          <div className="mt-2.5 flex items-center justify-between text-xs font-semibold">
            <span className="text-accent-brand">
              {sortedCount} of {orderedForms.length} sorted
            </span>
            <span className="text-text-secondary">
              {piles.length} {piles.length === 1 ? "pile" : "piles"}
            </span>
          </div>
        </header>

        {/* Active pile placement bar */}
        <section className="sticky top-2 z-20 rounded-xl border border-surface-border bg-surface-card p-3 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-text-primary">
              {selectedCard ? "Selected card ready to place" : "Tap any card below to move it"}
            </span>
            {selectedCard && (
              <button
                type="button"
                onClick={handleCreateNewPile}
                className="rounded-lg bg-accent-brand px-3 py-1.5 text-xs font-semibold text-text-inverse"
              >
                + New pile ({piles.length + 1})
              </button>
            )}
          </div>
          {selectedCard && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {piles.map((pile, idx) => (
                <button
                  key={pile.pile_id}
                  type="button"
                  onClick={() => handleAssignExistingPile(pile.pile_id)}
                  className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs font-semibold text-text-primary hover:border-accent-brand"
                >
                  Pile {idx + 1} ({pile.item_ids.length})
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Unsorted cards tray */}
        <section className="space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-wide text-text-muted">
            Unsorted ({unsortedCards.length})
          </h2>
          {unsortedCards.length === 0 ? (
            <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-center text-sm font-medium text-accent-brand">
              All 14 cards placed into {piles.length} piles.
            </div>
          ) : (
            <div className="space-y-3">
              {unsortedCards.map((card) => {
                const isSelected = selectedCardId === card.item_id;
                return (
                  <div
                    key={card.item_id}
                    className={`overflow-hidden rounded-xl border bg-surface-card p-2 transition-colors ${
                      isSelected ? "border-accent-brand ring-2 ring-accent-brand" : "border-surface-border"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedCardId(card.item_id)}
                      className="block w-full text-left"
                      aria-label={`Select card ${card.item_id}`}
                    >
                      <img
                        src={card.image_url}
                        alt="Blind Discover card form"
                        className="block h-auto w-full rounded-lg border border-surface-border bg-surface-base"
                        loading="eager"
                      />
                    </button>
                    <div className="mt-2 flex items-center justify-between px-1">
                      <button
                        type="button"
                        onClick={() => setSelectedCardId(card.item_id)}
                        className="text-xs font-semibold text-accent-brand"
                      >
                        {isSelected ? "Selected · tap a pile above" : "Tap to place"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setZoomCardId(card.item_id)}
                        className="text-xs text-text-muted hover:underline"
                      >
                        Inspect full size
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Created piles */}
        {piles.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wide text-text-muted">
              Your piles ({piles.length})
            </h2>
            {piles.map((pile, idx) => (
              <div
                key={pile.pile_id}
                className="rounded-xl border border-surface-border bg-surface-card p-3"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-bold text-text-primary">
                    Pile {idx + 1} · {pile.item_ids.length} {pile.item_ids.length === 1 ? "card" : "cards"}
                  </span>
                  {selectedCard && (
                    <button
                      type="button"
                      onClick={() => handleAssignExistingPile(pile.pile_id)}
                      className="rounded-md border border-surface-border bg-surface-elevated px-2 py-1 text-xs font-semibold text-accent-brand"
                    >
                      + Drop selected here
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {pile.item_ids.map((id) => {
                    const card = byId[id];
                    if (!card) return null;
                    return (
                      <div
                        key={id}
                        className="rounded-lg border border-surface-border bg-surface-elevated p-1.5"
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
                            className="block h-auto w-full rounded border border-surface-border"
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
              </div>
            ))}
          </section>
        )}

        {/* Save footer */}
        <section className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2.5">
          <button
            type="button"
            disabled={saving || sortedCount === 0}
            onClick={() => void handleSave()}
            className="w-full rounded-xl bg-accent-brand px-4 py-3 text-sm font-bold text-text-inverse disabled:opacity-45"
          >
            {saving ? "Saving piles…" : sortedCount === orderedForms.length ? "Save finished pile sort" : `Save draft (${sortedCount}/${orderedForms.length})`}
          </button>
          {statusMsg && <p className="text-xs font-medium text-accent-live">{statusMsg}</p>}
          {errorMsg && <p className="text-xs font-medium text-accent-danger">{errorMsg}</p>}
          {savedAt && (
            <p className="text-[11px] text-text-muted">Last saved: {savedAt}</p>
          )}
          {pilesSha256 && sortedCount === orderedForms.length && (
            <div className="rounded-lg border border-surface-border bg-surface-elevated p-2 text-[11px] text-text-secondary break-all">
              Freeze SHA-256: <span className="font-mono">{pilesSha256}</span>
            </div>
          )}
        </section>

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
