import {selectedPregame,pregameLabel,pregameNote,type PregameRow} from './pregameEvidence.ts';
export type NFLOriginalRow=Omit<PregameRow,'key'>&{row_key:string};
/** Details and catalog use exactly the same selected-side baseline rule.
 * The opposing row, last price, actual and settlement never fill a missing baseline. */
export function nflOriginalBaseline(row:NFLOriginalRow){
 const adapted={...row,key:row.row_key},value=selectedPregame(adapted),raw=row.pregame_mark,qualifiedNote=pregameNote(adapted);
 // An admitted dated source takes precedence even if its value happens to
 // equal the raw field. Numerical agreement is not provenance.
 const own=!qualifiedNote&&typeof raw==='number'&&Number.isFinite(raw)&&raw>=0&&raw<=1&&typeof row._inverted==='boolean'&&value!==null&&Math.abs(value-(row._inverted?1-raw:raw))<1e-12;
 const basis=own?(row._inverted?'inverted-own-row':'direct-own-row'):'qualified-source-or-unavailable';
 const note=qualifiedNote??(value===null?'No qualified pregame baseline is available for this selected outcome. Opening and final quotes are not substitutes.':'Supplied pregame baseline; it may be an opening-quote fallback. Exact baseline time is unavailable.');
 return {value,label:pregameLabel(adapted),raw:own?raw:null,basis,note};
}
