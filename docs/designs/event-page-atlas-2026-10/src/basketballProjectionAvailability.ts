/** Isolated delivery simulation. Does not alter retained records or producer admission. */
export function projectionPreviewUnavailable(search:string):boolean {
 const params=new URLSearchParams(search);
 return params.get('event')==='nba' && params.get('projection')==='unavailable';
}
export const nbaProjectionUnavailable=typeof window!=='undefined' && projectionPreviewUnavailable(window.location.search);
export function withoutNBAProjection<T extends {id:string;projectedHome:number|null;projectedAway:number|null;projectionAt:string|null;projectionNote?:string|null}>(record:T, unavailable:boolean):T {
 return unavailable&&record.id==='nba'?{...record,projectedHome:null,projectedAway:null,projectionAt:null,projectionNote:'Pregame score projection unavailable in this page response.'}:record;
}
export const nbaMarginTitle=nbaProjectionUnavailable?'Clippers won by 3':'Clippers beat the projected margin by 5.7';
