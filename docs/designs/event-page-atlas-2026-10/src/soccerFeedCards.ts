import {soccerJourneyContext} from './soccerJourney.ts';
import {soccerLifecycleContext,soccerLifecycleRank,type SoccerLifecycleContext} from './soccerLifecycle.ts';
import {soccerHalfSnapshot,type HalfCompetitor} from './soccerHalfResults.ts';
import {soccerSnackPreview} from './soccerSnackPreview.ts';
import type {SnackID} from './snackReplay.ts';
import type {StoryFrame} from './storyReadingFrame.ts';
import live from './liveSoccer.json' with {type:'json'};
export type SoccerFeedID=SnackID|'halves';
export const soccerFeedKeys=['goals','both','first','halves'];
export function soccerFeedRank(context:SoccerLifecycleContext,includeHalves:boolean){
 const original=soccerLifecycleRank(context);
 if(!includeHalves||!soccerHalfSnapshot(context.phase))return original;
 const comparison={id:'halves' as const,reason:context.phase==='final'?'Each half against its pre-match outlook':context.phase==='before'?'Different expectations for each half':'Pre-match context · half results unconfirmed'};
 return [original[0],comparison,...original.slice(1)];
}
export function soccerFeedFrame(index:number,scope:string,includeFinal=false):StoryFrame<SoccerLifecycleContext>{
 const context=includeFinal?soccerJourneyContext(index):soccerLifecycleContext(live.points,live.scoreHistory,live.baseline.at,index);
 return {scope,sequence:index,through:context.at,order:soccerFeedRank(context,includeFinal).map(c=>c.id),payload:context};
}
export function soccerFeedPreview(id:SoccerFeedID,context:SoccerLifecycleContext,selected:HalfCompetitor='home'){
 if(id!=='halves')return soccerSnackPreview(id,context);
 const outcome=soccerHalfSnapshot(context.phase)?.[0].outcomes.find(o=>o.team.id===selected);
 const predicate=selected==='draw'?'First half ends level':`${outcome?.team.label??'Team'} wins first half`;
 const actual=context.phase==='before'?'Before the match':context.phase==='in-match'?'Half results unconfirmed':`First half · ${outcome?.row.result==='won'?'Won':outcome?.row.result==='lost'?'Lost':'Unconfirmed'}`;
 return {id,title:'Half-by-half expectations',predicate,probability:outcome?.value??null,baselineAt:outcome?.row.baseline?.at??null,key:outcome?.row.key??null,actual};
}
