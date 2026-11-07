import {createContext} from 'react';
/** A rendered stream card supplies its identity for an explicit Explore action. */
export const StoryCardActivation=createContext<(()=>void)|null>(null);
