import {useState,type PropsWithChildren} from 'react';
import './previewPhoneSize.css';
import {createPortal} from 'react-dom';

/** App-owned design harness. Does not change the shared mobile runtime or sport data. */
export function PreviewPhoneSize({children}:PropsWithChildren){
 const [compact,setCompact]=useState(()=>new URLSearchParams(window.location.search).get('phone')==='compact');
 return <div className={compact?'phone-size-preview compact-phone-preview':'phone-size-preview'}>
  {createPortal(<div className="phone-size-tools" role="group" aria-label="Design preview size">
   <span>Design preview</span>
   <button aria-pressed={!compact} onClick={()=>setCompact(false)}>393 × 852</button>
   <button aria-pressed={compact} onClick={()=>setCompact(true)}>375 × 667</button>
  </div>,document.body)}
  {children}
 </div>;
}
