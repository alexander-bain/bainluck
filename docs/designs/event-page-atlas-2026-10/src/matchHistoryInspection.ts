import {matchHistoryFrame} from './matchHistoryTarget.ts';
type Series=Parameters<typeof matchHistoryFrame>[0];
/** A deliberate price inspection always opens a fresh history reader, even after paging away from history. */
export function matchHistoryInspection(all:Series,near:Series,ticker:string,at:number,revision:number){
 const frame=matchHistoryFrame(all,near,ticker,at);
 if(frame===null||!Number.isSafeInteger(revision)||revision<0||!Number.isSafeInteger(revision+1))return null;
 return {frame,revision:revision+1};
}
