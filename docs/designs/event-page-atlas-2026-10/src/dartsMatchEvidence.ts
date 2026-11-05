import raw from './dartsMatch.json' with {type:'json'};
export const dartsWire=raw;
export const dartsEvent='KXDARTSMATCH-26OCT120850JMCESOCK';
export const dartsTickers=[dartsEvent+'-JMCE',dartsEvent+'-SOCK'];
export type TradePoint={at:number;p:number;volume:number};
export function dartsSeries(wire=raw){
 if(wire.event.event.event_ticker!==dartsEvent||wire.event.event.series_ticker!=='KXDARTSMATCH')return [];
 return dartsTickers.flatMap(ticker=>{
  const markets=wire.event.markets.filter(m=>m.ticker===ticker&&m.event_ticker===dartsEvent);
  const histories=wire.history.markets.filter(m=>m.market_ticker===ticker);
  if(markets.length!==1||histories.length!==1)return [];
  const original=markets[0],end=Date.parse(original.close_time)/1000,start=Date.parse(original.open_time)/1000;
  const points:TradePoint[]=histories[0].candlesticks.flatMap(c=>{
   const p=typeof c.price.close_dollars==='string'&&/^\d+(\.\d+)?$/.test(c.price.close_dollars)?Number(c.price.close_dollars):NaN,volume=Number(c.volume_fp),at=c.end_period_ts;
   if(!Number.isFinite(p)||p<0||p>1||!Number.isFinite(volume)||volume<=0||!Number.isFinite(at)||at<=start||at>end)return [];
   if(histories[0].candlesticks.filter(other=>other.end_period_ts===at).length!==1)return [];
   return [{at,p,volume}];
  }).sort((a,b)=>a.at-b.at);
  return [{ticker,name:original.yes_sub_title,original,points,result:original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null,baseline:null}];
 });
}
export const dartsTimes=(series=dartsSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export function dartsExact(ticker:string,at:number,series=dartsSeries()){
 const matches=series.filter(s=>s.ticker===ticker).flatMap(s=>s.points.filter(p=>p.at===at));return matches.length===1?matches[0]:null;
}
export function dartsSegments(points:TradePoint[]){const chunks:TradePoint[][]=[];for(const point of points){const last=chunks.at(-1);if(last&&point.at-last.at(-1)!.at<=120)last.push(point);else chunks.push([point])}return chunks;}
export function dartsSelect(at:number|null){return at===null||dartsTimes().includes(at)?at:undefined;}
export function dartsPairNote(at:number|null){
 const series=dartsSeries(),points=series.map(s=>at===null?s.points.at(-1):dartsExact(s.ticker,at));
 return points.length===2&&points.every(Boolean)&&Math.abs(points[0]!.p+points[1]!.p-1)>.005?'Separate trades; these probabilities do not add to 100%.':null;
}
