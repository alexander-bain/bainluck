export type ReplayPoint = {at:string;value:number};
export type ScorePoint = {timestamp:string;home_score:number;away_score:number};
export type SnackID = 'goals'|'both'|'first';
export const replayTimes=['12:14:00','12:18:00','12:29:00','12:34:00','12:39:00','12:55:38.867795'].map(t=>`2026-10-12T${t}Z`);
export function replayContext(points:ReplayPoint[],scores:ScorePoint[],at:string){
 const time=Date.parse(at),history=points.filter(p=>Date.parse(p.at)<=time),observed=scores.filter(p=>Date.parse(p.timestamp)<=time);
 return {at,history,point:history.at(-1)??null,score:observed.at(-1)??null,scores:observed};
}
export function rankSnacks(score:ScorePoint|null):{id:SnackID;reason:string}[]{
 const goals=score?score.home_score+score.away_score:0;
 // Editorial rules for this recorded-data experiment. No current prop price is admitted.
 if(goals===0)return [{id:'both',reason:'Before either team scores'},{id:'goals',reason:'The pre-match goal expectations'},{id:'first',reason:'The opening-goal outlook'}];
 if(goals===1)return [{id:'first',reason:'The first scoring checkpoint'},{id:'both',reason:'One team is still scoreless'},{id:'goals',reason:'The next goal milestone'}];
 return [{id:'goals',reason:goals>=3?'A pre-match milestone has been reached':'Closing in on the next milestone'},{id:'both',reason:'A lopsided score changes the context'},{id:'first',reason:'How the scoring started'}];
}
export function motionMayRun(s:{playing:boolean;reduced:boolean;interacting:boolean;details:boolean;catalog:boolean;hidden:boolean}){
 return s.playing&&!s.reduced&&!s.interacting&&!s.details&&!s.catalog&&!s.hidden;
}
