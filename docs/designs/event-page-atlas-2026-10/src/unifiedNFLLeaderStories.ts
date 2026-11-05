import {nflReceivingCandidates,nflReceivingOrder,type ReceivingStoryID} from './unifiedNFLReceivingStories.ts';
import {receivingLeaderStory,receivingLeaderID,receivingLeaders} from './receivingLeaders.ts';
export type LeaderStoryID=ReceivingStoryID|typeof receivingLeaderID;
export function nflLeaderCandidates(phase:string){const leader=receivingLeaderStory(phase);return [...nflReceivingCandidates(phase),...(leader?[leader]:[])]}
/** Recorded winner is an explicit editorial feature, never a price-derived surprise score.
 * Every inherited probability-ranked candidate retains its relative order. */
export function nflLeaderOrder(phase:string):LeaderStoryID[]{
 const prior=nflReceivingOrder(phase),leader=receivingLeaderStory(phase);if(!leader)return prior;
 const soleWinner=phase==='Final'&&receivingLeaders(phase)?.filter(p=>p.result==='Recorded winner').length===1;
 return soleWinner?[receivingLeaderID,...prior]:[...prior,receivingLeaderID];
}
export function previewNFLLeaderOrder(phase:string,mode:string){const order=nflLeaderOrder(phase);return mode==='none'?[]:mode==='reverse'?[...order].reverse():order}
