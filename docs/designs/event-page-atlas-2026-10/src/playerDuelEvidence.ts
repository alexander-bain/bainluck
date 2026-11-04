import {probabilityLabel} from './probabilityLabel.ts';
import raw from './playerDuel.json' with {type:'json'};
export const duelWire=raw;
export const duelStart=Date.parse('2026-06-04T00:30:00Z')/1000;
export const duelEvent='KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8';
export const duelWinnerEvent='KXNBAGAME-26JUN03NYKSAS';
export type DuelPhase='before'|'final';
export type DuelWindow='match'|'all';
export type DuelFamily='winner'|'duel';
export type DuelPoint={at:number;p:number;volume:number};
const scalar=(v:unknown)=>typeof v==='number'?v:typeof v==='string'&&/^\d+(\.\d+)?$/.test(v)?Number(v):NaN;
export const duelCents=(p:number)=>probabilityLabel(p).replace('%','¢');
export function duelSeries(family:DuelFamily='winner',phase:DuelPhase='final',window:DuelWindow='all',wire=raw){
 const event=family==='winner'?wire.winnerEvent:wire.duelEvent,expected=family==='winner'?duelWinnerEvent:duelEvent,expectedSeries=family==='winner'?'KXNBAGAME':'KXNBAH2H3PT';
 if(event.event_ticker!==expected||event.series_ticker!==expectedSeries)return [];
 const markets=family==='winner'?wire.winnerMarkets.markets:wire.duelMarkets.markets,keys=family==='winner'?['NYK','SAS']:['JCHAMPAGNIE30','OANUNOBY8'];
 return keys.flatMap((key,index)=>{
  const ticker=`${expected}-${key}`,matches=markets.filter(m=>m.ticker===ticker&&m.event_ticker===expected),histories=wire.histories.filter(h=>h.ticker===ticker);
  if(matches.length!==1||histories.length!==1)return [];
  const original=matches[0];
  if(family==='duel'&&(!original.rules_primary.startsWith(`If ${['Julian Champagnie','OG Anunoby'][index]} records more made three pointers than ${['OG Anunoby','Julian Champagnie'][index]} in the full game`)||!original.rules_primary.includes('more made three pointers')||!original.rules_primary.includes('New York vs San Antonio')||!original.rules_primary.includes('Jun 3, 2026')||!original.rules_secondary.includes('all markets resolve to 50/50')))return [];
  const open=Date.parse(original.open_time)/1000,close=Date.parse(original.close_time)/1000;
  if(!Number.isFinite(open)||!Number.isFinite(close)||open>=duelStart||close<=duelStart)return [];
  const counts=new Map<number,number>();for(const c of histories[0].candlesticks)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
  const all=histories[0].candlesticks.flatMap(c=>{const p=scalar(c.price.close),volume=scalar(c.volume),at=c.end_period_ts;return Number.isFinite(p)&&p>=0&&p<=1&&Number.isFinite(volume)&&volume>0&&Number.isSafeInteger(at)&&at%60===0&&at>open&&at-60<close&&counts.get(at)===1?[{at,p,volume}]:[]}).sort((a,b)=>a.at-b.at),before=all.filter(p=>p.at<duelStart),baseline=before.at(-1)??null;
  return [{key,ticker,name:family==='winner'?['Knicks','Spurs'][index]:['Champagnie','Anunoby'][index],original,points:(phase==='before'?before:all).filter(p=>window==='all'||p.at>=duelStart-3600),baseline,result:phase==='final'&&original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null,meaning:family==='winner'?'win-chance' as const:'half-payout-tie' as const}];
 });
}
export const duelTimes=(series=duelSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function duelScore(phase:DuelPhase='final',wire=raw){
 const header=wire.header,comp=header.competitions[0];
 if(phase!=='final'||header.id!=='401859963'||header.competitions.length!==1||comp.id!=='401859963'||comp.date!=='2026-06-04T00:30Z'||comp.status.type.name!=='STATUS_FINAL'||!comp.status.type.completed)return null;
 const ny=comp.competitors.filter(c=>c.id==='18'&&c.team.displayName==='New York Knicks'),sa=comp.competitors.filter(c=>c.id==='24'&&c.team.displayName==='San Antonio Spurs');
 return ny.length===1&&sa.length===1&&ny[0].score==='105'&&sa[0].score==='95'&&ny[0].winner&&!sa[0].winner?{knicks:105,spurs:95}:null;
}
export function duelPlayers(phase:DuelPhase='final',wire=raw){
 const identities=[{key:'JCHAMPAGNIE30',id:'4592479',team:'24',name:'Julian Champagnie'},{key:'OANUNOBY8',id:'3934719',team:'18',name:'OG Anunoby'}];
 return identities.map(identity=>{
  const teams=wire.boxscore.players.filter(t=>t.team.id===identity.team),stats=teams.flatMap(t=>t.statistics.filter(s=>s.keys.filter(k=>k==='threePointFieldGoalsMade-threePointFieldGoalsAttempted').length===1)),rows=stats.flatMap(s=>s.athletes.filter(a=>a.athlete.id===identity.id&&a.athlete.displayName===identity.name).map(a=>({a,s})));
  if(teams.length!==1||rows.length!==1)return {...identity,headshot:null,actual:null};
  const {a,s}=rows[0],value=a.stats[s.keys.indexOf('threePointFieldGoalsMade-threePointFieldGoalsAttempted')],match=/^(\d+)-(\d+)$/.exec(value??''),minutes=Number(a.stats[s.keys.indexOf('minutes')]);
  const made=match?Number(match[1]):NaN,attempts=match?Number(match[2]):NaN;
  const valid=phase==='final'&&duelScore(phase,wire)!==null&&a.didNotPlay===false&&Number.isFinite(minutes)&&minutes>0&&Number.isSafeInteger(made)&&Number.isSafeInteger(attempts)&&made>=0&&attempts>=made;
  return {...identity,headshot:a.athlete.headshot?.href??null,actual:valid?{made,attempts}:null};
 });
}
export function duelReadout(p:DuelPoint|null|undefined,family:DuelFamily){return !p?{kind:'missing',label:'No recent price'}:family==='duel'?{kind:'contract-price',label:duelCents(p.p)}:{kind:'win-chance',value:p.p};}
export function duelOriginal(ticker:string,phase:DuelPhase,wire=raw){const row=[...duelSeries('winner',phase,'all',wire),...duelSeries('duel',phase,'all',wire)].find(s=>s.ticker===ticker);if(!row)return null;const m=row.original;return phase==='final'?{market:m,history:wire.histories.find(h=>h.ticker===ticker)}:{market:{ticker:m.ticker,event_ticker:m.event_ticker,title:m.title,yes_sub_title:m.yes_sub_title,rules_primary:m.rules_primary,rules_secondary:m.rules_secondary,open_time:m.open_time},history:row.points,cutoff:'2026-06-04T00:30:00Z'};}

export function duelComparison(phase:DuelPhase='final',wire=raw){const players=duelPlayers(phase,wire);const a=players[0].actual,b=players[1].actual;if(!a||!b)return null;return {margin:a.made-b.made,equalAccuracy:a.attempts>0&&b.attempts>0&&a.made*b.attempts===b.made*a.attempts};}

/** A half-payout value cannot isolate an outright winning probability. */
export function duelPregameWinChance(row:ReturnType<typeof duelSeries>[number]|undefined){
 if(!row)return {value:null,reason:"missing_contract"};
 if(row.meaning!=="win-chance")return {value:null,reason:"tie_splits_payout"};
 return {value:row.baseline?.p??null,reason:row.baseline?"recorded":"missing_observation"};
}
