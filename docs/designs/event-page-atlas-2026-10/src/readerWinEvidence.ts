import halfEvent from './halfEvent.json' with {type:'json'};
import half from './halfEvidence.json' with {type:'json'};
import tennisFinal from './tennisFinal.json' with {type:'json'};
import tennisPre from './tennisPropPregame.json' with {type:'json'};
import {probabilityLabel} from './probabilityLabel.ts';
import atlas from './atlas.json' with {type:'json'};
import finals from './finalHeaders.json' with {type:'json'};
import captures from './headlineCaptures.json' with {type:'json'};
import nfl from './nflCaptures.json' with {type:'json'};
import soccer from './soccerCaptures.json' with {type:'json'};
import soccerPre from './soccerPregameHeadline.json' with {type:'json'};
import {retainedCombatWinnerHistory} from './combatWinnerHistory.ts';
import {officialCombatFinal} from './combatOfficialFinal.ts';
import {reportedEsportsFinal} from './esportsFinalScore.ts';
import {retainedEsportsWinnerHistory} from './esportsWinnerHistory.ts';
import {retainedSoccerHistory} from './soccerFinalHistory.ts';
export type ReaderEvent={key:string;detail:Record<string,unknown>};
export type ReaderChance={name:string;baseline:number;baselineAt:string|null;recorded?:number};
export type ReaderWinContext={label:string;state:string;at:string|null;rows:ReaderChance[];note:string;source:string;unavailable:string|null;resultSource?:{label:string;url:string}};
const binding=['id','home_team','away_team','commence_time','status','completed_at','home_score','away_score','quality_hold'];
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const same=(a:Record<string,unknown>,b:Record<string,unknown>,keys:string[])=>keys.every(k=>stable(a[k]??null)===stable(b[k]??null));
const valid=(p:unknown):p is number=>typeof p==='number'&&Number.isFinite(p)&&p>=0&&p<=1;
const modeNote=(mode:string)=>mode==='loading'?'Loading win chances':mode==='error'?'Win chances unavailable':'No recent price';
/** Archived specimen adapter only. Never takes a prop price or derives chance from result. */
export function readerWinContext(ev:ReaderEvent,mode='captured'):ReaderWinContext|null{
 const d=ev.detail;
 const original=ev.key==='nba-half'?halfEvent.detail:ev.key==='nfl-live'&&d.status==='completed'?nfl.detail:ev.key==='soccer'&&d.status==='completed'?soccer.detail:atlas.events.find(e=>e.key===ev.key)?.detail;
 if(!original||!same(d,original,binding)||d.quality_hold)return null;
 const names=[String(d.home_team),String(d.away_team)];
 const pair=(home:number,away:number,at:string|null):ReaderChance[]=>[{name:names[0],baseline:home,baselineAt:at},{name:names[1],baseline:away,baselineAt:at}];
 const state=d.status==='completed'?`Final · ${d.home_score}–${d.away_score}${ev.key==='tennis'?' sets':''}`:d.status==='live'?`${d.home_score}–${d.away_score} · ${String((original.espn as {period?:string}|undefined)?.period??'In-game capture')}`:d.status==='suspended'?'Suspended · result unconfirmed':'Pre-match capture';
 const common={state,at:null,unavailable:null};
 if(ev.key==='tennis-final'){
  const b=tennisPre.headline;
  if(d.status!=='completed'||!same(d,original,['prematch_odds','score_source','score_observed_at','linescore'])||
   tennisPre.eventID!==d.id||tennisFinal.eventID!==d.id||!tennisPre.verifiedStart||tennisPre.start!==d.commence_time||
   tennisFinal.home!==names[0]||tennisFinal.away!==names[1]||tennisFinal.homeSets!==d.home_score||tennisFinal.awaySets!==d.away_score||
   !valid(b.home)||!valid(b.away)||b.home!==tennisFinal.prematchHome||b.away!==tennisFinal.prematchAway||
   !Number.isFinite(Date.parse(b.at))||Date.parse(b.at)>=Date.parse(tennisPre.start))return null;
  return {...common,state:`Final · ${tennisFinal.homeSets}–${tennisFinal.awaySets} sets · ${tennisFinal.homeGames}–${tennisFinal.awayGames} games`,label:'Pre-match win chances · Kalshi',rows:pair(b.home,b.away,b.at),note:`Match-winner quote recorded before the verified start. Separate opening sportsbook probabilities are not substituted. Final score observed ${tennisFinal.scoreAt}; sets and games are different units. A settled result supplies no probability.`,source:'tennisPropPregame.json + tennisFinal.json · full-match winner'};
 }
 if(ev.key==='nba-half'){
  const b=half.winnerBaseline;
  if(d.status!=='completed'||!same(d,original,['score_source','score_observed_at'])||half.eventID!==d.id||half.start!==d.commence_time||
   half.retainedCatalog.home_team!==names[0]||half.retainedCatalog.away_team!==names[1]||half.homeFinal!==d.home_score||half.awayFinal!==d.away_score||
   !valid(b.home_probability)||!Number.isFinite(Date.parse(b.timestamp))||Date.parse(b.timestamp)>=Date.parse(half.start))return null;
  return {...common,label:'Pregame win chances · full game',rows:pair(b.home_probability,1-b.home_probability,b.timestamp),note:`Last retained pregame Bain Luck blend; away is its documented binary complement. These are full-game winner chances, not chances of a halftime lead. Final score observed ${half.actualObservedAt}. Halftime was ${half.homeHalf}–${half.awayHalf}; its exact observation time is unavailable. Neither score supplies a probability.`,source:'halfEvidence.json + halfEvent.json · full-game winner'};
 }
 if(ev.key==='soccer'){
  if(d.status==='completed'){
   const p=retainedSoccerHistory.filter(p=>p.pregame).at(-1);if(!p)return null;
   return {...common,label:'Last pre-match win chances',rows:[...pair(p.home,p.away,p.at).slice(0,1),{name:'Draw',baseline:p.draw,baselineAt:p.at},...pair(p.home,p.away,p.at).slice(1)],note:'Three supplied Kalshi probabilities. Not normalized; a draw is its own outcome. The final result never supplies a price.',source:'soccerFinalHistory.json · full-event winner'};
  }
  if(d.status==='scheduled')return {...common,label:'Pre-match win chances',rows:soccerPre.rows.map(r=>({name:r.name==='Tie'?'Draw':r.name,baseline:r.chance,baselineAt:r.at})),note:'Three supplied Kalshi probabilities with independent observation times; 99.5% total is not normalized. The opening blend is incomplete.',source:'soccerPregameHeadline.json · full-event winner'};
  return null;
 }
 if(ev.key==='mma'||ev.key==='esports'){
  const p=(ev.key==='mma'?retainedCombatWinnerHistory:retainedEsportsWinnerHistory).filter(p=>p.pregame).at(-1);if(!p)return null;
  if(ev.key==='mma'&&officialCombatFinal)return {...common,state:'Final · Kopylov won · TKO · R1, 3:12',label:'Last pre-match win chances',rows:pair(p.home,p.away,p.at),note:'UFC confirms Roman Kopylov defeated Ateba Gautier by TKO (strikes), Round 1 at 3:12. This is elapsed round time, not an exact finish timestamp. The archived feed still says suspended. Contract results and conflicts remain independent; the result supplies no new probability.',source:'combatWinnerHistory.json + combatOfficialFinal.json',resultSource:{label:'Official UFC result',url:officialCombatFinal.source.url}};
  if(ev.key==='esports'&&reportedEsportsFinal)return {...common,state:'Final · Nice Try 13–1 Flame Hard · rounds · Map 1 Dust2',label:'Last pre-match win chances',rows:pair(p.home,p.away,p.at),note:'Scores24 reports Nice Try won 13–1 rounds (1–0 maps). The archived feed still says suspended; contract settlement stays independent. Historical probabilities retain the feed start reference, with no inferred finish time or 100% endpoint.',source:'esportsWinnerHistory.json + esportsFinalScore.json',resultSource:{label:'Reported match score · Scores24',url:reportedEsportsFinal.source.url}};
  return {...common,label:'Last pre-match win chances',rows:pair(p.home,p.away,p.at),unavailable:'Current chances unconfirmed',note:'Last retained observation before verified start. Away is the documented binary complement of the home aggregate. Suspended status and resolved props do not establish a match result.',source:ev.key==='mma'?'combatWinnerHistory.json':'esportsWinnerHistory.json'};
 }
 const f=finals.find(f=>f.id===ev.key);
 if(d.status==='completed'&&f&&same(d,original,['opening_odds'])&&f.home===names[0]&&f.away===names[1]&&f.homeScore===d.home_score&&f.awayScore===d.away_score){
  return {...common,label:'Pregame win chances · opening',rows:pair(f.homeBaseline,f.awayBaseline,f.baselineAt),note:'Historical opening probabilities. Exact opening quote time is unavailable. Final score and win chance are separate facts; the result is never plotted as 100%.',source:f.source};
 }
 const c=captures.find(c=>c.key===ev.key);
 if(d.status==='live'&&c&&same(d,original,['opening_odds','current_odds','espn'])&&c.eventID===d.id&&c.home===names[0]&&c.away===names[1]){
  const odds=d.current_odds as {home_probability:unknown;away_probability:unknown};
  if(!valid(odds.home_probability)||!valid(odds.away_probability))return null;
  const rows=pair(c.homeBaseline,c.awayBaseline,c.baselineAt);
  if(mode==='captured'){rows[0].recorded=odds.home_probability;rows[1].recorded=odds.away_probability;}
  return {...common,label:mode==='captured'?'Recorded in-game win chances':'Pregame win chances · opening',rows,at:mode==='captured'?c.chanceAt:null,unavailable:mode==='captured'?null:modeNote(mode),note:`Archived blend, not live. Recorded chance: ${c.chanceAt}. Actual score observed ${c.scoreAt}; it is not the score at an inspected historical moment. Opening quote time unavailable. Last recorded quote: ${names[0]} ${probabilityLabel(odds.home_probability)}; ${names[1]} ${probabilityLabel(odds.away_probability)}.`,source:`headlineCaptures.json + atlas.json · event ${c.eventID}`};
 }
 return null;
}
