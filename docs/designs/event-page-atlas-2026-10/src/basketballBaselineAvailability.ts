/** Design-only delivery simulation. Original captures remain immutable. */
export function withoutBaseline<T extends {value:number|null;at:string|null}>(record:T, unavailable:boolean):T {
 return unavailable ? {...record,value:null,at:null}:record;
}
export function baselinePreviewUnavailable(search:string):boolean {
 const params=new URLSearchParams(search);
 return params.get('event')==='nba' && params.get('baseline')==='unavailable';
}
export const nbaMountedBaselineUnavailable=typeof window!=='undefined' && baselinePreviewUnavailable(window.location.search);
