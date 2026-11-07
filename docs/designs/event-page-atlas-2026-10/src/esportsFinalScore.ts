import raw from './esportsFinalScore.json' with {type:'json'};
import history from './esportsWinnerHistory.json' with {type:'json'};
import {esportsQuestion,type EsportsRow} from './esportsEvidence.ts';
export type EsportsFinalWire=typeof raw;
type MatchIdentity={event_id:number;home_team:string;away_team:string;commence_time:string};
/** Source-bound design fixture, not a production match/result adapter. */
export function qualifyEsportsFinal(w:EsportsFinalWire,event:MatchIdentity){
 if(w.eventID!==15322123||event.event_id!==w.eventID||w.home!==event.home_team||w.away!==event.away_team||w.home!=='Nice Try'||w.away!=='Flame Hard')return null;
 if(w.eventDate!=='2026-10-01'||!Number.isFinite(Date.parse(event.commence_time))||new Date(event.commence_time).toISOString().slice(0,10)!==w.eventDate||w.competition!=='FOX Legacy Cup'||w.stage!=='Group B'||w.game!=='Counter-Strike 2'||w.format!=='BO1'||w.status!=='finished')return null;
 if(JSON.stringify(w.providerOrder)!==JSON.stringify(['Flame Hard','Nice Try'])||JSON.stringify(w.mapsWon)!==JSON.stringify([0,1])||w.map.number!==1||w.map.name!=='Dust2'||JSON.stringify(w.map.roundsWon)!==JSON.stringify([1,13])||w.actualStartAt!==null||w.completedAt!==null)return null;
 if(w.source.publisher!=='Scores24'||w.source.url!=='https://scores24.live/ru/csgo/m-01-10-2026-flame-hard-nice-try'||!/^[a-f0-9]{64}$/.test(w.source.sha256)||!Number.isFinite(Date.parse(w.source.capturedAt)))return null;
 const homeIndex=w.providerOrder.indexOf(w.home),awayIndex=w.providerOrder.indexOf(w.away);
 return {...w,homeRounds:w.map.roundsWon[homeIndex],awayRounds:w.map.roundsWon[awayIndex],homeMaps:w.mapsWon[homeIndex],awayMaps:w.mapsWon[awayIndex],winner:w.home};
}
export const reportedEsportsFinal=qualifyEsportsFinal(raw,history);
export function esportsMarginActual<T extends EsportsRow>(rows:T[]){
 const prop=esportsQuestion(rows),final=reportedEsportsFinal;
 if(!final||prop?.kind!=='roundMargin')return null;
 const margin=final.homeRounds-final.awayRounds,minimum=7;
 return {margin,minimum,beyondMinimum:margin-minimum,homeRounds:final.homeRounds,awayRounds:final.awayRounds,mapName:final.map.name};
}
