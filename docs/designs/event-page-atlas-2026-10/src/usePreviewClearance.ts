import {useLayoutEffect,useState,useCallback} from 'react';
/** Reference toolbar only; rebind when its portal mounts a new DOM node. */
export function usePreviewClearance(){
 const [node,setNode]=useState<HTMLDivElement|null>(null);
 const ref=useCallback((element:HTMLDivElement|null)=>setNode(element),[]);
 const [clearance,setClearance]=useState(76);
 useLayoutEffect(()=>{
  if(!node)return;
  const measure=()=>setClearance(Math.ceil(node.getBoundingClientRect().bottom)+12);
  const observer=new ResizeObserver(measure);observer.observe(node);measure();
  window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure)};
 },[node]);
 return {ref,clearance};
}
