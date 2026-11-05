/** Preserve legacy source records; adapt only this known unavailable display status. */
export function probabilityStatusLabel(raw: string): string {
 return raw === 'No recent price' ? 'Current probability unavailable' : raw;
}
