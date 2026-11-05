import raw from './hockeyLive.json' with {type:'json'};
export type HockeyLiveWire=typeof raw;
export type HockeyLiveStage=HockeyLiveWire['stages'][number];
export function hockeyLiveSnapshot(index:number,w:HockeyLiveWire=raw){
 if(w.eventID!==15169793||w.espnID!=='401891814'||w.retrospective!==true||w.recordedStart!=='2026-10-04T00:14:32+00:00'||w.freshnessSeconds!==300)return null;
 const baseline=w.winnerBaseline;
 if(!baseline||!Number.isFinite(baseline.home)||baseline.home<0||baseline.home>1||Math.abs(baseline.home+baseline.away-1)>1e-9||Date.parse(baseline.at)!==baseline.t||baseline.t>=Date.parse(w.listedStart))return null;
 const stage=w.stages[index];if(!stage||!Number.isInteger(index)||stage.t!==Date.parse(stage.at)/1000||stage.t<Date.parse(w.recordedStart)/1000||stage.t>=Date.parse(w.recordedEnd)/1000)return null;
 const unique=w.beforeProps.filter(p=>w.beforeProps.filter(q=>q.key===p.key).length===1);
 const props=unique.map(p=>{
  const matches=w.contracts.filter(c=>c.key===p.key&&c.kind===p.family&&c.player===p.player&&c.threshold===p.count);
  const c=matches.length===1?matches[0]:null;
  const observations=c?.observations.filter(o=>o.t>=Date.parse(w.recordedStart)/1000&&o.t<=stage.t&&Date.parse(o.at)/1000===o.t&&o.volume>0&&o.value>=0&&o.value<=1&&c.observations.filter(q=>q.t===o.t).length===1)??[];
  const last=observations.reduce((a,o)=>!a||o.t>a.t?o:a,null as typeof observations[number]|null);
  const recent=last&&stage.t-last.t<=w.freshnessSeconds?last:null;
  const people=c?.playerID?stage.stats.filter(a=>a.id===c.playerID&&a.name===c.player&&a.team===c.team):[];
  const person=people.length===1?people[0]:null;
  const stats=person&&[person.goals,person.assists,person.points].every(n=>Number.isInteger(n)&&n>=0)&&person.points===person.goals+person.assists?{goals:person.goals,assists:person.assists,points:person.points}:null;
  const actual=c&&stats?stats[c.kind as 'points'|'assists']:null;
  const baseline=p.chance!==null&&p.at!==null&&Date.parse(p.at)<Date.parse(w.listedStart)?{value:p.chance,at:p.at}:null;
  // Whitelist only. Never spread a final row or venue settlement into the live reader.
  return {key:p.key,title:p.title,market:p.market,source:p.source,marketID:p.marketID,family:p.family,player:p.player,team:p.team,threshold:p.count,baseline,recent,last,actual,stats,ticker:c?.ticker??null,rules:c?.rules??null};
 });
 const winner=w.winner.filter(p=>p.t<=stage.t&&p.t>=Date.parse(w.listedStart)/1000&&p.home>=0&&p.home<=1&&Math.abs(p.home+p.away-1)<1e-9&&w.winner.filter(q=>q.t===p.t).length===1);
 const last=winner.at(-1),chance=last&&stage.t-last.t<=w.freshnessSeconds?last:null;
 return {stage,props,winner,chance,markers:w.markers.filter(m=>m.t<=stage.t).sort((a,b)=>a.t-b.t),retrospective:true as const};
}
export type HockeyLiveProp=NonNullable<ReturnType<typeof hockeyLiveSnapshot>>['props'][number];
export function hockeyLiveProfiles<T extends {family:string;player:string|null;threshold:number|null}>(props:T[],kind:'points'|'assists'){
 const rows=props.filter(p=>p.family===kind&&p.player!==null);
 const names=[...new Set(rows.map(r=>r.player!))],preferred=['Kirill Kaprizov','Quinn Hughes','Joel Eriksson Ek'];
 names.sort((a,b)=>(preferred.includes(a)?preferred.indexOf(a):99)-(preferred.includes(b)?preferred.indexOf(b):99)||a.localeCompare(b));
 return names.map(name=>({name,records:rows.filter(r=>r.player===name).sort((a,b)=>a.threshold!-b.threshold!)}));
}
export function liveGameState(stage:HockeyLiveStage){return stage.intermission?`${stage.period===1?'First':'Second'} intermission`:`${stage.period===2?'2nd':'3rd'} · ${Math.floor(stage.remaining/60)}:${String(stage.remaining%60).padStart(2,'0')} left`;}
export {raw as hockeyLive};
