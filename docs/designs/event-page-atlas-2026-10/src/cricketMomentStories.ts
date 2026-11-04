import {cricketChase,liveCricketSides,cricketLiveName,liveCricketBaseline,liveCricketQuote,type LiveCricketSide} from './cricketLiveEvidence.ts';
export type CricketStoryID='shifts'|'chase'|'survival'|'expectations';
export interface CricketMomentOrder {ids:CricketStoryID[];reasons:Partial<Record<CricketStoryID,string>>}
export function cricketChanceChange(side:LiveCricketSide,stage:number,mode='captured'){
 const baseline=liveCricketBaseline(side),quote=mode==='captured'?liveCricketQuote(side,stage):null;
 return baseline&&quote?{baseline,quote,delta:quote.value-baseline.value}:null;
}
/** Recorded reports and qualified trades only; this is not a connected AI ranking service. */
export function cricketMomentOrder(stage:number|'before'|'final',mode='captured'):CricketMomentOrder {
 if(stage==='before')return {ids:[],reasons:{}};
 if(stage==='final')return {ids:['expectations','chase'],reasons:{}};
 const frame=cricketChase(stage);if(!frame)return {ids:[],reasons:{}};
 const prior=cricketChase(stage-1),lost=prior?frame.wickets-prior.wickets:0,gained=prior?frame.runs-prior.runs:0;
 const biggest=liveCricketSides.flatMap(side=>{const change=cricketChanceChange(side,stage,mode);return change?[{side,...change}]:[]}).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta))[0];
 const reasons:CricketMomentOrder['reasons']={};
 if(biggest)reasons.shifts=`${cricketLiveName(biggest.side)} ${biggest.side==='TIE'?'chance':'win chance'} ${biggest.delta>=0?'rose':'fell'} ${(Math.abs(biggest.delta)*100).toFixed(1)} points from pregame.`;
 if(prior&&lost>0)reasons.survival=`${lost} wickets lost since the ${prior.overs}-over report; ${frame.wicketsLeft} remain.`;
 else reasons.survival=`${frame.wicketsLeft} wickets remain at the ${frame.overs}-over report.`;
 reasons.chase=prior&&gained>0&&lost===0?`${gained} runs added without another wicket since the ${prior.overs}-over report.`:`South Africa still need ${frame.need} runs to win.`;
 const rest=biggest?['shifts'] as const:[];
 if(lost>0)return {ids:['survival',...rest,'chase',...(!biggest?['shifts'] as const:[])],reasons};
 if(prior&&gained>0)return {ids:['chase',...rest,'survival',...(!biggest?['shifts'] as const:[])],reasons};
 return {ids:biggest?['shifts','chase','survival']:['chase','survival','shifts'],reasons};
}
export const cricketMomentScope=(stage:number|'before'|'final')=>`cricket-moment:${stage}`;
