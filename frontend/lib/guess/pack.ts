// SET FOUR for /guess: FRIDAY'S FIFTEEN (443: A). Same three steps as set three (430: A).
//
// GENERATED from a public read of Bain Luck's own pages taken Thu Nov 26, 8:49 PM PT. Every
// number below was looked up by market and outcome when the set was built;
// none was typed, and each is the percent the site itself prints. The
// sentences, the context lines and the roasts are written by hand. A set is a
// dated edition: its numbers stay as they were read, and the page says when.
//
// Fifteen cards in three steps of five, easiest first:
//   Easy    above or below 50% (`side`), and which of two is more likely (`versus`)
//   Medium  pick the chance from four numbers (`four`), and pick the favorite (`leader`)
//   Hard    slide to the chance (`chance`)
//
// The two `versus` cards are ours (`ours: true`): each puts two markets side
// by side. Every other card restates one market and changes only how it is
// answered. Nothing here was shown in an earlier round or set.
//
// `coinTaps` is what the Coin taps on the ten tap cards. It was drawn at random
// when the set was built and kept only because it is an ordinary coin's result:
// two or three right of the five two-way taps, one right of the five four-way.
//
// `__tests__/guess/guessPack.test.ts` holds this file to its rules.

import type { GamePack } from "./types";

export const GUESS_PACK: GamePack = {
  "id": "2026-11-27-d",
  "code": "d1",
  "asOf": "Thu Nov 26, 8:49 PM PT",
  "perRound": 5,
  "steps": [
    {
      "name": "Easy",
      "how": "Above or below 50%? Which is more likely? One tap each."
    },
    {
      "name": "Medium",
      "how": "Pick one of four."
    },
    {
      "name": "Hard",
      "how": "Slide to the number. Closest wins."
    }
  ],
  "coinTaps": [
    1,
    0,
    0,
    0,
    1,
    0,
    1,
    3,
    1,
    3,
    null,
    null,
    null,
    null,
    null
  ],
  "topics": [
    "Sports",
    "Stars",
    "Odd stuff"
  ],
  "cards": [
    {
      "kind": "side",
      "flavor": "side",
      "ours": false,
      "topic": "Stars",
      "emoji": "🧙",
      "extras": [
        "⚡",
        "📺"
      ],
      "prompt": "The new Harry Potter series scores above 75 on Rotten Tomatoes",
      "short": "Harry Potter series tops 75",
      "context": "This is the new television series, not the 2001 film. The score is the share of critics who liked it.",
      "answer": 60,
      "id": "t1"
    },
    {
      "kind": "versus",
      "flavor": "versus",
      "ours": true,
      "topic": "Sports",
      "emoji": "🏒",
      "prompt": "Which is more likely?",
      "short": "A Canadian Stanley Cup, or the Yankees in the World Series",
      "context": "Seven of the NHL’s 32 teams play in Canada, and they get four seasons to do it. Thirty baseball teams chase two World Series places.",
      "options": [
        {
          "label": "The Yankees reach the 2027 World Series",
          "short": "Yankees in the Series",
          "emoji": "⚾",
          "percent": 26
        },
        {
          "label": "A Canadian team wins the Stanley Cup by 2030",
          "short": "A Canadian Cup",
          "emoji": "🍁",
          "percent": 48
        }
      ],
      "id": "t2"
    },
    {
      "kind": "side",
      "flavor": "side",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "🛸",
      "extras": [
        "📁",
        "👽"
      ],
      "prompt": "The president releases new UFO files before the year ends",
      "short": "New UFO files this year",
      "context": "The government has put out batches of files on unexplained sightings before. The year has five weeks left.",
      "answer": 64,
      "id": "t3"
    },
    {
      "kind": "versus",
      "flavor": "versus",
      "ours": true,
      "topic": "Odd stuff",
      "emoji": "🌭",
      "prompt": "Which is more likely?",
      "short": "A Mars colony, or the end of the $1.50 hot dog",
      "context": "Costco’s hot dog and soda combo has cost $1.50 since 1985. Nobody has been to Mars.",
      "options": [
        {
          "label": "Humans colonize Mars before 2050",
          "short": "A Mars colony",
          "emoji": "🚀",
          "percent": 28
        },
        {
          "label": "Costco charges more than $1.50 for its hot dog combo before 2028",
          "short": "A dearer hot dog",
          "emoji": "🌭",
          "percent": 11
        }
      ],
      "id": "t4"
    },
    {
      "kind": "side",
      "flavor": "side",
      "ours": false,
      "topic": "Sports",
      "emoji": "🏈",
      "extras": [
        "🙌",
        "🎯"
      ],
      "prompt": "Travis Kelce catches seven or more touchdown passes this season",
      "short": "Kelce catches seven touchdowns",
      "context": "Kelce is a tight end in his fourteenth NFL season. The regular season ends in early January.",
      "answer": 42,
      "id": "t5"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Sports",
      "emoji": "🎾",
      "extras": [
        "🇦🇺",
        "🏆"
      ],
      "prompt": "Carlos Alcaraz wins the Australian Open",
      "short": "Alcaraz wins in Australia",
      "context": "The Australian Open starts in January in Melbourne. 128 men start and one wins.",
      "answer": 58,
      "options": [
        28,
        43,
        58,
        73
      ],
      "id": "t6"
    },
    {
      "kind": "leader",
      "flavor": "leader",
      "ours": false,
      "topic": "Stars",
      "emoji": "👰",
      "prompt": "Who makes Taylor Swift’s wedding dress?",
      "short": "Swift’s wedding dress",
      "independent": false,
      "context": "Swift and Travis Kelce got engaged in August 2025. Thirty designers are in the running.",
      "options": [
        {
          "label": "Vera Wang",
          "short": "Vera Wang",
          "emoji": "👗",
          "percent": 4
        },
        {
          "label": "Dior",
          "short": "Dior",
          "emoji": "✨",
          "percent": 31
        },
        {
          "label": "Vivienne Westwood",
          "short": "Westwood",
          "emoji": "🎀",
          "percent": 4
        },
        {
          "label": "Chanel",
          "short": "Chanel",
          "emoji": "🧵",
          "percent": 3
        }
      ],
      "id": "t7"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "⛷️",
      "extras": [
        "❄️",
        "🏔️"
      ],
      "prompt": "Alta ski area gets more than 100 inches of snow in December",
      "short": "100 inches of snow at Alta",
      "context": "Alta is in Utah. A hundred inches is more than eight feet of snow in one month.",
      "answer": 51,
      "options": [
        36,
        51,
        66,
        81
      ],
      "id": "t8"
    },
    {
      "kind": "leader",
      "flavor": "leader",
      "ours": false,
      "topic": "Stars",
      "emoji": "🦸",
      "prompt": "Who is most likely to die in Avengers: Doomsday?",
      "short": "Who dies in Doomsday",
      "independent": true,
      "context": "The film opens in December. More than one of these four can die in it.",
      "options": [
        {
          "label": "Spider-Man",
          "short": "Spider-Man",
          "emoji": "🕷️",
          "percent": 52
        },
        {
          "label": "Thor",
          "short": "Thor",
          "emoji": "🔨",
          "percent": 62
        },
        {
          "label": "Doctor Doom",
          "short": "Doctor Doom",
          "emoji": "🎭",
          "percent": 9
        },
        {
          "label": "Loki",
          "short": "Loki",
          "emoji": "🐍",
          "percent": 87
        }
      ],
      "id": "t9"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Sports",
      "emoji": "⚽",
      "extras": [
        "🇺🇸",
        "🏆"
      ],
      "prompt": "The USA wins the 2027 Women’s World Cup",
      "short": "USA wins the Women’s World Cup",
      "context": "The tournament is in Brazil in the summer of 2027. The USA has won four of the nine played so far.",
      "answer": 19,
      "options": [
        19,
        34,
        49,
        64
      ],
      "id": "t10"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "⛳",
      "extras": [
        "🏌️",
        "🏆"
      ],
      "prompt": "Scottie Scheffler wins a major in 2027",
      "short": "Scheffler wins a 2027 major",
      "context": "There are four majors a year: the Masters, the PGA Championship, the U.S. Open and the Open.",
      "answer": 60,
      "roastHigh": "{n} said {g}%. {n} {has} already had the trophy engraved.",
      "roastLow": "{n} said {g}%. {n} think{s} four tries is not enough for him. The world says {w}%.",
      "id": "t11"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars",
      "emoji": "🎧",
      "extras": [
        "🎤",
        "📈"
      ],
      "prompt": "Taylor Swift is the most-played artist on Spotify in the US this year",
      "short": "Swift tops Spotify in the US",
      "context": "Spotify counts every play in the United States from January on and names the winner in December.",
      "answer": 4,
      "roastHigh": "{n} said {g}%. {n} {has} one playlist and it is all Taylor. The world says {w}%.",
      "id": "t12"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "🏀",
      "extras": [
        "👌",
        "⏳"
      ],
      "prompt": "Steph Curry retires before the 2029–30 NBA season",
      "short": "Curry retires by 2029",
      "context": "Curry turns 39 in March. His contract with the Warriors runs through this season.",
      "answer": 55,
      "roastHigh": "{n} said {g}%. {n} {is} ready to retire him. Curry is not.",
      "roastLow": "{n} said {g}%. {n} think{s} he shoots threes until he is 45.",
      "id": "t13"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars",
      "emoji": "🤠",
      "extras": [
        "🧸",
        "🏆"
      ],
      "prompt": "Toy Story 5 is nominated for the Oscar for best animated film",
      "short": "Toy Story 5 gets an Oscar nomination",
      "context": "Toy Story 3 and Toy Story 4 both won this award. Nominations come out in January.",
      "answer": 85,
      "roastLow": "{n} said {g}%. {n} {has} never cried at a Toy Story film. The world says {w}%.",
      "id": "t14"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "🗳️",
      "extras": [
        "💪",
        "🇺🇸"
      ],
      "prompt": "The Rock announces a run for president before 2028",
      "short": "The Rock runs for president",
      "context": "Dwayne Johnson wrestled as The Rock before he made films. He has said more than once that he has thought about it.",
      "answer": 10,
      "roastHigh": "{n} said {g}%. {n} can smell what The Rock is cooking. The world says {w}%.",
      "id": "t15"
    }
  ]
};

export const LEGACY_PACKS_BY_CODE: Record<string, GamePack> = {
  [GUESS_PACK.code]: GUESS_PACK,
};
