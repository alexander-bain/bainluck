/** Presentation permission only: never computes freshness or settlement authority. */
export type CardEvidenceKind = 'quote' | 'baseline' | 'result' | 'context' | 'mixed';

/** Mixed cards must gate each quote themselves while retaining their other evidence. */
export function cardEvidenceVisibility(kind: CardEvidenceKind, priceMode: string): boolean {
  switch (kind) {
    case 'quote': return priceMode === 'captured';
    case 'baseline':
    case 'result':
    case 'context':
    case 'mixed': return true;
    default: return false;
  }
}
