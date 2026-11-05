import {groupCatalogRows} from './catalogGroups.ts';
import {catalogOutcomeIdentity,type CatalogAnchor} from './catalogSelection.ts';
import type {CatalogEvidenceRow} from './catalogPresentation.ts';

export const fieldFocusKeys=['cricket-field','rugby-field','chess-field','darts-field','lacrosse-field','economics','void'] as const;
export function hasFieldFocus(key:string){return (fieldFocusKeys as readonly string[]).includes(key)}
export function fieldFocusGroups<T extends CatalogEvidenceRow>(key:string,rows:T[]){
 if(!hasFieldFocus(key)||key==='void'&&!isVoidStory(rows))return [];
 // Never merge separate market originals, even when all three settle as void.
 return groupCatalogRows(rows).filter(g=>new Set(g.rows.map(catalogOutcomeIdentity)).size===g.rows.length).map(g=>({...g,id:g.key,name:key==='void'?g.rows[0].outcome_name:key==='economics'?'Earnings outlook':key==='lacrosse-field'?'Qualification field':'Contender field'}));
}
export interface FieldReadingSession {focus:string|null;activeCard:string|null;anchors:Record<string,CatalogAnchor<CatalogEvidenceRow>>}
export const emptyFieldSession:FieldReadingSession={focus:null,activeCard:null,anchors:{}};

export const voidStoryKey='void-contract-reading';

// The visual groups this captured fixture only; it never declares arbitrary
// halted or settled matches void because they share a page key.
export function isVoidStory(rows:CatalogEvidenceRow[]){
 const names:Record<string,string>={'KXLALIGAGAME-26SEP16LEVATH-LEV':'Levante','KXLALIGAGAME-26SEP16LEVATH-ATH':'Bilbao','KXLALIGAGAME-26SEP16LEVATH-TIE':'Tie'};
 return rows.length===3&&new Set(rows.map(r=>r._market_id)).size===3&&rows.every(r=>r.source==='kalshi'&&r.settlement_kind==='fair_value'&&names[String(r._market_id)]===r.outcome_name);
}
