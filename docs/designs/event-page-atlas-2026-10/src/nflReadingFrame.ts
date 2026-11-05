import {nflContext,nflMoments,nflRank} from './nflReplay.ts';
import type {StoryFrame} from './storyReadingFrame.ts';

// Six retained observations plus the exact recorded expiry of the last projection.
// Expiry is a validity boundary, not an additional score or probability observation.
const expiration=nflContext(nflMoments[4]).lastProjection!.valid_until;
export const nflReadingMoments=[
 ...nflMoments.slice(0,5).map(at=>({at,kind:'observation' as const})),
 {at:expiration,kind:'expiry' as const},
 {at:nflMoments[5],kind:'observation' as const},
];
export function nflReadingFrame(index:number,scope:string):StoryFrame<ReturnType<typeof nflContext>>{
 if(!Number.isInteger(index)||index<0||index>=nflReadingMoments.length)throw new Error('Unknown football replay position');
 const moment=nflReadingMoments[index],payload=nflContext(moment.at);
 return {scope,sequence:index,through:moment.at,order:nflRank(payload.final),payload};
}
