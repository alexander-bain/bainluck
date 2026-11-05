import {nflPassingCandidates,type PassingStoryID} from './unifiedNFLPassingStories.ts';
import {rankNFLStories,type NFLStoryCandidate} from './unifiedNFLStories.ts';
import {touchdownStory,type touchdownID} from './passingTouchdowns.ts';
export type TouchdownStoryID=PassingStoryID|typeof touchdownID;
export function nflTouchdownCandidates(phase:string){const t=touchdownStory(phase);return [...nflPassingCandidates(phase),...(t?[t]:[])]}
export function nflTouchdownOrder(phase:string):TouchdownStoryID[]{return rankNFLStories(nflTouchdownCandidates(phase) as NFLStoryCandidate[]) as TouchdownStoryID[]}
export function previewNFLTouchdownOrder(phase:string,mode:string){const order=nflTouchdownOrder(phase);return mode==='none'?[]:mode==='reverse'?[...order].reverse():order}
