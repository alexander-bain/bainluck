import {useLayoutEffect,useRef} from 'react';
import {denseCardPlan} from './denseCardPlan';
/** Move existing boxes only: no column wrappers, reparenting, or state remounts. */
export function useDenseCardLayout(){
 const ref=useRef<HTMLDivElement>(null);
 useLayoutEffect(()=>{
  const root=ref.current;if(!root)return;
  let frame=0,disposed=false;
  const watched=new Set<HTMLElement>();
  const originals=new Map<HTMLElement,string>();
  const rootStyle=root.getAttribute('style');
  const set=(node:HTMLElement,key:string,value:string)=>{if(node.style.getPropertyValue(key)!==value)node.style.setProperty(key,value)};
  const restore=(node:HTMLElement)=>{const value=originals.get(node);if(value!==undefined){value?node.setAttribute('style',value):node.removeAttribute('style');originals.delete(node)}};
  const schedule=()=>{if(!disposed&&!frame)frame=requestAnimationFrame(measure)};
  const resize=new ResizeObserver(schedule);
  function measure(){
   frame=0;if(disposed||!root||root.clientWidth===0)return;
   const css=getComputedStyle(root);
   const columns=css.gridTemplateColumns.split(' ').filter(Boolean).length;
   const gap=parseFloat(css.columnGap)||0;
   const children=Array.from(root.children).filter((n):n is HTMLElement=>n instanceof HTMLElement&&getComputedStyle(n).display!=='none');
   for(const child of watched)if(!children.includes(child)){resize.unobserve(child);watched.delete(child);restore(child)}
   for(const child of children)if(!watched.has(child)){watched.add(child);resize.observe(child)}
   if(columns<=1){
    for(const child of children)restore(child);
    if(rootStyle)root.setAttribute('style',rootStyle);else root.removeAttribute('style');
    return;
   }
   set(root,'position','relative');
   const available=root.clientWidth;
   const width=Math.max(0,(available-gap*(columns-1))/columns);
   const full=children.map(child=>getComputedStyle(child).gridColumnEnd==='-1');
   children.forEach((child,i)=>{
    if(!originals.has(child))originals.set(child,child.getAttribute('style')??'');
    set(child,'position','absolute');set(child,'box-sizing','border-box');
    set(child,'width',`${full[i]?available:width}px`);
    set(child,'margin','0');
   });
   const plan=denseCardPlan(available,columns,gap,children.map((child,i)=>({height:child.getBoundingClientRect().height,fullWidth:full[i]})));
   children.forEach((child,i)=>{set(child,'left',`${plan.frames[i].x}px`);set(child,'top',`${plan.frames[i].y}px`)});
   set(root,'height',`${plan.height}px`);
  }
  resize.observe(root);
  const mutations=new MutationObserver(schedule);
  // Class changes include larger text; child/text changes include disclosure and source refresh.
  mutations.observe(root,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['class','open','hidden']});
  const owner=root.closest('.event-content,.atlas-content');
  if(owner)mutations.observe(owner,{attributes:true,attributeFilter:['class']});
  schedule();
  return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();mutations.disconnect();for(const child of originals.keys())restore(child);if(rootStyle)root.setAttribute('style',rootStyle);else root.removeAttribute('style')};
 },[]);
 return ref;
}
