import raw from './periodEvidence.json' with {type:'json'};
import {pregameRows,pregameWire,type PregameRow,pregameTime,pregamePercent} from './pregameEvent.ts';
export type PeriodBaseline={value:number;at:string;volume:number;intervalMinutes:number};
export type PeriodRow={key:string;quarter:number;side:string;label:string;baseline:PeriodBaseline|null;recent:null;recentReason:string;ticker:string;rules:string;secondary:string;bookAt:string};
export const periodWire=raw as {eventID:number;start:string;rows:PeriodRow[]};
export const periodRows=periodWire.rows;
export function periodFor(row:PregameRow){return periodWire.eventID===pregameWire.eventID?periodRows.find(p=>p.key===row.key):undefined;}
export function periodBaseline(p:PeriodRow){const b=p.baseline;if(!b||![b.value,b.volume].every(Number.isFinite)||b.value<=0||b.value>=1||b.volume<=0||![1,60].includes(b.intervalMinutes))return null;const at=Date.parse(b.at),book=Date.parse(p.bookAt),start=Date.parse(periodWire.start);return Number.isFinite(at)&&at<=book&&at<start?b:null;}
export const periodOriginal=(p:PeriodRow)=>pregameRows.find(r=>r.key===p.key)!;
export const periodClock=(b:PeriodBaseline)=>`${b.intervalMinutes===1?'Minute':'Hour'} ending ${pregameTime(b.at)}`;
export const periodCaption=(p:PeriodRow)=>`Q${p.quarter} · ${p.side==='tie'?'Tied quarter':p.label+' outscores opponent'}`;
export const periodHistoryText=(p:PeriodRow)=>{const b=periodBaseline(p);return b?`Pregame ${pregamePercent(b.value)} · ${periodClock(b)}`:'Pregame chance unavailable';};
