import {probabilityLabel} from './probabilityLabel';
import './pregameContext.css';
export function PregameContext({value=null,label='Pregame chance',subject,note}:{value?:number|null;label?:string;subject?:string;note?:string}){
 const known=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;
 return <div className="pregame-context" data-temporal-role="pregame-baseline" aria-label={`${label}${subject?' for '+subject:''}: ${known?probabilityLabel(value):'Unavailable'}`}><div><span>{known&&<i aria-hidden="true"/>}{label}</span><strong>{known?probabilityLabel(value):'Unavailable'}</strong></div>{subject&&<small>{subject}</small>}{(known||note)&&<small>{note??'May use an opening quote · time unavailable'}</small>}</div>;
}
