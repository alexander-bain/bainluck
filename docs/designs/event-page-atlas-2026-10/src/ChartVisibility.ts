import {createContext,createElement,useContext,type ComponentProps,type ReactNode} from 'react';
import {ResponsiveContainer as RechartsResponsiveContainer} from 'recharts';

const ChartVisibilityContext=createContext(true);
/** Keep selection-owning cards mounted; only pause layout-dependent plot children. */
export function ChartVisibility({visible,children}:{visible:boolean;children:ReactNode}){
 const ancestorVisible=useContext(ChartVisibilityContext);
 return createElement(ChartVisibilityContext.Provider,{value:ancestorVisible&&visible},children);
}
export function ResponsiveContainer(props:ComponentProps<typeof RechartsResponsiveContainer>){
 const visible=useContext(ChartVisibilityContext);
 return visible?createElement(RechartsResponsiveContainer,props):null;
}
