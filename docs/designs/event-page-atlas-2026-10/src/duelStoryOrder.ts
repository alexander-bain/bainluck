import {duelPlayers,duelSeries,duelWire,type DuelPhase} from './playerDuelEvidence.ts';
export type DuelStoryID='duel'|'movement';
/** Phase-based editorial reference; no synchronous AI or new odds engine. */
export function duelStoryOrder(phase:DuelPhase,wire=duelWire):DuelStoryID[]{
 const supplied=duelSeries('duel',phase,'all',wire);
 const paired=supplied.length===2;
 const actual=duelPlayers(phase,wire).every(p=>p.actual!==null);
 // Half-payout values remain in the optional reader; they do not rank as win probabilities.
 return paired&&(phase==='before'||actual)?['duel']:[];
}
export const duelStoryScope=(phase:DuelPhase)=>`player-duel-stream:${phase}`;

export const duelReaderOrder=(ids:string[],optional:string[]=[])=>['history',...new Set([...ids,...optional].filter(id=>id==='duel'||id==='movement'))];
