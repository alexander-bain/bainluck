import type {ReactNode} from 'react';
import './golfSourceFacts.css';

/** Source facts scroll independently so returning never requires scrolling back. */
export function GolfSourceFacts({children,onClose}:{children:ReactNode;onClose:()=>void}) {
 return <div className="golf-source-facts">
  <div className="golf-source-actions"><button onClick={onClose}>Done</button></div>
  <div className="golf-source-scroll" role="region" aria-label="Source facts" tabIndex={0}>{children}</div>
 </div>;
}
