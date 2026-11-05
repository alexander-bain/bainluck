import {readerTime} from './readerTime.ts';
import wire from './tennisPropPregame.json' with {type:'json'};
export type TennisPropWire=typeof wire;
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
export function tennisPropBaseline(row:unknown,w:TennisPropWire=wire){
 if(w.eventID!==15327291||w.verifiedStart!==true||w.start!=='2026-10-11T12:50:00+00:00')return null;
 const matches=w.points.filter(p=>stable(row)===stable(p.display)||stable(row)===stable(p.original));
 if(matches.length!==1)return null;
 const p=matches[0];
 if(p.marketID!==p.original._market_id||p.outcomeID!==p.original.contributor_outcome_ids[0]||p.source!==p.original.source)return null;
 const before=p.observations.filter(o=>Number.isFinite(Date.parse(o.at))&&Date.parse(o.at)<Date.parse(w.start));
 const last=before.reduce((a,o)=>!a||Date.parse(o.at)>Date.parse(a.at)?o:a,null as typeof before[number]|null);
 if(!last||last.kind!=='consensus'||!Number.isFinite(last.value)||last.value<=0||last.value>=1||before.filter(o=>Date.parse(o.at)===Date.parse(last.at)).length!==1)return null;
 return {value:last.value,at:last.at,source:p.source};
}
export function tennisPropNote(row:unknown){const b=tennisPropBaseline(row);return b?`${b.source==='kalshi'?'Kalshi':'Polymarket'} · recorded ${readerTime(b.at)} before the match. Historical quote; not current trading activity.${b.source==='kalshi'&&(row as {_market_id?:number})._market_id===65129355?` This contract observation predates the headline’s ${readerTime(wire.headline.at)} match-winner snapshot.`:""}`:undefined}
export {wire as tennisPropEvidence};
