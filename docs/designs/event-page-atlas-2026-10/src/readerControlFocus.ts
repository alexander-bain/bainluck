export type ReaderControlRegion='header'|'card'|'footer';
export interface ReaderControlDescription {tag:string;type?:string;key?:string|null;label?:string|null;plot?:string|null;text?:string|null;region:ReaderControlRegion}
export interface ReaderControlTarget {cardID:string;tag:string;type:string;kind:'key'|'label'|'plot'|'text';value:string;region:ReaderControlRegion}
const clean=(value:string|null|undefined)=>(value??'').replace(/\s+/g,' ').trim();
export function readerControlTarget(cardID:string,control:ReaderControlDescription):ReaderControlTarget|null{
 if(!cardID)return null;
 for(const kind of ['key','label','plot','text'] as const){const value=clean(control[kind]);if(value)return {cardID,tag:control.tag.toLowerCase(),type:control.type??'',kind,value,region:control.region};}
 return null;
}
/** Exact, unique identity only. A missing original never borrows its sibling's action. */
export function readerControlIndex(target:ReaderControlTarget,cardID:string,controls:readonly ReaderControlDescription[]){
 if(target.cardID!==cardID)return -1;
 const matches=controls.flatMap((c,i)=>c.tag.toLowerCase()===target.tag&&(c.type??'')===target.type&&clean(c[target.kind])===target.value?[i]:[]);
 const local=matches.filter(i=>controls[i].region===target.region);
 return local.length===1?local[0]:local.length>1?-1:matches.length===1?matches[0]:-1;
}
const selector='button,a[href],input,select,textarea,summary,[tabindex="0"]';
function region(root:HTMLElement,element:Element):ReaderControlRegion|null{
 if(element.closest('.cf-info-panel'))return null;
 if(root.querySelector('.cf-header')?.contains(element))return 'header';
 if(root.querySelector('.cf-footer')?.contains(element))return 'footer';
 if(element.closest('.cf-slide:not([inert])'))return 'card';
 return null;
}
function description(root:HTMLElement,element:Element):ReaderControlDescription|null{
 const where=region(root,element);if(!where)return null;
 return {tag:element.tagName,type:element.getAttribute('type')??'',key:element.getAttribute('data-reader-focus-key'),label:element.getAttribute('aria-label'),plot:element.closest('[role="img"][aria-label]')?.getAttribute('aria-label'),text:element.textContent,region:where};
}
export function rememberReaderControl(root:HTMLElement,eventTarget:EventTarget|null,cardID:string){
 if(!(eventTarget instanceof Element))return null;
 const element=eventTarget.closest(selector);if(!element||!root.contains(element)||element.closest('[inert]'))return null;
 const control=description(root,element);return control?readerControlTarget(cardID,control):null;
}
export function restoreReaderControl(root:HTMLElement,target:ReaderControlTarget,cardID:string){
 const elements=Array.from(root.querySelectorAll(selector)).filter(e=>!e.closest('[inert]')&&!e.hasAttribute('disabled')&&e.getAttribute('aria-disabled')!=='true'&&e.getClientRects().length>0);
 const controls=elements.map(e=>description(root,e));
 const available=controls.flatMap((c,i)=>c?[{control:c,element:elements[i]}]:[]);
 const index=readerControlIndex(target,cardID,available.map(x=>x.control));
 const element=index<0?root.querySelector<HTMLButtonElement>('.cf-back'):available[index].element as HTMLElement;
 element?.focus({preventScroll:true});
 return element!==null&&document.activeElement===element;
}
