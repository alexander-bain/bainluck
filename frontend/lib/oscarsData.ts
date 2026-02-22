/**
 * Static data for the Oscars landing page.
 * Ceremony order, category metadata, and emoji mapping.
 */

/** Category keys in ceremony presentation order (98th Academy Awards, March 2, 2026) */
export const CEREMONY_ORDER: string[] = [
  "best_supporting_actor",
  "best_casting",
  "best_animated_short",
  "best_live_action_short",
  "best_makeup_hairstyling",
  "best_costume_design",
  "best_documentary_short",
  "best_sound",
  "best_original_score",
  "best_film_editing",
  "best_visual_effects",
  "best_animated_feature",
  "best_supporting_actress",
  "best_original_song",
  "best_international_feature",
  "best_documentary_feature",
  "best_adapted_screenplay",
  "best_production_design",
  "best_cinematography",
  "best_original_screenplay",
  "best_director",
  "best_actress",
  "best_actor",
  "best_picture",
];

/** Major (acting/directing/picture) categories get larger cards */
export const MAJOR_CATEGORIES = new Set([
  "best_picture",
  "best_director",
  "best_actor",
  "best_actress",
  "best_supporting_actor",
  "best_supporting_actress",
]);

/** Person categories — search TMDB for people, not movies */
export const PERSON_CATEGORIES = new Set([
  "best_actor",
  "best_actress",
  "best_supporting_actor",
  "best_supporting_actress",
  "best_director",
]);

/** Emoji for each category */
export const CATEGORY_EMOJI: Record<string, string> = {
  best_picture: "\uD83C\uDFAC",
  best_director: "\uD83C\uDFAC",
  best_actor: "\uD83C\uDFAD",
  best_actress: "\uD83C\uDFAD",
  best_supporting_actor: "\uD83C\uDFAD",
  best_supporting_actress: "\uD83C\uDFAD",
  best_original_screenplay: "\u270D\uFE0F",
  best_adapted_screenplay: "\u270D\uFE0F",
  best_animated_feature: "\uD83E\uDDF8",
  best_international_feature: "\uD83C\uDF0D",
  best_documentary_feature: "\uD83D\uDCF9",
  best_documentary_short: "\uD83D\uDCF9",
  best_animated_short: "\uD83E\uDDF8",
  best_live_action_short: "\uD83C\uDFAC",
  best_original_score: "\uD83C\uDFB5",
  best_original_song: "\uD83C\uDFA4",
  best_sound: "\uD83D\uDD0A",
  best_production_design: "\uD83C\uDFD7\uFE0F",
  best_cinematography: "\uD83D\uDCF7",
  best_film_editing: "\u2702\uFE0F",
  best_costume_design: "\uD83E\uDDE5",
  best_makeup_hairstyling: "\uD83D\uDC84",
  best_visual_effects: "\u2728",
  best_casting: "\uD83C\uDFAD",
};
