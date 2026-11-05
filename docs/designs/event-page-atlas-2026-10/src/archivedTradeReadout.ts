export type ArchivedTradePoint={at:number;p:number};
/** Exact historical evidence only. A missing minute never borrows the preceding trade. */
export function archivedTradeReadout<T extends ArchivedTradePoint>(points:readonly T[],at:number|null){
 const matches=at===null?points.slice(-1):points.filter(p=>p.at===at);
 const point=matches.length===1?matches[0]:null;
 return {point,emptyLabel:at===null?'No recorded trade':'No trade this minute'};
}

/** Share a date only when every displayed trade falls on the same local calendar date. */
export function archivedTradeSharedDate(points:readonly (ArchivedTradePoint|null|undefined)[],clock:{date:(at:number)=>string}){
 const dates=new Set(points.filter((p):p is ArchivedTradePoint=>p!=null).map(p=>clock.date(p.at)));
 return dates.size===1?[...dates][0]:null;
}

export function archivedTradeSharedInstant(points:readonly (ArchivedTradePoint|null|undefined)[]){
 const times=new Set(points.filter((p):p is ArchivedTradePoint=>p!=null).map(p=>p.at));
 return times.size===1?[...times][0]:null;
}
