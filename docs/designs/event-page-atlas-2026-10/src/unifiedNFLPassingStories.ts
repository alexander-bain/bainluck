import {nflStoryCandidates,rankNFLStories,type NFLStoryCandidate} from './unifiedNFLStories.ts';
import {passingStory,type passingID} from './passingYards.ts';
export type PassingStoryID=NFLStoryCandidate['id']|typeof passingID;
export function nflPassingCandidates(phase:string){const p=passingStory(phase);return [...nflStoryCandidates(phase),...(p?[p]:[])]}
/** The unchanged editorial ranker accepts the additional known card family.
 * The cast is confined to its generic score/id operation; no price is computed. */
export function nflPassingOrder(phase:string):PassingStoryID[]{return rankNFLStories(nflPassingCandidates(phase) as NFLStoryCandidate[]) as PassingStoryID[]}
export function previewNFLPassingOrder(phase:string,mode:string){const ids=nflPassingOrder(phase);return mode==='none'?[]:mode==='reverse'?[...ids].reverse():ids}
