import {receivingLeaderID,receivingLeaderMarket,leaderKnownKey} from './receivingLeaders.ts';
import {nflReceivingCandidates,nflReceivingOrder} from './unifiedNFLReceivingStories.ts';
export const leaderProbabilityStatus={available:false,label:'Probability unavailable',reason:'A comparable pregame win probability is not verified for this prop.'} as const;
/** This archive has price records but no qualified outright probability. It is
 * browsable in All props; it cannot earn a ranked probability story slot. */
export function probabilityFirstNFLCandidates(phase:string){return nflReceivingCandidates(phase)}
export function probabilityFirstNFLOrder(phase:string){return nflReceivingOrder(phase)}
export function previewProbabilityFirstNFLOrder(phase:string,mode:string){const order=probabilityFirstNFLOrder(phase);return mode==='none'?[]:mode==='reverse'?[...order].reverse():order}
export function usesLeaderProbabilityUnavailable(row:{row_key:string;_market_id:number},eventID:string){return row._market_id===receivingLeaderMarket||eventID==='14780549'&&leaderKnownKey(row.row_key)}
export {receivingLeaderID};
