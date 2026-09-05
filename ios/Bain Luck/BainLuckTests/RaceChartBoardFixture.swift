import Foundation
@testable import Bain_Luck

/// The men's title board off production on 2026-09-05, WITH its per-row `trend`
/// arrays — the payload the RACE chart actually draws from.
///
/// `TournamentHubProdFixture` exists and is frozen and is not this: it cut the
/// per-row `trend` to stay a readable size, so every render taken from it draws
/// the "one reading" note where the chart should be. A chart primitive with no
/// fixture carrying a series is a chart primitive whose render evidence is of an
/// empty state.
///
/// Trimmed to the members this screen renders — six standing contenders, one
/// board, the published main-draw start that dates the `Draw` window — and
/// otherwise key for key as served.
///
/// Three facts about it are load-bearing, and all three are why it is a CAPTURE
/// rather than a hand-built payload:
///
///   - **The leader is 0.445.** `× 1.15 = 0.512`, which is #3032's case: on the
///     old 10/25/50/100 ladder that landed on 1.0 and drew the whole race in the
///     bottom half of the plot.
///   - **The rows do NOT share one window.** Five start `2026-08-06` and Learner
///     Tien starts `2026-08-26`, because a contender's history begins when a
///     market first put a number on them. That is #3033's mixed case, and it is
///     what the six-row phone board really shows.
///   - **The series are sparse.** 16 readings across 30 days with a gap from
///     10 to 26 August. Gaps stay gaps.
enum RaceChartBoardFixture {

    static func decode() throws -> TournamentHubResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TournamentHubResponse.self, from: Data(json.utf8))
    }

    static func presentation() throws -> TournamentHubPresentation {
        TournamentHubPresentation(response: try decode())
    }

    static let json = #"""
    {
      "slug": "us-open",
      "title": "US Open 2026",
      "subtitle": "Flushing Meadows",
      "main_draw_starts_at": "2026-08-30T11:00:00-04:00",
      "slate": {
        "matches": [],
        "count": 0
      },
      "results": {
        "matches": [],
        "count": 0
      },
      "boards": [
        {
          "draw": "mens-singles",
          "label": "Men's Singles",
          "price_state": "live",
          "contenders": 36,
          "rows": [
            {
              "entity_key": "carlos-alcaraz",
              "display_name": "Carlos Alcaraz",
              "state": "live",
              "probability": 0.445,
              "rank": 1,
              "trend_delta": 0.334374,
              "source_count": 2,
              "trend": [
                {
                  "date": "2026-08-06",
                  "probability": 0.122
                },
                {
                  "date": "2026-08-07",
                  "probability": 0.130833
                },
                {
                  "date": "2026-08-08",
                  "probability": 0.135
                },
                {
                  "date": "2026-08-09",
                  "probability": 0.145625
                },
                {
                  "date": "2026-08-10",
                  "probability": 0.138824
                },
                {
                  "date": "2026-08-26",
                  "probability": 0.286875
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.265
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.274375
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.270357
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.26
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.296042
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.345938
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.366051
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.410417
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.442796
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.456374
                }
              ]
            },
            {
              "entity_key": "alexander-zverev",
              "display_name": "Alexander Zverev",
              "state": "live",
              "probability": 0.20025,
              "rank": 2,
              "trend_delta": 0.097958,
              "source_count": 2,
              "trend": [
                {
                  "date": "2026-08-06",
                  "probability": 0.10685
                },
                {
                  "date": "2026-08-07",
                  "probability": 0.106854
                },
                {
                  "date": "2026-08-08",
                  "probability": 0.100208
                },
                {
                  "date": "2026-08-09",
                  "probability": 0.105938
                },
                {
                  "date": "2026-08-10",
                  "probability": 0.133147
                },
                {
                  "date": "2026-08-26",
                  "probability": 0.203188
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.214687
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.229896
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.22619
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.222576
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.230354
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.230865
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.208701
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.217156
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.205953
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.204808
                }
              ]
            },
            {
              "entity_key": "taylor-fritz",
              "display_name": "Taylor Fritz",
              "state": "live",
              "probability": 0.10275,
              "rank": 3,
              "trend_delta": 0.074885,
              "source_count": 2,
              "trend": [
                {
                  "date": "2026-08-06",
                  "probability": 0.027
                },
                {
                  "date": "2026-08-07",
                  "probability": 0.027667
                },
                {
                  "date": "2026-08-08",
                  "probability": 0.0295
                },
                {
                  "date": "2026-08-09",
                  "probability": 0.030021
                },
                {
                  "date": "2026-08-10",
                  "probability": 0.034971
                },
                {
                  "date": "2026-08-26",
                  "probability": 0.051187
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.057375
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.066438
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.069036
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.071804
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.072583
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.076646
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.085189
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.084625
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.107344
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.101885
                }
              ]
            },
            {
              "entity_key": "ben-shelton",
              "display_name": "Ben Shelton",
              "state": "live",
              "probability": 0.08825,
              "rank": 4,
              "trend_delta": 0.066474,
              "source_count": 2,
              "trend": [
                {
                  "date": "2026-08-06",
                  "probability": 0.0156
                },
                {
                  "date": "2026-08-07",
                  "probability": 0.018729
                },
                {
                  "date": "2026-08-08",
                  "probability": 0.021625
                },
                {
                  "date": "2026-08-09",
                  "probability": 0.021083
                },
                {
                  "date": "2026-08-10",
                  "probability": 0.020618
                },
                {
                  "date": "2026-08-26",
                  "probability": 0.078
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.0715
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.05925
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.056071
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.061543
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.077198
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.08499
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.082768
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.086333
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.083228
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.082074
                }
              ]
            },
            {
              "entity_key": "daniil-medvedev",
              "display_name": "Daniil Medvedev",
              "state": "live",
              "probability": 0.0605,
              "rank": 5,
              "trend_delta": 0.03925,
              "source_count": 2,
              "trend": [
                {
                  "date": "2026-08-06",
                  "probability": 0.0175
                },
                {
                  "date": "2026-08-07",
                  "probability": 0.020125
                },
                {
                  "date": "2026-08-08",
                  "probability": 0.017667
                },
                {
                  "date": "2026-08-09",
                  "probability": 0.020188
                },
                {
                  "date": "2026-08-10",
                  "probability": 0.020941
                },
                {
                  "date": "2026-08-26",
                  "probability": 0.026063
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.02475
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.025
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.024536
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.027043
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.041438
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.04201
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.045894
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.052292
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.053641
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.05675
                }
              ]
            },
            {
              "entity_key": "learner-tien",
              "display_name": "Learner Tien",
              "state": "live",
              "probability": 0.025,
              "rank": 6,
              "trend_delta": 0.01,
              "source_count": 1,
              "trend": [
                {
                  "date": "2026-08-26",
                  "probability": 0.015
                },
                {
                  "date": "2026-08-27",
                  "probability": 0.015
                },
                {
                  "date": "2026-08-28",
                  "probability": 0.015
                },
                {
                  "date": "2026-08-29",
                  "probability": 0.015
                },
                {
                  "date": "2026-08-30",
                  "probability": 0.015
                },
                {
                  "date": "2026-08-31",
                  "probability": 0.015
                },
                {
                  "date": "2026-09-01",
                  "probability": 0.015
                },
                {
                  "date": "2026-09-02",
                  "probability": 0.015
                },
                {
                  "date": "2026-09-03",
                  "probability": 0.015
                },
                {
                  "date": "2026-09-04",
                  "probability": 0.023182
                },
                {
                  "date": "2026-09-05",
                  "probability": 0.025
                }
              ]
            }
          ]
        }
      ],
      "bracket": {},
      "event_links": {
        "by_espn": {}
      },
      "broadcasts": []
    }
    """#
}
