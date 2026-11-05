import capture from './liveSoccer.json' with {type:'json'};
import type {SoccerLifecycleContext} from './soccerLifecycle';
import type {SnackID} from './snackReplay';

/** Uses the displayed frame only. No received state, latest quote or inferred grade. */
export function soccerSnackPreview(id:SnackID, context:SoccerLifecycleContext){
 const total=context.phase==='before'?null:context.score?context.score.home_score+context.score.away_score:null;
 const index=total!==null&&total>=3?1:0;
 const market=id==='goals'?capture.bindings.totals[index]:id==='both'?capture.bindings.bothScore:capture.bindings.firstScore;
 const row=capture.rows.find(r=>r.marketID===market&&(id==='both'?r.label==='Yes':id==='first'?r.label==='Real Valladolid CF':true))!;
 const title={goals:'Goal milestones',both:'Both teams to score',first:'First team to score'}[id];
 const predicate=id==='goals'?`${[3,5,6][index]}+ goals`:id==='both'?'Both teams score':'Valladolid scores first';
 const actual=context.phase==='before'?'Before the match':context.score?`${context.phase==='final'?'Final':'Recorded'} · Valladolid ${context.score.home_score}–${context.score.away_score} Albacete`:'Score unavailable';
 return {id,title,predicate,probability:row.baseline?.value??null,baselineAt:row.baseline?.at??null,key:row.key,actual};
}
