import wire from './hockeyContributions.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
import {eventReaderTime} from './eventReaderTime.ts';
export type ContributionKind='points'|'assists';
export type ContributionPhase='before'|'final';
export type ContributionWire=typeof wire;
export type ContributionRow=CatalogEvidenceRow&{actual?:unknown;player_team?:unknown};
const stable=(value:unknown):string=>JSON.stringify(value,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const markets={points:{id:64871068,ticker:'KXNHLPTS-26OCT03BOSMIN'},assists:{id:64870807,ticker:'KXNHLAST-26OCT03BOSMIN'}};
export function hockeyContribution(row:ContributionRow,eventID:unknown,kind:ContributionKind,phase:ContributionPhase='final',w:ContributionWire=wire){
 const family=markets[kind];
 if(eventID!==15169793||w.eventID!==eventID||w.espnID!=='401891814'||w.verifiedStart!==true||w.start!=='2026-10-04T00:00:00+00:00'||w.home!=='Minnesota Wild'||w.away!=='Boston Bruins'||JSON.stringify(w.score)!=='[4,1]')return null;
 const matches=w.points.filter(p=>p.key===row.key&&p.kind===kind&&p.marketID===family.id&&p.eventTicker===family.ticker&&stable(p.original)===stable(row));
 if(matches.length!==1)return null;
 const p=matches[0];
 if(row.source!=='kalshi'||row._inverted!==false||row._market_id!==family.id||p.threshold!==row.threshold||!Number.isInteger(p.threshold)||p.threshold<1||p.threshold>3||!p.ticker.startsWith(family.ticker+'-')||row.outcome_name!==p.player+': '+p.threshold+'+')return null;
 const observations=p.observations.filter(o=>Number.isFinite(Date.parse(o.at))&&Date.parse(o.at)<Date.parse(w.start));
 const last=observations.reduce((a,o)=>!a||Date.parse(o.at)>Date.parse(a.at)?o:a,null as typeof observations[number]|null);
 const baseline=last&&Number.isFinite(last.value)&&last.value>0&&last.value<1&&Number.isFinite(last.volume)&&last.volume>0&&observations.filter(o=>o.at===last.at).length===1?{value:last.value,at:last.at,volume:last.volume}:null;
 const a=p.actual;
 const official=a!==null&&a.name===p.player&&[a.goals,a.assists,a.points].every(n=>Number.isInteger(n)&&n>=0)&&a.points===a.goals+a.assists&&a.team===(row.player_team==='home'?w.home:row.player_team==='away'?w.away:null)&&(row.actual==null||row.actual===a[kind])?a:null;
 const actual=phase==='final'?official:null;
 const result=phase==='final'&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Reached':'Missed'):null;
 return {key:p.key,kind,player:p.player,threshold:p.threshold,ticker:p.ticker,rules:p.rules,baseline,actual,result,row};
}
export function contributionBaseline(row:ContributionRow,w:ContributionWire=wire){
 for(const kind of ['points','assists'] as const){const record=hockeyContribution(row,15169793,kind,'before',w);if(record)return record.baseline;}
 return null;
}
export function contributionBaselineNote(row:ContributionRow){const b=contributionBaseline(row);return b?'Pre-game trade · minute ending '+eventReaderTime.full(b.at):undefined;}
export function hockeyContributionProfiles<T extends ContributionRow>(rows:T[],eventID:unknown,kind:ContributionKind,phase:ContributionPhase='final',w:ContributionWire=wire){
 const records=rows.flatMap(row=>{const record=hockeyContribution(row,eventID,kind,phase,w);return record?[{...record,row}]:[]});
 const unique=records.filter(r=>records.filter(other=>other.key===r.key).length===1);
 const names=[...new Set(unique.map(r=>r.player))];
 const preferred=['Quinn Hughes','Kirill Kaprizov','Joel Eriksson Ek'];
 names.sort((a,b)=>{const ai=preferred.indexOf(a),bi=preferred.indexOf(b);return (ai<0?99:ai)-(bi<0?99:bi)||a.localeCompare(b)});
 return names.map(name=>({name,records:unique.filter(r=>r.player===name).sort((a,b)=>a.threshold-b.threshold)}));
}
export {wire as hockeyContributionEvidence};
