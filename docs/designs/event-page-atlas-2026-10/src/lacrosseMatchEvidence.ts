import raw from './lacrosseMatch.json' with {type:'json'};
export const lacrosseWire=raw;
export const lacrosseEvent='KXNCAAMLAXGAME-26MAY23SYRNOT';
export const lacrosseStart=Date.parse('2026-05-23T18:55:00Z')/1000;
export type LacrossePhase='before'|'final';
export type LacrosseWindow='match'|'all';
export type LacrossePoint={at:number;p:number;volume:number};
const number=(v:unknown)=>typeof v==='number'?v:typeof v==='string'&&/^\d+(\.\d+)?$/.test(v)?Number(v):NaN;
export function lacrosseSeries(phase:LacrossePhase='final',window:LacrosseWindow='all',wire=raw){
 if(wire.event.event_ticker!==lacrosseEvent||wire.event.series_ticker!=='KXNCAAMLAXGAME'||wire.event.mutually_exclusive!==true||wire.listedStart!=='2026-05-23T18:55:00Z')return [];
 return ['NOT','SYR'].flatMap((key,index)=>{
  const ticker=`${lacrosseEvent}-${key}`,markets=wire.markets.markets.filter(m=>m.ticker===ticker&&m.event_ticker===lacrosseEvent),histories=wire.histories.filter(h=>h.ticker===ticker);
  if(markets.length!==1||histories.length!==1)return [];
  const original=markets[0];if(!original.rules_primary.startsWith(`If ${['Notre Dame','Syracuse'][index]} wins the Syracuse vs Notre Dame men's college lacrosse game`)||original.yes_sub_title!==['Notre Dame','Syracuse'][index]||!original.rules_primary.includes('Syracuse vs Notre Dame')||!original.rules_primary.includes('May 23, 2026'))return [];
  const open=Date.parse(original.open_time)/1000,close=Date.parse(original.close_time)/1000;
  if(!Number.isFinite(open)||!Number.isFinite(close)||open>=lacrosseStart||close<=lacrosseStart)return [];
  const counts=new Map<number,number>();for(const c of histories[0].candlesticks)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
  const all=histories[0].candlesticks.flatMap(c=>{const p=number(c.price.close),volume=number(c.volume),at=c.end_period_ts;return Number.isFinite(p)&&p>=0&&p<=1&&Number.isFinite(volume)&&volume>0&&Number.isSafeInteger(at)&&at%60===0&&at>open&&at-60<close&&counts.get(at)===1?[{at,p,volume}]:[]}).sort((a,b)=>a.at-b.at);
  const before=all.filter(p=>p.at<lacrosseStart),baseline=before.at(-1)??null;
  const points=(phase==='before'?before:all).filter(p=>window==='all'||p.at>=lacrosseStart-3600);
  const result=phase==='final'&&original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null;
  return [{key,ticker,name:['Notre Dame','Syracuse'][index],original,points,baseline,result}];
 });
}
export const lacrosseTimes=(series=lacrosseSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function lacrosseSegments(points:LacrossePoint[]){const segments:LacrossePoint[][]=[];for(const p of points){const last=segments.at(-1);if(last&&p.at-last.at(-1)!.at===60)last.push(p);else segments.push([p])}return segments;}
export function lacrosseExact(ticker:string,at:number,series=lacrosseSeries()){return series.find(s=>s.ticker===ticker)?.points.find(p=>p.at===at)??null;}
export function lacrosseScore(phase:LacrossePhase='final',wire=raw){
 if(phase!=='final'||wire.event.event_ticker!==lacrosseEvent||wire.header.id!=='401870923'||wire.header.competitions.length!==1)return null;
 const h=wire.header.competitions[0],events=wire.scoreboard.events.filter(e=>e.id==='401870923');
 if(h.id!=='401870923'||h.date!=='2026-05-23T18:55Z'||!h.status.type.completed||h.status.type.name!=='STATUS_FINAL'||events.length!==1||events[0].competitions.length!==1)return null;
 const c=events[0].competitions[0];
 if(c.id!==h.id||c.date!==h.date||events[0].date!==h.date||!c.status.type.completed||c.status.type.name!=='STATUS_FINAL')return null;
 const keys=[{id:'87',name:'Notre Dame Fighting Irish',score:'15',winner:true},{id:'183',name:'Syracuse Orange',score:'7',winner:false}];
 const teams=keys.map(k=>{const hs=h.competitors.filter(t=>t.id===k.id&&t.team.displayName===k.name),ss=c.competitors.filter(t=>t.id===k.id&&t.team.displayName===k.name);return hs.length===1&&ss.length===1&&hs[0].score===k.score&&ss[0].score===k.score&&hs[0].winner===k.winner&&ss[0].winner===k.winner?ss[0]:null});
 if(teams.some(t=>t===null))return null;
 return {notreDame:15,syracuse:7,teams:teams.filter(t=>t!==null)};
}
export function lacrosseQuarters(phase:LacrossePhase='final',wire=raw){
 const score=lacrosseScore(phase,wire);if(!score)return [];
 const qs=score.teams.map(t=>[1,2,3,4].map(period=>{const rows=t.linescores.filter(s=>s.period===period);return rows.length===1&&Number.isSafeInteger(rows[0].value)&&rows[0].value>=0&&Number(rows[0].displayValue)===rows[0].value?rows[0].value:null}));
 if(qs.some((q,i)=>q.some(v=>v===null)||q.reduce<number>((sum,v)=>sum+(v??0),0)!==[15,7][i])||score.teams.some(t=>t.linescores.length!==4))return [];
 return [1,2,3,4].map((period,index)=>({period,notreDame:qs[0][index]!,syracuse:qs[1][index]!,notreDameTotal:qs[0].slice(0,index+1).reduce<number>((a,v)=>a+v!,0),syracuseTotal:qs[1].slice(0,index+1).reduce<number>((a,v)=>a+v!,0)}));
}
export function lacrosseOriginal(ticker:string,phase:LacrossePhase,wire=raw){const row=lacrosseSeries(phase,'all',wire).find(s=>s.ticker===ticker);if(!row)return null;const m=row.original;return phase==='final'?{market:m,history:wire.histories.find(h=>h.ticker===ticker)}:{market:{ticker:m.ticker,event_ticker:m.event_ticker,title:m.title,yes_sub_title:m.yes_sub_title,rules_primary:m.rules_primary,open_time:m.open_time},history:row.points,cutoff:wire.listedStart};}

export function lacrosseFinish(wire=raw){const qs=lacrosseQuarters('final',wire);if(qs.length!==4)return null;const last=qs[3],previous=qs[2];return {title:`A ${last.notreDame}–${last.syracuse} finish`,caption:`After Q3: Notre Dame ${previous.notreDameTotal}–${previous.syracuseTotal} Syracuse. Q4: ${last.notreDame}–${last.syracuse}.`};}
