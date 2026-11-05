import {nflAdmitted,nflBaselineRow} from './nflReconciliation.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export type BinaryDialRow=CatalogEvidenceRow&{pregame_mark?:unknown;category?:unknown;source_file?:unknown};
export type BinaryDial<T>={rows:[T,T];threshold:number};
/** A pair within one exact source question; never combines different markets or invents a leg. */
export function binaryCatalogDial<T extends BinaryDialRow>(rows:T[]):BinaryDial<T>|null{
 if(rows.length!==2)return null;
 const over=rows.find(r=>r.outcome_name==='Over'),under=rows.find(r=>r.outcome_name==='Under');
 if(!over||!under||over._inverted!==false||under._inverted!==true||over.source!=='polymarket'||(over.source_file!=='nfl-14639175-game-markets.json'&&!nflAdmitted(over))||over.category!=='player_props'||!over._market_id||typeof over.threshold!=='number'||!Number.isFinite(over.threshold)||over.threshold<0)return null;
 if(under.source!==over.source||under.source_file!==over.source_file||under.category!==over.category||under.market_name!==over.market_name||String(under._market_id)!==String(over._market_id)||under.threshold!==over.threshold||over.period!=null||under.period!=null)return null;
 return {rows:[over,under],threshold:over.threshold};
}
export function binaryPregame(row:BinaryDialRow):number|null{
 const value=nflBaselineRow(row).pregame_mark;
 return typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1?(row._inverted===true?1-value:value):null;
}
export function dialPoint(chance:number){const angle=Math.PI*(1-chance);return {x:150+112*Math.cos(angle),y:138-112*Math.sin(angle)}}
