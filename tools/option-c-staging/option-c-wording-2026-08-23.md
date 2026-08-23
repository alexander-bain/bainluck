# Option C, as ruled — the wording, generated from the live payload

UX-P122 item C. **Staging only.** `frontend/lib/calibrationPopulation.ts` is in
the unmerged stack's barred set and UX-P122's write gate was CLOSED, so this is
the tested content for `program/ux-108`, not an applied change.

- payload `generated_at`: `2026-08-23T21:32:06.714996+00:00`
- `by_category` rows published: **34**
- rendered rows: **15** · of which POOL: **6**
- normalized keys that pool: **7** — 1 of them never reach the screen (mma)

**Amendment 6 is exactly this pair of numbers.** The shipped page passes
`7` (every normalized key) over `15` (rendered rows) — a fraction whose
halves come from two different populations. The numerator must be **6**.

## The section sentence

```
Every figure in this table is measured over traded outcomes only, so it will not match the whole-population number the API publishes in `by_category` for the same name. 6 of 15 rows also pool several payload categories under one label — expand a row to see every one of them.
```

## The rows

Each row shows the sentence as ruled (published members named inline), the
counts-only alternative, and the FULL member list the expander must carry.
Nothing below is capped.

### Baseball (`baseball`)

Renders **1.4pp** over n=153,862 (axis D, unchanged). Folds **4** payload categories: **4** published, **0** not.

```
This row pools 4 published categories (baseball, baseball_mlb, baseball_mlb_preseason and baseball_ncaa), and is measured over traded outcomes only. The API publishes 2.00pp for “baseball” over 208,684 outcomes — that figure covers the “baseball” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 4 published categories, and is measured over traded outcomes only. The API publishes 2.00pp for “baseball” over 208,684 outcomes — that figure covers the “baseball” category alone, over the whole population.
```

<details><summary>full member list (4)</summary>

- published in `by_category` (4): baseball, baseball_mlb, baseball_mlb_preseason, baseball_ncaa
- not published (0): _none_

</details>

### Basketball (`basketball`)

Renders **1.0pp** over n=163,592 (axis D, unchanged). Folds **8** payload categories: **7** published, **1** not.

```
This row pools 7 published categories (basketball, basketball_euroleague, basketball_nba, basketball_nba_summer_league, basketball_ncaab, basketball_wnba and basketball_wncaab) and 1 unpublished, and is measured over traded outcomes only. The API publishes 1.35pp for “basketball” over 123,814 outcomes — that figure covers the “basketball” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 7 published categories and 1 unpublished, and is measured over traded outcomes only. The API publishes 1.35pp for “basketball” over 123,814 outcomes — that figure covers the “basketball” category alone, over the whole population.
```

<details><summary>full member list (8)</summary>

- published in `by_category` (7): basketball, basketball_euroleague, basketball_nba, basketball_nba_summer_league, basketball_ncaab, basketball_wnba, basketball_wncaab
- not published (1): basketball_nbl

</details>

### Soccer (`soccer`)

Renders **4.2pp** over n=68,350 (axis D, unchanged). Folds **55** payload categories: **1** published, **54** not.

```
This row pools 1 published category (soccer) and 54 unpublished, and is measured over traded outcomes only. The API publishes 2.86pp for “soccer” over 122,604 outcomes — that figure covers the “soccer” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 1 published category and 54 unpublished, and is measured over traded outcomes only. The API publishes 2.86pp for “soccer” over 122,604 outcomes — that figure covers the “soccer” category alone, over the whole population.
```

<details><summary>full member list (55)</summary>

- published in `by_category` (1): soccer
- not published (54): soccer_argentina_primera_division, soccer_australia_aleague, soccer_austria_bundesliga, soccer_belgium_first_div, soccer_brazil_campeonato, soccer_brazil_serie_b, soccer_chile_campeonato, soccer_china_superleague, soccer_conmebol_copa_libertadores, soccer_conmebol_copa_sudamericana, soccer_denmark_superliga, soccer_efl_champ, soccer_england_efl_cup, soccer_england_league1, soccer_england_league2, soccer_epl, soccer_fa_cup, soccer_fifa_world_cup, soccer_fifa_world_cup_qualifiers_europe, soccer_finland_veikkausliiga, soccer_france_ligue_one, soccer_france_ligue_two, soccer_germany_bundesliga, soccer_germany_bundesliga2, soccer_germany_dfb_pokal, soccer_germany_liga3, soccer_greece_super_league, soccer_italy_coppa_italia, soccer_italy_serie_a, soccer_italy_serie_b, soccer_japan_j_league, soccer_korea_kleague1, soccer_league_of_ireland, soccer_mexico_ligamx, soccer_netherlands_eredivisie, soccer_norway_eliteserien, soccer_poland_ekstraklasa, soccer_portugal_primeira_liga, soccer_russia_premier_league, soccer_spain_copa_del_rey, soccer_spain_la_liga, soccer_spain_segunda_division, soccer_spl, soccer_sweden_allsvenskan, soccer_sweden_superettan, soccer_switzerland_superleague, soccer_turkey_super_league, soccer_uefa_champs_league, soccer_uefa_champs_league_qualification, soccer_uefa_champs_league_women, soccer_uefa_europa_conference_league, soccer_uefa_europa_league, soccer_uefa_nations_league, soccer_usa_mls

</details>

### Tennis (`tennis`)

Renders **1.7pp** over n=17,920 (axis D, unchanged). Folds **7** payload categories: **4** published, **3** not.

```
This row pools 4 published categories (tennis, tennis_atp_canadian_open, tennis_atp_cincinnati_open and tennis_wta_canadian_open) and 3 unpublished, and is measured over traded outcomes only. The API publishes 1.97pp for “tennis” over 47,084 outcomes — that figure covers the “tennis” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 4 published categories and 3 unpublished, and is measured over traded outcomes only. The API publishes 1.97pp for “tennis” over 47,084 outcomes — that figure covers the “tennis” category alone, over the whole population.
```

<details><summary>full member list (7)</summary>

- published in `by_category` (4): tennis, tennis_atp_canadian_open, tennis_atp_cincinnati_open, tennis_wta_canadian_open
- not published (3): tennis_atp_washington_open, tennis_wta_cincinnati_open, tennis_wta_washington_open

</details>

### Hockey (`hockey`)

Renders **2.3pp** over n=27,093 (axis D, unchanged). Folds **4** payload categories: **2** published, **2** not.

```
This row pools 2 published categories (hockey and icehockey_nhl) and 2 unpublished, and is measured over traded outcomes only. The API publishes 0.95pp for “hockey” over 35,426 outcomes — that figure covers the “hockey” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 2 published categories and 2 unpublished, and is measured over traded outcomes only. The API publishes 0.95pp for “hockey” over 35,426 outcomes — that figure covers the “hockey” category alone, over the whole population.
```

<details><summary>full member list (4)</summary>

- published in `by_category` (2): hockey, icehockey_nhl
- not published (2): icehockey_sweden_allsvenskan, icehockey_sweden_hockey_league

</details>

### Football (`football`)

Renders **3.1pp** over n=5,806 (axis D, unchanged). Folds **5** payload categories: **1** published, **4** not.

```
This row pools 1 published category (football) and 4 unpublished, and is measured over traded outcomes only. The API publishes 2.28pp for “football” over 8,569 outcomes — that figure covers the “football” category alone, over the whole population.
```

counts-only alternative:

```
This row pools 1 published category and 4 unpublished, and is measured over traded outcomes only. The API publishes 2.28pp for “football” over 8,569 outcomes — that figure covers the “football” category alone, over the whole population.
```

<details><summary>full member list (5)</summary>

- published in `by_category` (1): football
- not published (4): americanfootball_cfl, americanfootball_nfl, americanfootball_nfl_preseason, americanfootball_ufl

</details>

## What an implementation must NOT copy from this file

Every number above is a reading of one payload. The census moved twice in two
days with no code change — tennis 3 → 4 published members overnight, and the
prior one-pager regenerated 108 diff lines seven hours after it was committed.
Copy the FUNCTIONS; derive the counts.

