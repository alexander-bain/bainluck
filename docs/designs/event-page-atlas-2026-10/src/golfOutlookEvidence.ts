import raw from './datagolfOutlook.json' with {type:'json'};
export type ForecastRow={id:number;name:string;probability:number|null;opening_probability:number|null;last_updated:string|null;is_winner:boolean|null};
export type ForecastMarket={id:number;source:string;external_id:string;name:string;outcomes:ForecastRow[]};
export const dgWire=raw;
export const dgMarkets=raw.markets as ForecastMarket[];
export const finishLabels=['Win','Top 5','Top 10','Top 20','Make cut'];
export function capturedProfile(name:string,markets:ForecastMarket[]=dgMarkets){
 const suffix=['win','top_5','top_10','top_20','make_cut'];
 return suffix.map(kind=>{const groups=markets.filter(m=>m.source==='datagolf'&&m.external_id===`${raw.eventKey}:${kind}`);if(groups.length!==1)return null;const rows=groups[0].outcomes.filter(r=>r.name===name);return rows.length===1?{market:groups[0],row:rows[0]}:null});
}
export function forecastValue(value:number|null|undefined){return typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1?value:null}
export function recordedHistory(name:string){const row=capturedProfile(name)[0]?.row;if(!row)return[];const series=raw.history.outcomes.filter(o=>o.outcome_id===row.id&&o.name===name);if(series.length!==1)return[];return series[0].history.filter(p=>forecastValue(p.probability)!==null&&Date.parse(p.timestamp)<Date.parse(raw.start));}
export const golferNames=dgMarkets[0].outcomes.map(r=>r.name);
export const leaders=dgMarkets[0].outcomes.filter(r=>forecastValue(r.probability)!==null).slice(0,6);
