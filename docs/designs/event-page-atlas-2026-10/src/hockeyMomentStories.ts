import totals from './hockeyEvidence.json' with {type:'json'};
import scorers from './hockeyScorerPregame.json' with {type:'json'};
import first from './hockeyFirstPregame.json' with {type:'json'};
import headers from './finalHeaders.json' with {type:'json'};
import {hockeyPregame} from './hockeyEvidence.ts';
import {scorerPregame} from './hockeyScorerPregame.ts';
import {firstScorerPregame} from './hockeyFirstPregame.ts';
import {hockeyScoringRows,hockeyScoringRecord,type HockeyScoringRow} from './hockeyScoringEvidence.ts';

export const hockeyFamilies=[{id:'totals',name:'Total-goal expectations'},{id:'first',name:'First goalscorer'},{id:'goals',name:'Who found the net?'},{id:'forecast',name:'Score versus forecast'}] as const;
export type HockeyFamily=typeof hockeyFamilies[number]['id'];
type Order={ids:HockeyFamily[];reasons:Partial<Record<HockeyFamily,string>>;selectedScorerKey:string|null};

/** Retained-game ranking: the 1+ goal trade never becomes a first-goalscorer chance. */
export function hockeyMomentOrder(rows:HockeyScoringRow[],eventID:unknown,total=totals,scorer=scorers,firstScorer=first,header=headers.find(h=>h.id==='nhl')!):Order {
 const fallback:Order={ids:hockeyFamilies.map(card=>card.id),reasons:{},selectedScorerKey:null};
 if(eventID!==15169793||header.id!=='nhl'||header.home!=='Minnesota Wild'||header.away!=='Boston Bruins'||header.homeScore!==4||header.awayScore!==1||header.winner!=='home'||total.eventID!==eventID||total.actual!==5||total.homeScore!==4||total.awayScore!==1||header.scoreAt!==total.actualAt||header.projectedHome!==4||header.projectedAway!==2.5)return fallback;
 const goal=hockeyScoringRows(rows,eventID,'goals').find(row=>JSON.stringify(row.contributor_outcome_ids)==='[243943090]');
 const firstGoal=hockeyScoringRows(rows,eventID,'first').find(row=>JSON.stringify(row.contributor_outcome_ids)==='[243940876]');
 const milestone=rows.find(row=>row.key===total.points.find(point=>point.count===6)?.key);
 if(!goal||!firstGoal||!milestone||rows.filter(row=>row.key===milestone.key).length!==1)return fallback;
 const chance=scorerPregame(goal,scorer),record=hockeyScoringRecord(goal,'goals'),before=hockeyPregame(milestone,total);
 if(!chance||chance.value!==.08||record?.player!=='Tanner Jeannot'||record.actual!==1||record.result!=='Won'||goal._market_id!==64870965||goal.threshold!==1||goal._inverted!==false||goal.resolution_source!=='api_settlement'||!before||before.value!==.585||milestone.is_winner!==false||milestone.resolution_source!=='api_settlement')return fallback;
 if(firstGoal._market_id!==64870910||firstGoal.outcome_name!=='Tanner Jeannot'||firstGoal.is_winner!==true||firstGoal.resolution_source!=='api_settlement'||firstScorerPregame(firstGoal,firstScorer)!==null)return fallback;
 // A missing/foreign fixture cannot justify an unavailable-baseline claim.
 const retainedFirst=firstScorer.points.filter(point=>point.key===firstGoal.key&&point.contributor===243940876);
 if(firstScorer.eventID!==eventID||firstScorer.marketID!==64870910||firstScorer.eventTicker!=='KXNHLFIRSTGOAL-26OCT03BOSMIN'||firstScorer.verifiedStart!==true||firstScorer.start!==total.start||retainedFirst.length!==1||retainedFirst[0].observations.length!==0)return fallback;
 return {ids:['goals','totals','first','forecast'],selectedScorerKey:goal.key,reasons:{
  goals:'Jeannot scored after an 8% pregame chance of scoring at least once.',
  totals:'Six or more goals had a 58.5% pregame chance. The game finished at five.',
  first:'Jeannot scored first. His pregame first-scorer chance is unavailable.',
  forecast:'Minnesota matched its four-goal forecast; Boston finished 1.5 goals below.'
 }};
}
