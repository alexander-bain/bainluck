import {readerTime} from './readerTime.ts';
import {soccerPrevious} from './soccerReconciliation.ts';
import raw from './soccerScorePregame.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export function soccerScoreBaseline(row:CatalogEvidenceRow,w=raw):{value:number;at:string}|null{
 const previous=soccerPrevious(row);if(previous)row=previous;
 if(w.eventID!==15311089||!w.verifiedStart||!Number.isFinite(Date.parse(w.start)))return null;
 const fields=['key','source','source_file','category','_market_id','market_name','outcome_name','observed_at','contributor_outcome_ids','probability','is_winner','resolution_source','period','_inverted'] as const;
 const matches=w.rows.filter(r=>fields.every(k=>JSON.stringify((r as any)[k])===JSON.stringify((row as any)[k])));if(matches.length!==1)return null;
 const r=matches[0],t=Date.parse(r.observed_at),p=r.probability;
 if(!Number.isFinite(t)||t>=Date.parse(w.start)||!Number.isFinite(p)||p<=0||p>=1||r.is_winner!==null||r.resolution_source!==null)return null;
 return {value:p,at:r.observed_at};
}
export function soccerScoreNote(row:CatalogEvidenceRow){const b=soccerScoreBaseline(row);return b?'Earlier pre-match quote · '+readerTime(b.at):undefined}
