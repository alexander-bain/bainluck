import type {ReaderControlTarget} from './readerControlFocus';
/** Rail geometry stays in CSS pixels, including inside the scaled phone preview. */
export const readerCardWidth=(viewport:number,count:number,peekAdjacent=true)=>Math.max(1,viewport-(!peekAdjacent?26:count===1?28:48));
export const readerCardOffset=(index:number,width:number)=>Math.max(0,index)*(width+12);
export function readerIndexFromScroll({left,viewport,width,count,previous,positioned,peekAdjacent=true}:{left:number;viewport:number;width:number;count:number;previous:number;positioned:boolean;peekAdjacent?:boolean}){
 // A viewport resize can clamp/scroll the rail before ResizeObserver commits new
 // card widths. That intermediate offset is not a user choice of another card.
 if(!positioned||count<1||Math.abs(readerCardWidth(viewport,count,peekAdjacent)-width)>.5)return previous;
 return Math.min(count-1,Math.max(0,Math.round(left/(width+12))));
}

export interface ReaderSelectionMemory {openingID:string;cardID:string|null;order:string[]}
/** A source sheet temporarily unmounts the reader. A different explicit opening
 * must still win over remembered paging from an earlier reading session. */
export function readerOpeningSelection(order:string[],start:string,resumeAt:string|null|undefined,remembered?:ReaderSelectionMemory){
 if(resumeAt!=null)return {order,id:resumeAt};
 return remembered?.openingID===start?{order:remembered.order,id:remembered.cardID}:{order,id:start};
}
export interface CardFocusMemory {scrollTop:Record<string,number>;control?:ReaderControlTarget;selection?:ReaderSelectionMemory}
