import {firstScorerPregame} from './hockeyFirstPregame.ts';
import type {HockeyScoringRow} from './hockeyScoringEvidence.ts';
export function firstScorerLeaders<T extends HockeyScoringRow>(rows:T[]){
 const known=rows.flatMap(row=>{const baseline=firstScorerPregame(row);return baseline?[{row,baseline}]:[]}).sort((a,b)=>b.baseline.value-a.baseline.value||a.row.outcome_name.localeCompare(b.row.outcome_name));
 return {known,leaders:known.slice(0,4),ceiling:known.length?Math.min(1,Math.ceil(known[0].baseline.value*20)/20):1};
}
