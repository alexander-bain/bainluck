import {readerTime} from './readerTime.ts';
import retained from './combatPregameEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type CombatPregameWire=typeof retained;
export function combatHistoryBinding(row:CatalogEvidenceRow,wire:CombatPregameWire=retained){
 if(wire.eventID!==15318681||wire.verifiedStart!==true||!Number.isFinite(Date.parse(wire.start))||row.source!=='polymarket'||typeof row.key!=='string'||!row.key.startsWith('mma-15318681-game-markets.json:')||row.period!=null||row.contributor_outcome_ids?.length!==1)return null;
 const matches=wire.rows.filter(b=>b.key===row.key&&String(b.marketID)===String(row._market_id)&&b.source===row.source&&b.question===row.market_name&&b.side===row.outcome_name&&String(b.outcomeID)===String(row.contributor_outcome_ids![0]));
 return matches.length===1?matches[0]:null;
}
export function combatPregame(row:CatalogEvidenceRow,wire:CombatPregameWire=retained){
 const binding=combatHistoryBinding(row,wire);if(!binding)return null;
 const start=Date.parse(wire.start),before=binding.observations.filter(p=>Number.isFinite(Date.parse(p.timestamp))&&Date.parse(p.timestamp)<start);
 // 0/1 in this resolved-history feed lack a price-versus-settlement discriminator.
 // Refuse them as baseline evidence; do not substitute an older point past an ambiguous latest record.
 const latest=before.reduce((last,p)=>!last||Date.parse(p.timestamp)>Date.parse(last.timestamp)?p:last,null as typeof before[number]|null);
 if(!latest||typeof latest.probability!=='number'||!Number.isFinite(latest.probability)||latest.probability<=0||latest.probability>=1||latest.bookmaker!=='consensus'||before.filter(p=>Date.parse(p.timestamp)===Date.parse(latest.timestamp)).length!==1)return null;
 return {value:latest.probability,at:latest.timestamp,outcomeID:binding.outcomeID,historyFile:binding.historyFile};
}
export function combatResultConflict(row:CatalogEvidenceRow,wire:CombatPregameWire=retained){const b=combatHistoryBinding(row,wire);return !!b&&b.resolutionSource==='api_settlement'&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'&&typeof b.detailResult==='boolean'&&b.detailResult!==row.is_winner;}
export function combatCheckedResult(row:CatalogEvidenceRow,grade:string){return combatResultConflict(row)?'Result unconfirmed':grade;}
export const combatQuoteTime=(at:string)=>readerTime(at);
export function combatPregameNote(row:CatalogEvidenceRow){const p=combatPregame(row);return p?'Last recorded before start · '+combatQuoteTime(p.at):undefined;}
