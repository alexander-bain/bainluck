import {catalogPresentation as sourcePresentation, type CatalogPresentation} from './catalogPresentation.ts';
import {probabilityStatusLabel} from './probabilityStatusLabel.ts';
export * from './catalogPresentation.ts';
/** The evidence model stays byte-identical; only the current unavailable label changes. */
export function catalogPresentation(...args: Parameters<typeof sourcePresentation>): CatalogPresentation {
 const state = sourcePresentation(...args);
 return state.kind === 'unavailable' ? {...state, label: probabilityStatusLabel(state.label)} : state;
}
