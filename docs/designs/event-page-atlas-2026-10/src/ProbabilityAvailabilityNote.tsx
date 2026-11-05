import {probabilityAvailabilityNotice} from './probabilityAvailabilityNotice';
export function ProbabilityAvailabilityNote({phase,mode='captured',important=null,as:Tag='p',className}:{phase:string;mode?:string;important?:string|null;as?:'p'|'small';className?:string}) {
 const text=probabilityAvailabilityNotice(phase,mode,important);
 return text ? <Tag className={className} role="status">{text}</Tag> : null;
}
