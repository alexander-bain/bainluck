import raw from './aflMatch.json' with {type:'json'};
export const aflWire=raw;
export const aflEvent='KXAFLGAME-26SEP260030BRIFRE';
export const aflStart=Date.parse('2026-09-26T04:30:00Z')/1000;
export type AflPhase='before'|'final';
export type AflWindow='match'|'all';
export type AflPoint={at:number;p:number;volume:number};
const number=(v:unknown)=>typeof v==='number'?v:typeof v==='string'&&/^\d+(\.\d+)?$/.test(v)?Number(v):NaN;
export function aflSeries(phase:AflPhase='final',window:AflWindow='all',wire=raw){
 if(wire.event.event_ticker!==aflEvent||wire.event.series_ticker!=='KXAFLGAME'||wire.event.mutually_exclusive!==true||wire.listedStart!=='2026-09-26T04:30:00Z')return [];
 return ['BRI','FRE'].flatMap((key,index)=>{
  const ticker=`${aflEvent}-${key}`,markets=wire.markets.markets.filter(m=>m.ticker===ticker&&m.event_ticker===aflEvent),histories=wire.histories.filter(h=>h.ticker===ticker);
  if(markets.length!==1||histories.length!==1)return [];
  const original=markets[0],name=['Brisbane Lions','Fremantle Dockers'][index];
  if(original.rules_primary!==`If ${name} wins the Brisbane Lions vs Fremantle Dockers professional AFL game originally scheduled for Sep 26, 2026, then the market resolves to Yes.`||original.yes_sub_title!==name)return [];

  const open=Date.parse(original.open_time)/1000,close=Date.parse(original.close_time)/1000;
  if(!Number.isFinite(open)||!Number.isFinite(close)||open>=aflStart||close<=aflStart)return [];
  const counts=new Map<number,number>();for(const c of histories[0].candlesticks)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
  const all=histories[0].candlesticks.flatMap(c=>{const p=number((c.price as {close_dollars?:string}).close_dollars),volume=number(c.volume_fp),at=c.end_period_ts;return Number.isFinite(p)&&p>=0&&p<=1&&Number.isFinite(volume)&&volume>0&&Number.isSafeInteger(at)&&at%60===0&&at>open&&at-60<close&&counts.get(at)===1?[{at,p,volume}]:[]}).sort((a,b)=>a.at-b.at);
  const before=all.filter(p=>p.at<aflStart),baseline=before.at(-1)??null;
  const points=(phase==='before'?before:all).filter(p=>window==='all'||p.at>=aflStart-3600);
  const result=phase==='final'&&original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null;
  return [{key,ticker,name:['Brisbane','Fremantle'][index],original,points,baseline,result}];
 });
}
export const aflTimes=(series=aflSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function aflSegments(points:AflPoint[]){const segments:AflPoint[][]=[];for(const p of points){const last=segments.at(-1);if(last&&p.at-last.at(-1)!.at===60)last.push(p);else segments.push([p])}return segments;}
export function aflExact(ticker:string,at:number,series=aflSeries()){return series.find(s=>s.ticker===ticker)?.points.find(p=>p.at===at)??null;}
export function aflScore(phase:AflPhase='final',wire=raw){
 if(phase!=='final'||wire.event.event_ticker!==aflEvent||wire.header.id!=='1133711'||wire.header.competitions.length!==1)return null;
 const h=wire.header.competitions[0],events=wire.scoreboard.events.filter(e=>e.id==='1133711');
 if(h.id!=='1133711'||h.date!=='2026-09-26T04:30Z'||!h.status.type.completed||h.status.type.name!=='STATUS_FINAL'||events.length!==1||events[0].competitions.length!==1)return null;
 const c=events[0].competitions[0];
 if(c.id!==h.id||c.date!==h.date||events[0].date!==h.date||!c.status.type.completed||c.status.type.name!=='STATUS_FINAL')return null;
 const keys=[{id:'11',name:'Brisbane Lions',score:'96',winner:true},{id:'1',name:'Fremantle',score:'89',winner:false}];
 const teams=keys.map(k=>{const hs=h.competitors.filter(t=>t.id===k.id&&t.team.displayName===k.name),ss=c.competitors.filter(t=>t.id===k.id&&t.team.displayName===k.name);return hs.length===1&&ss.length===1&&hs[0].score===k.score&&ss[0].score===k.score&&hs[0].winner===k.winner&&ss[0].winner===k.winner?ss[0]:null});
 if(teams.some(t=>t===null))return null;
 return {brisbane:96,fremantle:89,teams:teams.filter(t=>t!==null)};
}
export function aflQuarters(phase:AflPhase='final',wire=raw){
 const score=aflScore(phase,wire);if(!score)return [];
 const summary=wire.header.competitions[0].competitors;
 const qs=score.teams.map(t=>[1,2,3,4].map(period=>{const rows=t.linescores.filter(s=>s.period===period),other=summary.find(s=>s.id===t.id)?.linescores[period-1];return rows.length===1&&Number.isSafeInteger(rows[0].value)&&rows[0].value>=0&&Number(rows[0].displayValue)===rows[0].value&&other?.value===rows[0].value?rows[0].value:null}));
 if(qs.some((q,i)=>q.some(v=>v===null)||q.reduce<number>((sum,v)=>sum+(v??0),0)!==[96,89][i])||score.teams.some(t=>t.linescores.length!==4)||summary.some(t=>t.linescores.length!==4))return [];
 return [1,2,3,4].map((period,index)=>({period,brisbane:qs[0][index]!,fremantle:qs[1][index]!,brisbaneTotal:qs[0].slice(0,index+1).reduce<number>((a,v)=>a+v!,0),fremantleTotal:qs[1].slice(0,index+1).reduce<number>((a,v)=>a+v!,0)}));
}
export function aflOriginal(ticker:string,phase:AflPhase,wire=raw){const row=aflSeries(phase,'all',wire).find(s=>s.ticker===ticker);if(!row)return null;const m=row.original;return phase==='final'?{market:m,history:wire.histories.find(h=>h.ticker===ticker)}:{market:{ticker:m.ticker,event_ticker:m.event_ticker,title:m.title,yes_sub_title:m.yes_sub_title,rules_primary:m.rules_primary,open_time:m.open_time},history:row.points,cutoff:wire.listedStart};}


export function aflLow(wire=raw){return aflSeries('final','all',wire).find(s=>s.key==='BRI')?.points.filter(p=>p.at>=aflStart).reduce<AflPoint|null>((low,p)=>!low||p.p<low.p?p:low,null)??null;}
export function aflMargins(wire=raw){return aflQuarters('final',wire).map(q=>({...q,margin:q.brisbaneTotal-q.fremantleTotal}));}
