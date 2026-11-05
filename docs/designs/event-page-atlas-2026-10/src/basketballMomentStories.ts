import {totalPregameRecord} from './totalPregame.ts';
import {marginRecord} from './marginPregame.ts';
import totals from './totalPregame.json' with {type:'json'};
import margins from './marginPregame.json' with {type:'json'};
import headers from './finalHeaders.json' with {type:'json'};
export const basketballFamilies=[{id:'margin',name:'Winning margin'},{id:'totals',name:'Scoring expectations'},{id:'forecast',name:'Score versus forecast'}] as const;
export type BasketballFamily=typeof basketballFamilies[number]['id'];
type Order={ids:BasketballFamily[];reasons:Partial<Record<BasketballFamily,string>>;selectedTotalKey:string|null};
/** One retained game's final-state policy, not connected AI or a universal surprise score. */
export function basketballMomentOrder(total=totals,margin=margins,header=headers.find(h=>h.id==='nba')!):Order {
 const fallback:Order={ids:basketballFamilies.map(c=>c.id),reasons:{},selectedTotalKey:null};
 const line=total.records.find(r=>r.outcomeID===240505185);
 if(total.eventID!==15320337||margin.eventID!==total.eventID||header.id!=='nba'||header.home!=='Los Angeles Clippers'||header.away!=='Golden State Warriors'||header.homeScore!==104||header.awayScore!==101||header.winner!=='home'||total.actual!==205||margin.actual!==3||total.forecast!==222.3||margin.forecast!==-2.7||header.projectedHome!==109.8||header.projectedAway!==112.5||header.projectionAt!==total.forecastAt||header.projectionAt!==margin.forecastAt||header.scoreAt!==total.actualAt||header.scoreAt!==margin.actualAt||!line||line.threshold!==206.5||line.value!==.825||line.result!=='Lost'||!line.at||!Number.isFinite(Date.parse(line.at))||Date.parse(line.at)>=Date.parse(total.start)||!Number.isFinite(Date.parse(total.start)))return fallback;
 let original:Record<string,unknown>;
 try{original=JSON.parse(line.originalJSON)}catch{return fallback}
 if(original.source!=='kalshi'||original._market_id!==63856441||original.threshold!==206.5||original.market_type!=='game_total'||original.is_winner!==false||original.resolution_source!=='api_settlement'||JSON.stringify(original.contributor_outcome_ids)!=='[240505185]')return fallback;
 return {ids:['totals','margin','forecast'],selectedTotalKey:line.key,reasons:{
  totals:'Over 206.5 had an 82.5% pregame chance. The game finished at 205.',
  margin:'Clippers won by 3 after a pregame forecast of Warriors by 2.7.',
  forecast:'Clippers finished 5.8 points below their forecast; Warriors, 11.5 below.'
 }};
}

/** Separately observed final score; never rewrites the original contract's actual field. */
export function basketballActual(row:unknown){
 if(totalPregameRecord(row))return {value:`${totals.actual} combined points`,at:totals.actualAt};
 if(marginRecord(row))return {value:`Clippers by ${margins.actual} points`,at:margins.actualAt};
 return null;
}
