import raw from './rugbyMatch.json' with {type:'json'};
export const rugbyWire=raw;
export const rugbyEvent='KXSIXNATIONSMATCH-26MAR14ENGFRA';
export const rugbyStart=Date.parse('2026-03-14T20:10:00Z')/1000;
export type RugbyPhase='before'|'final';
export type RugbyWindow='match'|'all';
export type RugbyPoint={at:number;p:number;volume:number};
const number=(v:unknown)=>typeof v==='number'?v:typeof v==='string'&&/^\d+(\.\d+)?$/.test(v)?Number(v):NaN;
export function rugbySeries(phase:RugbyPhase='final',window:RugbyWindow='all',wire=raw){
 if(wire.event.event_ticker!==rugbyEvent||wire.event.series_ticker!=='KXSIXNATIONSMATCH'||wire.event.mutually_exclusive!==true||wire.listedStart!=='2026-03-14T20:10:00Z')return [];
 return ['FRA','ENG','TIE'].flatMap((key,index)=>{
  const ticker=`${rugbyEvent}-${key}`,markets=wire.markets.markets.filter(m=>m.ticker===ticker&&m.event_ticker===rugbyEvent),histories=wire.histories.filter(h=>h.ticker===ticker);
  if(markets.length!==1||histories.length!==1)return [];
  const original=markets[0];if(original.yes_sub_title!==['France','England','Tie'][index]||!original.rules_primary.includes('France vs England')||!original.rules_primary.includes('Mar 14, 2026'))return [];
  const open=Date.parse(original.open_time)/1000,close=Date.parse(original.close_time)/1000;
  if(!Number.isFinite(open)||!Number.isFinite(close)||open>=rugbyStart||close<=rugbyStart)return [];
  const counts=new Map<number,number>();for(const c of histories[0].candlesticks)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
  const all=histories[0].candlesticks.flatMap(c=>{const p=number(c.price.close),volume=number(c.volume),at=c.end_period_ts;return Number.isFinite(p)&&p>=0&&p<=1&&Number.isFinite(volume)&&volume>0&&Number.isSafeInteger(at)&&at%60===0&&at>open&&at-60<close&&counts.get(at)===1?[{at,p,volume}]:[]}).sort((a,b)=>a.at-b.at);
  const before=all.filter(p=>p.at<rugbyStart),baseline=before.at(-1)??null;
  const points=(phase==='before'?before:all).filter(p=>window==='all'||p.at>=rugbyStart-3600);
  const result=phase==='final'&&original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null;
  return [{key,ticker,name:['France','England','Draw'][index],original,points,baseline,result}];
 });
}
export const rugbyTimes=(series=rugbySeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function rugbySegments(points:RugbyPoint[]){const segments:RugbyPoint[][]=[];for(const p of points){const last=segments.at(-1);if(last&&p.at-last.at(-1)!.at===60)last.push(p);else segments.push([p])}return segments;}
export function rugbyExact(ticker:string,at:number,series=rugbySeries()){return series.find(s=>s.ticker===ticker)?.points.find(p=>p.at===at)??null;}
export function rugbyScore(phase:RugbyPhase='final',wire=raw){
 if(phase!=='final'||wire.event.event_ticker!==rugbyEvent||wire.score.eventId!=='602516'||wire.score.competitionId!=='602516'||!wire.score.status.type.completed||wire.score.status.type.name!=='STATUS_FINAL')return null;
 const france=wire.score.competitors.filter(c=>c.id==='9'&&c.name==='France'),england=wire.score.competitors.filter(c=>c.id==='1'&&c.name==='England');
 if(france.length!==1||england.length!==1||france[0].score!=='48'||england[0].score!=='46'||!france[0].winner||england[0].winner)return null;
 return {france:48,england:46,winner:'France'};
}
export function rugbyLow(wire=raw){const row=rugbySeries('final','all',wire).find(s=>s.key==='FRA');return row?.points.filter(p=>p.at>=rugbyStart).reduce<RugbyPoint|null>((lo,p)=>!lo||p.p<lo.p?p:lo,null)??null;}
export function rugbyOriginal(ticker:string,phase:RugbyPhase,wire=raw){const row=rugbySeries(phase,'all',wire).find(s=>s.ticker===ticker);if(!row)return null;const m=row.original;return phase==='final'?{market:m,history:wire.histories.find(h=>h.ticker===ticker)}:{market:{ticker:m.ticker,event_ticker:m.event_ticker,title:m.title,yes_sub_title:m.yes_sub_title,rules_primary:m.rules_primary,open_time:m.open_time},history:row.points,cutoff:wire.listedStart};}
