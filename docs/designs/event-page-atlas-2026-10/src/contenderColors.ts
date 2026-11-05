/** Preserve each continuing identity's color when a ranked cohort changes order.
 * New entrants take vacant slots; leaving the chart releases the slot.
 * This deliberately does not use rank, array position, probability, or display name as identity.
 */
export function retainContenderColors(previous:Record<string,number>,ids:readonly string[],capacity=3):Record<string,number>{
 const unique=[...new Set(ids)],size=Math.max(capacity,unique.length),next:Record<string,number>={},used=new Set<number>();
 for(const id of unique){const slot=previous[id];if(Number.isInteger(slot)&&slot>=0&&slot<size&&!used.has(slot)){next[id]=slot;used.add(slot)}}
 for(const id of unique)if(next[id]===undefined){const slot=Array.from({length:size},(_,i)=>i).find(i=>!used.has(i))!;next[id]=slot;used.add(slot)}
 return next;
}
export const contenderPalette=['var(--series-home)','var(--series-away)','var(--atlas-purple)'];
export function chessIdentityColor(id:number){return contenderPalette[id===235705516?0:id===235705515?1:2]}
