import raw from './squashMatch.json' with {type:'json'};
export const squashWire=raw;
export const squashEvent='KXSQUASHMATCH-26JUN07ASSELI';
export const squashTickers=[`${squashEvent}-ASS`,`${squashEvent}-ELI`];
export type SquashPhase='before'|'final';
export type SquashWindow='all'|'day';
export type SquashPoint={at:number;p:number;volume:number};
const scalar=(s:unknown)=>typeof s==='number'?s:typeof s==='string'&&/^\d+(\.\d+)?$/.test(s)?Number(s):NaN;
export function squashSeries(phase:SquashPhase='final',window:SquashWindow='all',wire=raw){
 if(wire.event.event.event_ticker!==squashEvent||wire.event.event.series_ticker!=='KXSQUASHMATCH')return [];
 return squashTickers.flatMap((ticker,i)=>{
  const markets=wire.markets.markets.filter(m=>m.ticker===ticker&&m.event_ticker===squashEvent),histories=wire.histories.filter(h=>h.ticker===ticker);
  if(markets.length!==1||histories.length!==1)return [];
  const original=markets[0],name=['Mostafa Asal','Diego Elias'][i];
  if(original.yes_sub_title!==['Mostafa Assal','Diego Elias'][i])return [];
  const open=Date.parse(original.open_time)/1000,close=Date.parse(original.close_time)/1000,before=Date.parse(wire.beforeCutoff)/1000;
  if(!Number.isFinite(open)||!Number.isFinite(close)||open>=close||wire.beforeCutoff!=='2026-06-05T23:00:00Z')return [];
  const end=phase==='before'?before:close,start=window==='day'&&phase==='final'?before:open;
  const candles=histories[0].candlesticks,counts=new Map<number,number>();for(const c of candles)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
  const points:SquashPoint[]=candles.flatMap(c=>{
   const p=scalar(c.price.close),volume=scalar(c.volume),at=c.end_period_ts;
   return Number.isFinite(p)&&p>=0&&p<=1&&Number.isFinite(volume)&&volume>0&&Number.isSafeInteger(at)&&at%60===0&&at>start&&at<=end&&counts.get(at)===1?[{at,p,volume}]:[];
  }).sort((a,b)=>a.at-b.at);
  const result=phase==='final'&&original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null;
  return [{ticker,name,original,points,result,baseline:null}];
 });
}
export function squashScore(wire=raw){
 const s=wire.score;
 if(wire.event.event.event_ticker!==squashEvent||s.url!=='https://britishopensquash.info/2026-day-eight/'||s.reportDate!=='2026-06-06'||s.competition!=='2026 Quilter Cheviot British Open'||s.round!=='Semifinal'||s.players.join('|')!=='Mostafa Asal|Diego Elias')return null;
 if(s.games.length<3||s.games.length>5||s.gameWins.length!==2||!Number.isFinite(s.durationMinutes)||s.durationMinutes<=0)return null;
 const won=[0,0],steps:{game:number;points:number[];winner:number;won:number[]}[]=[];
 for(const [index,points] of s.games.entries()){
  if(points.length!==2||points.some(p=>!Number.isSafeInteger(p)||p<0)||Math.max(...won)>=3)return null;
  const hi=Math.max(...points),lo=Math.min(...points);if(hi<11||hi-lo<2||(hi>11&&hi-lo!==2))return null;
  const winner=points[0]>points[1]?0:1;won[winner]++;steps.push({game:index+1,points,winner,won:[...won]});
 }
 if(Math.max(...won)!==3||won.some((v,i)=>v!==s.gameWins[i]))return null;
 return {steps,won,totalPoints:[0,1].map(i=>s.games.reduce((n,g)=>n+g[i],0)),duration:s.durationMinutes,winner:won[0]>won[1]?0:1};
}
export const squashTimes=(series=squashSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function squashExact(ticker:string,at:number,series=squashSeries()){return series.find(s=>s.ticker===ticker)?.points.find(p=>p.at===at)??null;}
export function squashSegments(points:SquashPoint[]){const chunks:SquashPoint[][]=[];for(const p of points){const prior=chunks.at(-1);if(prior&&p.at-prior.at(-1)!.at===60)prior.push(p);else chunks.push([p])}return chunks;}
export function squashClock(times:number[]){
 const start=times[0]??Date.parse(raw.beforeCutoff)/1000,end=times.at(-1)??start;
 const gaps=times.slice(1).flatMap((t,i)=>t-times[i]>3600?[{start:times[i],end:t,kept:300}]:[]);
 const offset=(at:number)=>at-start-gaps.reduce((n,g)=>n+(at<=g.start?0:(Math.min(at,g.end)-g.start)*(1-g.kept/(g.end-g.start))),0),span=Math.max(60,offset(end));
 return {start,end,gaps,fraction:(at:number)=>offset(at)/span};
}

// A before-play reconstruction must not expose later settlement or trades in its original reader.
export function squashOriginal(ticker:string,phase:SquashPhase,wire=raw){
 const s=squashSeries(phase,'all',wire).find(row=>row.ticker===ticker);if(!s)return null;
 if(phase==='final')return {market:s.original,history:wire.histories.find(h=>h.ticker===ticker)};
 const m=s.original,cutoff=Date.parse(wire.beforeCutoff)/1000;
 return {market:{ticker:m.ticker,event_ticker:m.event_ticker,title:m.title,yes_sub_title:m.yes_sub_title,open_time:m.open_time,rules_primary:m.rules_primary,rules_secondary:m.rules_secondary},history:{ticker,candlesticks:wire.histories.find(h=>h.ticker===ticker)!.candlesticks.filter(c=>c.end_period_ts<=cutoff)}};
}
