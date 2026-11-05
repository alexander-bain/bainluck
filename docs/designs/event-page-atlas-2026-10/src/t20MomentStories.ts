import {t20Baseline,t20Chase,t20Quote} from './t20Evidence.ts';
export type T20StoryID='before'|'chase'|'shift';
export interface T20MomentOrder {ids:T20StoryID[];reasons:Partial<Record<T20StoryID,string>>}
const points=(value:number)=>Math.round(Math.abs(value)*100);
/** Editorial replay over exact retained reports/trades, not connected AI or a current-price service. */
export function t20MomentOrder(stage:number):T20MomentOrder {
 if(stage===-1)return {ids:['before'],reasons:{before:'The last traded chances before the pre-match report.'}};
 const frame=t20Chase(stage);if(!frame)return {ids:[],reasons:{}};
 if(stage===4)return {ids:['shift','chase'],reasons:{shift:t20Baseline('WI')?`West Indies started at ${points(t20Baseline('WI')!.value)}% and won the match.`:'Pregame chance unavailable; West Indies won the match.',chase:`${frame.runs} runs scored with ${frame.ballsLeft} balls to spare.`}};
 const prior=t20Chase(stage-1),quote=t20Quote('WI',stage),baseline=t20Baseline('WI'),previous=t20Quote('WI',stage-1);
 const change=quote&&baseline?quote.value-baseline.value:null;
 const reasons:T20MomentOrder['reasons']={chase:`${frame.need} runs needed from ${frame.ballsLeft} balls at the ${frame.overs.split('.')[0]}-over report.`};
 if(change!==null)reasons.shift=`At this report, West Indies’ last traded chance was ${points(quote!.value)}% — ${points(change)} points ${change>=0?'above':'below'} pregame.`;
 if(prior&&frame.wickets>prior.wickets){reasons.chase=`${frame.wickets-prior.wickets} wicket lost since ${prior.overs.split('.')[0]} overs; ${frame.need} runs still needed from ${frame.ballsLeft} balls.`;return {ids:['chase','shift'],reasons}}
 if(frame.ballsLeft<=12)return {ids:['chase','shift'],reasons};
 const swing=quote&&previous?Math.abs(quote.value-previous.value):Math.abs(change??0);
 return {ids:swing>=.2?['shift','chase']:['chase','shift'],reasons};
}
export const t20MomentScope=(stage:number)=>`t20-moment:${stage}`;
