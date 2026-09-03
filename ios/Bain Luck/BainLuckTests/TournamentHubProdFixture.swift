import Foundation
@testable import Bain_Luck

/// The 2026-09-03 production `GET /api/tournaments/us-open` payload, trimmed to
/// the members this screen renders.
///
/// The live response is 903 KB. Everything cut is a member the phone does not
/// draw — `grids` (404 KB of draw cells), the per-row `trend` series, `props`,
/// and 252 older results — plus the per-side telemetry the hub reports for its
/// own health (`liquidity_reasons`, `mixed_freshness`, `stale_sides`, `raw_*`).
/// What remains is REAL WIRE SHAPE, key for key: three live matches, two priced
/// upcoming matches, one UNPRICED upcoming match whose sides carry
/// `"probability": null`, three finals, one retirement, both title boards, the
/// empty `bracket` the server actually served, and the `by_espn` links.
///
/// The three live matches are chosen, not taken in order, so the fixture can
/// discriminate: one where the favourite is the FIRST side on the wire, one
/// where it is the second, and one at 99/1 that exercises the formatter's
/// boundary.
///
/// The unpriced match and the empty bracket are the reason this is a captured
/// payload rather than a hand-built one. Both are states the screen must label
/// honestly and both were invisible from a hand-written fixture — the previous
/// tournament fixture in this repo said `"probability": 62`, a whole percent no
/// server has ever sent, and that is exactly how #2888 shipped.
///
/// Frozen deliberately. Regenerating it whenever production moves would destroy
/// the only thing it is for.
enum TournamentHubProdFixture {

    /// `generated_at` as served.
    static let servedGeneratedAt = "2026-09-03T20:48:20.226684+00:00"

    /// `slate.age_hours` as served — the matches were live, the prices were four
    /// hours old, and the screen says so.
    static let servedSlateAgeHours = 3.99

    /// Decoded with the app's own decoder, so the fixture exercises the shipped
    /// `.convertFromSnakeCase` path rather than a test-local one.
    static func decode() throws -> TournamentHubResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TournamentHubResponse.self, from: Data(json.utf8))
    }

    static let json = #"""
    {
      "slug": "us-open",
      "tournament": "us-open",
      "season": "2026",
      "title": "US Open 2026",
      "subtitle": "Flushing Meadows",
      "draw_released": true,
      "main_draw_label": "Sunday 30 August",
      "generated_at": "2026-09-03T20:48:20.226684+00:00",
      "slate": {
        "matches": [
          {
            "priced": true,
            "matchup_key": "espn:182711",
            "event_id": null,
            "draw": "mens-singles",
            "draw_label": "Men's Singles",
            "round": "R64",
            "scheduled_date": "2026-09-03T18:25:00+00:00",
            "live_state": "in_progress",
            "status_detail": "4th Set",
            "start_is_tbd": false,
            "price_state": "live",
            "source_count": 1,
            "sides": [
              {
                "entity_key": "espn:athlete:4030",
                "display_name": "Dane Sweeny",
                "seed": null,
                "country": "Australia",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/aus.png"
                },
                "probability": 0.69697,
                "opening_probability": 0.06,
                "price_state": "live",
                "liquidity": "traded"
              },
              {
                "entity_key": "espn:athlete:3764",
                "display_name": "Lorenzo Musetti",
                "seed": null,
                "country": "Italy",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ita.png"
                },
                "probability": 0.30303,
                "opening_probability": 0.94,
                "price_state": "live",
                "liquidity": "traded"
              }
            ]
          },
          {
            "priced": true,
            "matchup_key": "espn:182709",
            "event_id": null,
            "draw": "mens-singles",
            "draw_label": "Men's Singles",
            "round": "R64",
            "scheduled_date": "2026-09-03T18:45:00+00:00",
            "live_state": "in_progress",
            "status_detail": "3rd Set",
            "start_is_tbd": false,
            "price_state": "live",
            "source_count": 1,
            "sides": [
              {
                "entity_key": "espn:athlete:2862",
                "display_name": "Alexei Popyrin",
                "seed": null,
                "country": "Australia",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/aus.png"
                },
                "probability": 0.42,
                "opening_probability": 0.492462,
                "price_state": "live",
                "liquidity": "traded"
              },
              {
                "entity_key": "espn:athlete:2970",
                "display_name": "Alejandro Tabilo",
                "seed": null,
                "country": "Chile",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/chi.png"
                },
                "probability": 0.58,
                "opening_probability": 0.507538,
                "price_state": "live",
                "liquidity": "traded"
              }
            ]
          },
          {
            "priced": true,
            "matchup_key": "espn:182542",
            "event_id": null,
            "draw": "womens-singles",
            "draw_label": "Women's Singles",
            "round": "R64",
            "scheduled_date": "2026-09-03T18:35:00+00:00",
            "live_state": "in_progress",
            "status_detail": "3rd Set",
            "start_is_tbd": false,
            "price_state": "live",
            "source_count": 1,
            "sides": [
              {
                "entity_key": "espn:athlete:7804",
                "display_name": "Nikola Bartunkova",
                "seed": null,
                "country": "Czechia",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/cze.png"
                },
                "probability": 0.99,
                "opening_probability": 0.683673,
                "price_state": "live",
                "liquidity": "traded"
              },
              {
                "entity_key": "espn:athlete:2346",
                "display_name": "Tatjana Maria",
                "seed": null,
                "country": "Germany",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ger.png"
                },
                "probability": 0.01,
                "opening_probability": 0.316327,
                "price_state": "live",
                "liquidity": "traded"
              }
            ]
          },
          {
            "priced": true,
            "matchup_key": "espn:182741",
            "event_id": null,
            "draw": "mens-singles",
            "draw_label": "Men's Singles",
            "round": "R64",
            "scheduled_date": "2026-09-03T20:55:00+00:00",
            "live_state": "upcoming",
            "status_detail": "Thu, September 3rd at 4:55 PM EDT",
            "start_is_tbd": false,
            "price_state": "live",
            "source_count": 1,
            "sides": [
              {
                "entity_key": "espn:athlete:2355",
                "display_name": "Benjamin Bonzi",
                "seed": null,
                "country": "France",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/fra.png"
                },
                "probability": 0.470588,
                "opening_probability": 0.420792,
                "price_state": "live",
                "liquidity": "traded"
              },
              {
                "entity_key": "espn:athlete:11226",
                "display_name": "Ignacio Buse",
                "seed": null,
                "country": "Peru",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/per.png"
                },
                "probability": 0.529412,
                "opening_probability": 0.579208,
                "price_state": "live",
                "liquidity": "traded"
              }
            ]
          },
          {
            "priced": true,
            "matchup_key": "espn:182538",
            "event_id": null,
            "draw": "womens-singles",
            "draw_label": "Women's Singles",
            "round": "R64",
            "scheduled_date": "2026-09-03T21:00:00+00:00",
            "live_state": "upcoming",
            "status_detail": "Thu, September 3rd at 5:00 PM EDT",
            "start_is_tbd": false,
            "price_state": "live",
            "source_count": 1,
            "sides": [
              {
                "entity_key": "espn:athlete:9820",
                "display_name": "Mirra Andreeva",
                "seed": null,
                "country": "Russia",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/rus.png"
                },
                "probability": 0.910891,
                "opening_probability": 0.739336,
                "price_state": "live",
                "liquidity": "traded"
              },
              {
                "entity_key": "espn:athlete:5260",
                "display_name": "Eva Lys",
                "seed": null,
                "country": "Germany",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ger.png"
                },
                "probability": 0.089109,
                "opening_probability": 0.260664,
                "price_state": "live",
                "liquidity": "traded"
              }
            ]
          },
          {
            "priced": false,
            "matchup_key": "espn:182540",
            "event_id": null,
            "draw": "womens-singles",
            "draw_label": "Women's Singles",
            "round": "R32",
            "scheduled_date": "2026-09-05T04:00:00+00:00",
            "live_state": "upcoming",
            "status_detail": null,
            "start_is_tbd": true,
            "price_state": "unpriced",
            "source_count": 0,
            "sides": [
              {
                "entity_key": "espn:athlete:2971",
                "display_name": "Anastasia Potapova",
                "seed": null,
                "country": "Austria",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/aut.png"
                },
                "probability": null,
                "opening_probability": null,
                "price_state": "unpriced",
                "liquidity": "unknown"
              },
              {
                "entity_key": "espn:athlete:3221",
                "display_name": "Amanda Anisimova",
                "seed": null,
                "country": "USA",
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
                },
                "probability": null,
                "opening_probability": null,
                "price_state": "unpriced",
                "liquidity": "unknown"
              }
            ]
          }
        ],
        "count": 6,
        "price_state": "live",
        "age_hours": 3.99,
        "newest_observed_at": "2026-09-03T16:49:00.445093+00:00"
      },
      "results": {
        "matches": [
          {
            "matchup_key": "espn:182556",
            "draw": "womens-singles",
            "draw_label": "Women's Singles",
            "round": "Round 2",
            "winner_entity_key": "alexandra-eala",
            "score": "6-1, 6-4",
            "completion": "final",
            "completed_at": "2026-09-03T18:45Z",
            "espn_competition_id": "182556",
            "players": [
              {
                "entity_key": "alexandra-eala",
                "display_name": "Alexandra Eala",
                "seed": null,
                "is_winner": true,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/6/6e/Ealas_and_Patrick_Gregorio_%28cropped_Alexandra_Eala%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail_unscaled",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/phi.png"
                },
                "prematch_probability": 0.8642,
                "prematch_source": "books"
              },
              {
                "entity_key": "oleksandra-oliynykova",
                "display_name": "Oleksandra Oliynykova",
                "seed": null,
                "is_winner": false,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Oleksandra_Oliynykova_Transylvania_Open_2026_%28cropped%29.jpg/330px-Oleksandra_Oliynykova_Transylvania_Open_2026_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ukr.png"
                },
                "prematch_probability": 0.1358,
                "prematch_source": "books"
              }
            ]
          },
          {
            "matchup_key": "espn:182755",
            "draw": "mens-singles",
            "draw_label": "Men's Singles",
            "round": "Round 2",
            "winner_entity_key": "taylor-fritz",
            "score": "6-0, 6-1, 6-1",
            "completion": "final",
            "completed_at": "2026-09-03T18:05Z",
            "espn_competition_id": "182755",
            "players": [
              {
                "entity_key": "mattia-bellucci",
                "display_name": "Mattia Bellucci",
                "seed": null,
                "is_winner": false,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Mattia_Bellucci_%282024_DC_Open%29_02_%28cropped%29.jpg/330px-Mattia_Bellucci_%282024_DC_Open%29_02_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ita.png"
                },
                "prematch_probability": 0.1401,
                "prematch_source": "books"
              },
              {
                "entity_key": "taylor-fritz",
                "display_name": "Taylor Fritz",
                "seed": null,
                "is_winner": true,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/61/Taylor_Fritz_-_Delray_Beach_Open_Final_Round_%28cropped%29.jpg/330px-Taylor_Fritz_-_Delray_Beach_Open_Final_Round_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
                },
                "prematch_probability": 0.8599,
                "prematch_source": "books"
              }
            ]
          },
          {
            "matchup_key": "espn:182579",
            "draw": "womens-singles",
            "draw_label": "Women's Singles",
            "round": "Round 2",
            "winner_entity_key": "amanda-anisimova",
            "score": "6-3, 3-6, 6-1",
            "completion": "final",
            "completed_at": "2026-09-03T16:40Z",
            "espn_competition_id": "182579",
            "players": [
              {
                "entity_key": "amanda-anisimova",
                "display_name": "Amanda Anisimova",
                "seed": null,
                "is_winner": true,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/Amanda_Anisimova_%282024_DC_Open%29_05_%28cropped4%29.jpg/330px-Amanda_Anisimova_%282024_DC_Open%29_05_%28cropped4%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
                },
                "prematch_probability": 0.8078,
                "prematch_source": "books"
              },
              {
                "entity_key": "lilli-tagger",
                "display_name": "Lilli Tagger",
                "seed": null,
                "is_winner": false,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/French_Open_Juniors_Champion_Lilli_Tagger_%28cropped%29.jpg/330px-French_Open_Juniors_Champion_Lilli_Tagger_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/aut.png"
                },
                "prematch_probability": 0.1922,
                "prematch_source": "books"
              }
            ]
          },
          {
            "matchup_key": "espn:184661",
            "draw": "mens-singles",
            "draw_label": "Men's Singles",
            "round": "Qualifying 1st Round",
            "winner_entity_key": "federico-cina",
            "score": "6-4, 3-0",
            "completion": "retired",
            "completed_at": "2026-08-25T20:55Z",
            "espn_competition_id": "184661",
            "players": [
              {
                "entity_key": "federico-cina",
                "display_name": "Federico Cina",
                "seed": null,
                "is_winner": true,
                "image": {
                  "url": null,
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ita.png"
                },
                "prematch_probability": null,
                "prematch_source": null
              },
              {
                "entity_key": "luca-nardi",
                "display_name": "Luca Nardi",
                "seed": null,
                "is_winner": false,
                "image": {
                  "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Nardi_WMQ23_%2853061881614%29.jpg/330px-Nardi_WMQ23_%2853061881614%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                  "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ita.png"
                },
                "prematch_probability": null,
                "prematch_source": null
              }
            ]
          }
        ],
        "count": 4
      },
      "boards": [
        {
          "draw": "mens-singles",
          "label": "Men's Singles",
          "price_state": "live",
          "contenders": 36,
          "age_hours": 0.97,
          "rows": [
            {
              "entity_key": "carlos-alcaraz",
              "display_name": "Carlos Alcaraz",
              "seed": null,
              "country": "Spain",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/25th_Laureus_World_Sports_Awards_-_Red_Carpet_-_Carlos_Alcaraz_-_240422_192324_%28cropped%29.jpg/330px-25th_Laureus_World_Sports_Awards_-_Red_Carpet_-_Carlos_Alcaraz_-_240422_192324_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/esp.png"
              },
              "state": "live",
              "probability": 0.425,
              "rank": 1,
              "trend_delta": 0.195875,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "alexander-zverev",
              "display_name": "Alexander Zverev",
              "seed": null,
              "country": "Germany",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Alexander_Zverev.jpg/330px-Alexander_Zverev.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/ger.png"
              },
              "state": "live",
              "probability": 0.21325,
              "rank": 2,
              "trend_delta": 0.141995,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "taylor-fritz",
              "display_name": "Taylor Fritz",
              "seed": null,
              "country": "USA",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/61/Taylor_Fritz_-_Delray_Beach_Open_Final_Round_%28cropped%29.jpg/330px-Taylor_Fritz_-_Delray_Beach_Open_Final_Round_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
              },
              "state": "live",
              "probability": 0.085,
              "rank": 3,
              "trend_delta": 0.061638,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "ben-shelton",
              "display_name": "Ben Shelton",
              "seed": null,
              "country": "USA",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Ben_Shelton%2C_media_conference%2C_Swiss_Indoors_Basel_2025_%28cropped%29.jpg/330px-Ben_Shelton%2C_media_conference%2C_Swiss_Indoors_Basel_2025_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
              },
              "state": "live",
              "probability": 0.08425,
              "rank": 4,
              "trend_delta": 0.07132,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "daniil-medvedev",
              "display_name": "Daniil Medvedev",
              "seed": null,
              "country": "Russia",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Danill_Medvedev_Miami_2019_%28cropped%29.jpg/330px-Danill_Medvedev_Miami_2019_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/rus.png"
              },
              "state": "live",
              "probability": 0.05425,
              "rank": 5,
              "trend_delta": 0.03602,
              "source_count": 2,
              "price_state": "live"
            }
          ]
        },
        {
          "draw": "womens-singles",
          "label": "Women's Singles",
          "price_state": "live",
          "contenders": 44,
          "age_hours": 0.97,
          "rows": [
            {
              "entity_key": "aryna-sabalenka",
              "display_name": "Aryna Sabalenka",
              "seed": null,
              "country": "Belarus",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Aryna_Sabalenka_Miami_Open_Final.jpg/330px-Aryna_Sabalenka_Miami_Open_Final.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/blr.png"
              },
              "state": "live",
              "probability": 0.255,
              "rank": 1,
              "trend_delta": 0.01425,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "coco-gauff",
              "display_name": "Coco Gauff",
              "seed": null,
              "country": "USA",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Coco_Gauff_Miami_Open.jpg/330px-Coco_Gauff_Miami_Open.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
              },
              "state": "live",
              "probability": 0.18575,
              "rank": 2,
              "trend_delta": 0.034387,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "iga-swiatek",
              "display_name": "Iga Swiatek",
              "seed": null,
              "country": "Poland",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Iga_Swiatek_2023_Cropped_%2B_Retouched.jpg/330px-Iga_Swiatek_2023_Cropped_%2B_Retouched.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/pol.png"
              },
              "state": "live",
              "probability": 0.15,
              "rank": 3,
              "trend_delta": -0.00125,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "jessica-pegula",
              "display_name": "Jessica Pegula",
              "seed": null,
              "country": "USA",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Jessica_Pegula_%282025_DC_Open%29_01_%28cropped%29.jpg/330px-Jessica_Pegula_%282025_DC_Open%29_01_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png"
              },
              "state": "live",
              "probability": 0.08425,
              "rank": 4,
              "trend_delta": 0.028762,
              "source_count": 2,
              "price_state": "live"
            },
            {
              "entity_key": "elena-rybakina",
              "display_name": "Elena Rybakina",
              "seed": null,
              "country": "Kazakhstan",
              "image": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Elena_Rybakina_%282025_DC_Open%29_11_%28cropped%29.jpg/330px-Elena_Rybakina_%282025_DC_Open%29_11_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail",
                "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/kaz.png"
              },
              "state": "live",
              "probability": 0.05925,
              "rank": 5,
              "trend_delta": -0.00725,
              "source_count": 2,
              "price_state": "live"
            }
          ]
        }
      ],
      "bracket": {
        "mens-singles": [],
        "womens-singles": []
      },
      "event_links": {
        "by_espn": {
          "182556": 15300877,
          "182755": 15300837,
          "182579": 15299608
        }
      },
      "broadcasts": [
        {
          "region": "US",
          "channels": [
            "ESPN",
            "ESPN2",
            "ESPN+"
          ],
          "note": "ESPN holds exclusive US rights through 2026."
        },
        {
          "region": "UK",
          "channels": [
            "Sky Sports Tennis"
          ],
          "note": null
        },
        {
          "region": "AU",
          "channels": [
            "Stan Sport"
          ],
          "note": null
        }
      ]
    }
    """#
}
