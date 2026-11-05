import {eventReaderTime} from './eventReaderTime.ts';
import raw from './pregameEvent.json' with {type:'json'};
export type PregameRow={key:string;category:string;family?:string;original:Record<string,any>;qualified:null|{value:number;at:string;volume:number;bid:number;ask:number;bookAt:string;ticker:string};reason:string|null;provider?:{ticker:string;rules:string;secondary:string;capturedAt:string}};
export const pregameWire=raw as unknown as {eventID:number;detail:any;history:{timestamp:string;home_probability:number}[][];rows:PregameRow[];families:{id:string;keys:string[];providerOnly:string[]}[]};
export const pregameAtlasEvent={key:'nfl-pregame',label:'NFL · Rams–Bills pregame',unit:'points',detail:pregameWire.detail,rows:[],series:[],pregame_projection:null,source:'v70 captured pregame evidence'};
export const pregameRows=pregameWire.rows;
export const pregameCategories:Record<string,string>={All:'All props',totals:'Game points',player_props:'Players',team_totals:'Team points',spreads:'Margins',period_markets:'Quarters & halves',other:'More'};
export function capturedPregame(row:PregameRow){
 const q=row.qualified,o=row.original,start=Date.parse(pregameWire.detail.commence_time);
 if(!q||!row.provider||o.source!=='kalshi'||row.provider.ticker!==q.ticker||q.bookAt!==row.provider.capturedAt||!row.family||o.is_winner!=null||o._inverted===true)return null;
 if(![q.value,q.volume,q.bid,q.ask].every(Number.isFinite)||!(q.value>0&&q.value<1&&q.volume>0&&q.bid>0&&q.bid<=q.ask&&q.ask<1&&q.ask-q.bid<=.050000001))return null;
 const at=Date.parse(q.at),book=Date.parse(q.bookAt);if(!Number.isFinite(at)||!Number.isFinite(book)||book>=start||at>book||book-at>900000)return null;
 return q;
}
export const familyRows=(family:string)=>pregameRows.filter(r=>r.family===family);
export function originalQuote(row:PregameRow){const o=row.original;if(typeof o.probability==='number')return o.probability;if(typeof o.over_probability==='number')return o._inverted===true||/^(Under\b|No$)/i.test(o.outcome_name)?1-o.over_probability:o.over_probability;return null;}
export function groupPregame(rows=pregameRows){const map=new Map<string,PregameRow[]>();for(const r of rows){const key=`${r.original.source}:${r.original._market_id}`;map.set(key,[...(map.get(key)||[]),r]);}return [...map].map(([key,rows])=>({key,rows}));}
export function filterPregame(category:string,query:string,rows=pregameRows){const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);return rows.filter(r=>(category==='All'||r.category===category)&&terms.every(t=>`${r.original.market_name} ${r.original.outcome_name} ${r.original.source}`.toLowerCase().includes(t)));}
export function retainedSelection(rows:PregameRow[],key?:string){return rows.find(r=>r.key===key)||rows.find(r=>capturedPregame(r))||rows[0];}
export const pregameTime=eventReaderTime.full;
export const pregamePercent=(value:number|null|undefined)=>value==null?'Unavailable':`${+(value*100).toFixed(1)}%`;

export function revealPregame(row:PregameRow,rows=pregameRows){
 if(!rows.some(r=>r.key===row.key))return null;
 const query=`${row.original.market_name} ${row.original.outcome_name}`;
 const keys=new Set(filterPregame('All',query,rows).map(r=>r.key));
 const groups=groupPregame(rows).filter(g=>g.rows.some(r=>keys.has(r.key)));
 const index=groups.findIndex(g=>g.rows.some(r=>r.key===row.key));
 return index<0?null:{category:'All',query,limit:Math.max(12,index+1)};
}
