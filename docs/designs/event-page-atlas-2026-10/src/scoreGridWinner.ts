import type {ScoreGrid,ScoreGridRow} from './exactScoreGrid';
import {catalogPresentation,type CatalogContext} from './catalogPresentation.ts';
import {selectedPregame} from './pregameEvidence.ts';
/** Only a uniquely reported winning coordinate with an admitted baseline earns the shortcut. */
export function scoreGridWinner<T extends ScoreGridRow>(data:ScoreGrid<T>,context:CatalogContext){
 if(context.status!=='completed')return null;
 const won=[...data.cells.map(c=>c.row),data.other].filter(row=>catalogPresentation(row,context).label==='Won');
 if(won.length!==1||selectedPregame(won[0])==null)return null;
 return data.cells.find(c=>c.row===won[0])??null;
}
