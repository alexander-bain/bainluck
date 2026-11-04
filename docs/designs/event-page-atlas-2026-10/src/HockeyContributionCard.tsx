import {useMemo} from 'react';
import type {Row} from './Atlas';
import {hockeyContributionProfiles,type ContributionKind} from './hockeyContributions';
import {HockeyContributionVisual,type ContributionSelection} from './HockeyContributionVisual';
export type {ContributionSelection} from './HockeyContributionVisual';
export {contributionTitles} from './HockeyContributionVisual';
export function HockeyContributionCard({rows,eventID,kind,...rest}:{rows:Row[];eventID:unknown;kind:ContributionKind;selection:ContributionSelection;onSelection:(s:ContributionSelection)=>void;onPick:(r:Row)=>void;playersOpen:boolean;onPlayersOpen:(open:boolean)=>void;large?:boolean}){
 const profiles=useMemo(()=>hockeyContributionProfiles(rows,eventID,kind),[rows,eventID,kind]);
 return <HockeyContributionVisual profiles={profiles} kind={kind} phase="final" {...rest}/>;
}
