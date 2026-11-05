import {cloneElement,useLayoutEffect,useRef,useState,type ReactElement} from 'react';
/** The history plot has an explicit CSS height. Pass measured CSS dimensions
 * directly to the chart, avoiding a zero-sized overflow wrapper in dialogs. */
export function NFLHistoryPlotSize({children}:{children:ReactElement<{width?:number;height?:number}>}){
 const host=useRef<HTMLDivElement>(null);
 const [size,setSize]=useState({width:0,height:0});
 useLayoutEffect(()=>{
  const element=host.current!;
  const measure=()=>{const width=element.clientWidth,height=element.clientHeight;if(width>0&&height>0)setSize(old=>old.width===width&&old.height===height?old:{width,height})};
  const observer=new ResizeObserver(measure);observer.observe(element);measure();return()=>observer.disconnect();
 },[]);
 return <div ref={host} style={{width:'100%',height:'100%'}}>{size.width>0&&size.height>0?cloneElement(children,size):null}</div>;
}
