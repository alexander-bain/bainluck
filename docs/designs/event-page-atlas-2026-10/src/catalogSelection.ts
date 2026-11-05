import type {CatalogEvidenceRow} from './catalogPresentation';

/** Captured provider identity, never rank, price or observation time.
 * Rows lacking provider IDs are scoped to their immutable capture key. They must
 * not be rebound to a future capture by guessing from a title or row position.
 */
export function catalogOutcomeIdentity(row: CatalogEvidenceRow): string {
 const id = row.id;
 const contributors = row.contributor_outcome_ids;
 const contract = id != null ? ['outcome', String(id)]
  : contributors?.length ? ['contributors', ...contributors.map(String).sort()]
  : ['capture', row.key];
 return JSON.stringify([row.source, row._market_id == null ? null : String(row._market_id),
  contract, row.market_name, row.outcome_name, row.threshold ?? null, row.period ?? null]);
}
export interface CatalogAnchor<T> { identity: string; row: T }
export function catalogAnchor<T extends CatalogEvidenceRow>(row: T): CatalogAnchor<T> {
 return {identity: catalogOutcomeIdentity(row), row};
}
export function resolveCatalogSelection<T extends CatalogEvidenceRow>(rows: T[], anchor: CatalogAnchor<T> | null, windowCount = 6, visibleRows: T[] = rows) {
 const selectedAnchor = anchor ?? ((visibleRows[0]??rows[0]) ? catalogAnchor(visibleRows[0]??rows[0]) : null);
 const matches = selectedAnchor ? rows.map((r,i)=>catalogOutcomeIdentity(r)===selectedAnchor.identity?i:-1).filter(i=>i>=0) : [];
 // Duplicate identities are ambiguous. Never silently choose the first one.
 const index = matches.length === 1 ? matches[0] : null;
 const row = index !== null ? rows[index] : selectedAnchor?.row ?? null;
 const count = Math.max(1, Math.floor(windowCount));
 const visibleIndex = index === null ? null : visibleRows.findIndex(r=>catalogOutcomeIdentity(r)===selectedAnchor!.identity);
 const windowIndex = visibleIndex == null || visibleIndex < 0 ? null : visibleIndex;
 const offset = Math.floor((windowIndex ?? 0) / count) * count;
 return {row,index,windowIndex,offset,shown:visibleRows.slice(offset,offset+count),present:index!==null,
  filteredOut:index!==null&&windowIndex===null,ambiguous:matches.length>1};
}
