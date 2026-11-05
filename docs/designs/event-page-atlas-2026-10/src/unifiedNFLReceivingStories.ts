import {nflTouchdownCandidates,type TouchdownStoryID} from './unifiedNFLTouchdownStories.ts';
import {rankNFLStories,type NFLStoryCandidate} from './unifiedNFLStories.ts';
import {receivingStory,type receivingID} from './receivingYards.ts';
export type ReceivingStoryID=TouchdownStoryID|typeof receivingID;
export function nflReceivingCandidates(phase:string){const r=receivingStory(phase);return [...nflTouchdownCandidates(phase),...(r?[r]:[])]}
export function nflReceivingOrder(phase:string):ReceivingStoryID[]{return rankNFLStories(nflReceivingCandidates(phase) as unknown as NFLStoryCandidate[]) as ReceivingStoryID[]}
export function previewNFLReceivingOrder(phase:string,mode:string){const order=nflReceivingOrder(phase);return mode==='none'?[]:mode==='reverse'?[...order].reverse():order}
