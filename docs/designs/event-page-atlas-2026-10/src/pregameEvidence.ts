import {contributionBaseline,contributionBaselineNote} from './hockeyContributions.ts';
import {warriorsTotalFor,warriorsTotalNote} from './warriorsTotalEvidence.ts';
import {postponedBaseline,postponedBaselineNote} from './postponedEvidence.ts';
import {marginRecord,marginNote} from './marginPregame.ts';
import {nflTotalPregameRecord,nflTotalPregame,nflTotalPregameNote} from './nflTotalPregame.ts';
import {totalPregameRecord,totalPregame,totalPregameNote} from './totalPregame.ts';
import {seriesPregame,seriesPregameRecord,seriesPregameNote} from './seriesPregame.ts';
import {tennisPropBaseline,tennisPropNote} from './tennisPropPregame.ts';
import {halfFor,halfNote} from './halfEvidence.ts';
import {placementPregame,placementNote,placementFor} from './placementEvidence.ts';
import {golfPregame,golfNote,golfFor} from './golfEvidence.ts';
import {racingPregame,racingNote,racingFor} from './racingEvidence.ts';
import {finalQuarterPregame,finalQuarterNote} from './finalQuarterEvidence.ts';
import {firstScorerPregame,firstScorerPregameNote} from './hockeyFirstPregame.ts';
import {scorerPregame,scorerPregameNote} from './hockeyScorerPregame.ts';
import {hockeyPregame,hockeyPregameNote} from './hockeyEvidence.ts';
import {completionPregame,completionPregameNote} from './nflCompletion.ts';
import {nflBaselineRow,nflPregameNote} from './nflReconciliation.ts';
import {soccerScoreBaseline,soccerScoreNote} from './soccerScorePregame.ts';
import {esportsBaseline,esportsPregameNote} from './esportsEvidence.ts';
import {combatPregame,combatPregameNote} from './combatPregame.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export type PregameRow=CatalogEvidenceRow&{pregame_mark?:unknown;opening_probability?:unknown;source_file?:unknown;_display_scope?:unknown};
/** Only the supplied normalized baseline and explicit side orientation qualify.
 * A terminal quote, opening quote or resolution never supplies a missing baseline. */
export function selectedPregame(row:PregameRow):number|null {
 const total=warriorsTotalFor(row);if(total)return total.baseline?.value??null;
 const postponed=postponedBaseline(row);if(postponed)return postponed.value;
 const margin=marginRecord(row);if(margin)return margin.value;
 if(nflTotalPregameRecord(row))return nflTotalPregame(row)?.value??null;
 if(totalPregameRecord(row))return totalPregame(row)?.value??null;
 if(seriesPregameRecord(row))return seriesPregame(row)?.value??null;
 const tennis=tennisPropBaseline(row);if(tennis)return tennis.value;
 if(halfFor(row))return halfFor(row)!.baseline?.value??null;
 if(placementFor(row))return placementPregame(row)?.value??null;
 if(golfFor(row))return golfPregame(row)?.value??null;
 const race=racingFor(row);if(race)return racingPregame(row)?.value??null;
 const quarter=finalQuarterPregame(row);if(quarter)return quarter.value;
 row=nflBaselineRow(row);
 const p=row.pregame_mark;
 if(typeof p!=='number'||!Number.isFinite(p)||p<0||p>1||typeof row._inverted!=='boolean')return contributionBaseline(row)?.value??firstScorerPregame(row)?.value??scorerPregame(row)?.value??hockeyPregame(row)?.value??completionPregame(row)?.value??combatPregame(row)?.value??esportsBaseline(row)?.value??soccerScoreBaseline(row)?.value??null;
 return row._inverted?1-p:p;
}
export function pregameLabel(row:PregameRow):string {
 if(tennisPropBaseline(row))return 'Pre-match chance';
 if(placementFor(row))return 'Pre-event top-10 chance';
 if(golfFor(row))return 'Pre-event chance';
 if(racingFor(row))return 'Pre-race chance';
 return row._display_scope==='series'?'Pre-series chance':typeof row.source_file==='string'&&row.source_file.startsWith('economics')?'Earlier chance':typeof row.source_file==='string'&&/^(mma|boxing|tennis|esports)-/.test(row.source_file)?'Pre-match chance':'Pregame chance';
}

export function pregameNote(row:PregameRow){return contributionBaselineNote(row)??warriorsTotalNote(row)??postponedBaselineNote(row)??marginNote(row)??nflTotalPregameNote(row)??totalPregameNote(row)??seriesPregameNote(row)??tennisPropNote(row)??halfNote(row)??placementNote(row)??golfNote(row)??racingNote(row)??finalQuarterNote(row)??firstScorerPregameNote(row)??scorerPregameNote(row)??hockeyPregameNote(row)??completionPregameNote(row)??nflPregameNote(row)??combatPregameNote(row)??esportsPregameNote(row)??soccerScoreNote(row)}
