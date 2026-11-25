// THE FIRST SET for /guess (425: C, 426: A).
//
// GENERATED from a public read of Bain Luck's own pages taken Wed Nov 25, 12:02 PM PT. Every
// number below was looked up by market and outcome when the set was built;
// none was typed. Every answer is derived from those numbers by rule: the
// larger of two, the nearest to a stated reference, the earliest year at 50%
// or more, the count at 50% or more. The sentences, the context lines and the
// roasts are written by hand. A set is a dated edition: its numbers stay as
// they were read, and the page says when that was.
//
// `ours: true` marks a card of a kind that compares or counts ACROSS markets,
// which no single market page can show. `ours: false` is one market, restated.
// The marks people give at the end of a round are kept with this flag, so the
// first thing the game teaches us is which kind people like better.
//
// `__tests__/guess/guessPack.test.ts` holds this file to its rules.

import type { GamePack } from "./types";

export const GUESS_PACK: GamePack = {
  "id": "2026-11-25-a",
  "code": "a1",
  "asOf": "Wed Nov 25, 12:02 PM PT",
  "perRound": 7,
  "topics": [
    "Sports",
    "Screen and games",
    "Space and science",
    "Odd ones"
  ],
  "cards": [
    {
      "id": "g1",
      "kind": "chance",
      "ours": false,
      "topic": "Odd ones",
      "emoji": "🛒",
      "extras": [
        "🎮",
        "📦"
      ],
      "prompt": "GameStop buys eBay in 2026",
      "short": "GameStop buys eBay",
      "context": "GameStop is the video-game shop chain. eBay is the online marketplace.",
      "answer": 3,
      "roastHigh": "{n} said {g}%. A video-game shop buying eBay. {n} {has} seen the future, and it is confusing."
    },
    {
      "id": "g2",
      "kind": "pick",
      "flavor": "pair",
      "ours": true,
      "topic": "Screen and games",
      "emoji": "⚖️",
      "prompt": "Which is more likely?",
      "short": "Iron Man or Duke",
      "context": "Robert Downey Jr. last played Iron Man in 2019. He is back in a Marvel film this December as a different character. The Final Four is the last weekend of college basketball’s tournament.",
      "options": [
        {
          "label": "Duke reaches the Final Four",
          "short": "Duke",
          "emoji": "🏀",
          "percent": 37
        },
        {
          "label": "Robert Downey Jr. is back as Iron Man this year",
          "short": "Iron Man",
          "emoji": "🦾",
          "percent": 45
        }
      ],
      "roastWrong": "{n} backed a college basketball team over Hollywood bringing a favorite back. The world has Iron Man at {w}% and Duke at {pp}%.",
      "answer": 1,
      "partial": {}
    },
    {
      "id": "g3",
      "kind": "pick",
      "flavor": "match",
      "ours": true,
      "topic": "Sports",
      "emoji": "🎲",
      "target": 17,
      "prompt": "Which of these is about as likely as rolling a six?",
      "sub": "One roll of one die: 1 in 6, about 17%.",
      "short": "As likely as rolling a six",
      "context": "The Hurricanes are the favorite for the Stanley Cup. In hockey, even the favorite is about a roll of the dice.",
      "options": [
        {
          "label": "Christopher Nolan wins the Oscar for Best Director",
          "short": "the Nolan Oscar",
          "emoji": "🎬",
          "percent": 58
        },
        {
          "label": "The Carolina Hurricanes win the Stanley Cup",
          "short": "the Hurricanes",
          "emoji": "🏒",
          "percent": 17
        },
        {
          "label": "Joe Rogan joins 60 Minutes as a correspondent this year",
          "short": "Joe Rogan on 60 Minutes",
          "emoji": "🎙️",
          "percent": 3
        },
        {
          "label": "Brock Purdy is the NFL’s Most Valuable Player",
          "short": "Purdy for MVP",
          "emoji": "🏈",
          "percent": 40
        }
      ],
      "roastWrong": "{n} picked {pick}, which the world has at {pp}%. A six comes up about 17% of the time.",
      "answer": 1,
      "partial": {
        "2": 8
      }
    },
    {
      "id": "g4",
      "kind": "chance",
      "ours": false,
      "topic": "Screen and games",
      "emoji": "🎮",
      "extras": [
        "🏆",
        "🚗"
      ],
      "prompt": "Grand Theft Auto VI wins Game of the Year",
      "short": "GTA VI wins Game of the Year",
      "context": "The Game Awards name one Game of the Year each December.",
      "answer": 94,
      "roastLow": "{n} said {g}%. {n} {has} not been near a teenager lately. The world says {w}%."
    },
    {
      "id": "g5",
      "kind": "ladder",
      "ours": true,
      "topic": "Space and science",
      "emoji": "⚛️",
      "prompt": "When is nuclear fusion achieved?",
      "sub": "Pick the earliest year the world calls more likely than not.",
      "short": "When fusion arrives",
      "context": "Fusion is what powers the Sun. No power plant runs on it yet.",
      "options": [
        {
          "label": "By 2030",
          "short": "2030",
          "emoji": "",
          "percent": 37
        },
        {
          "label": "By 2035",
          "short": "2035",
          "emoji": "",
          "percent": 64
        },
        {
          "label": "By 2040",
          "short": "2040",
          "emoji": "",
          "percent": 78
        },
        {
          "label": "Not by 2040",
          "short": "not by 2040",
          "emoji": "",
          "percent": null
        }
      ],
      "roastWrong": "{n} said {pick}. The world gets past even by 2035. Fusion has been thirty years away for sixty years, so that is forgivable.",
      "answer": 1,
      "partial": {
        "0": 8,
        "2": 8
      }
    },
    {
      "id": "g6",
      "kind": "count",
      "ours": true,
      "topic": "Sports",
      "emoji": "🏒",
      "prompt": "How many of these six score 100 points this season?",
      "sub": "Count the ones the world has above 50%.",
      "short": "NHL stars reaching 100 points",
      "context": "A 100-point season is rare. Only a few NHL players get there each year.",
      "items": [
        {
          "label": "Connor McDavid",
          "short": "McDavid",
          "emoji": "🏒",
          "percent": 94
        },
        {
          "label": "Nathan MacKinnon",
          "short": "MacKinnon",
          "emoji": "🏒",
          "percent": 22
        },
        {
          "label": "Leon Draisaitl",
          "short": "Draisaitl",
          "emoji": "🏒",
          "percent": 95
        },
        {
          "label": "Cale Makar",
          "short": "Makar",
          "emoji": "🏒",
          "percent": 14
        },
        {
          "label": "Macklin Celebrini",
          "short": "Celebrini",
          "emoji": "🏒",
          "percent": 62
        },
        {
          "label": "Jack Eichel",
          "short": "Eichel",
          "emoji": "🏒",
          "percent": 45
        }
      ],
      "step": 7,
      "roastHigh": "{n} said {g}. The world counts {w}. {n} {has} a generous heart.",
      "roastLow": "{n} said {g}. The world counts {w}. {n} trust{s} nobody.",
      "answer": 3,
      "max": 6
    },
    {
      "id": "g7",
      "kind": "order",
      "ours": true,
      "topic": "Odd ones",
      "emoji": "🥇",
      "prompt": "Three favorites. Put them in order, the surest first.",
      "short": "Three favorites in order",
      "context": "An Oscar, the NBA scoring title, and Billboard’s artist of the year.",
      "items": [
        {
          "label": "Luka Dončić leads the NBA in scoring",
          "short": "the scoring title",
          "emoji": "🏀",
          "percent": 77
        },
        {
          "label": "Morgan Wallen is Billboard’s top artist of 2026",
          "short": "the singer",
          "emoji": "🎤",
          "percent": 66
        },
        {
          "label": "Julianne Moore wins the Oscar for Best Actress",
          "short": "the Oscar",
          "emoji": "🏆",
          "percent": 86
        }
      ],
      "roastWrong": "{n} had them out of order. The world is surest about the Oscar, then the scoring title, then the singer."
    },
    {
      "id": "g8",
      "kind": "chance",
      "ours": false,
      "topic": "Space and science",
      "emoji": "☄️",
      "extras": [
        "🔭",
        "🪐"
      ],
      "prompt": "A new interstellar visitor is confirmed before 2027",
      "short": "A new interstellar visitor",
      "context": "An interstellar visitor is an object passing through from outside our solar system. Only three have ever been confirmed.",
      "answer": 7,
      "roastHigh": "{n} said {g}%. There are five weeks left in the year, {n}. Space is big and slow."
    },
    {
      "id": "g9",
      "kind": "pick",
      "flavor": "pair",
      "ours": true,
      "topic": "Space and science",
      "emoji": "⚖️",
      "prompt": "Which is more likely?",
      "short": "The novel or the rocket",
      "context": "The Winds of Winter is the sixth Game of Thrones novel. Readers have been waiting since 2011. Nothing SpaceX has built has landed on Mars.",
      "options": [
        {
          "label": "The Winds of Winter gets a release date this year",
          "short": "the novel",
          "emoji": "📚",
          "percent": 7
        },
        {
          "label": "SpaceX lands something on Mars before 2030",
          "short": "Mars",
          "emoji": "🚀",
          "percent": 26
        }
      ],
      "roastWrong": "{n} had the novel arriving before the rocket. The world has Mars at {w}% and the novel at {pp}%.",
      "answer": 1,
      "partial": {}
    },
    {
      "id": "g10",
      "kind": "pick",
      "flavor": "field",
      "ours": false,
      "topic": "Odd ones",
      "emoji": "📖",
      "prompt": "Which is the favorite for Merriam-Webster’s Word of the Year?",
      "short": "Word of the Year",
      "context": "Larping: playing a part, from live-action role-playing. Agentic: software that acts on its own. Looksmaxxing: going all out to improve your looks.",
      "options": [
        {
          "label": "vibe",
          "short": "vibe",
          "emoji": "✨",
          "percent": 4
        },
        {
          "label": "looksmaxxing",
          "short": "looksmaxxing",
          "emoji": "🪞",
          "percent": 6
        },
        {
          "label": "larping",
          "short": "larping",
          "emoji": "🎭",
          "percent": 22
        },
        {
          "label": "agentic",
          "short": "agentic",
          "emoji": "🤖",
          "percent": 10
        }
      ],
      "roastWrong": "{n} picked {pick}, at {pp}%. The world’s word is larping, at {w}%, which is also what that pick was.",
      "answer": 2,
      "partial": {
        "3": 8
      }
    },
    {
      "id": "g11",
      "kind": "pick",
      "flavor": "match",
      "ours": true,
      "topic": "Screen and games",
      "emoji": "🪙",
      "target": 50,
      "prompt": "Which of these is a coin flip?",
      "sub": "The world has one of them at about 50%.",
      "short": "The coin flip",
      "context": "Avengers: Secret Wars is the Marvel film planned for December 2027.",
      "options": [
        {
          "label": "Johnny Depp is cast in the next Pirates of the Caribbean film",
          "short": "Johnny Depp in Pirates",
          "emoji": "🏴‍☠️",
          "percent": 77
        },
        {
          "label": "OpenAI launches a gadget by the end of the year",
          "short": "the OpenAI gadget",
          "emoji": "📱",
          "percent": 19
        },
        {
          "label": "Avengers: Secret Wars is delayed",
          "short": "the Marvel delay",
          "emoji": "🎬",
          "percent": 50
        },
        {
          "label": "Spider-Man: Brand New Day is the top-grossing movie of 2026",
          "short": "Spider-Man on top",
          "emoji": "🕷️",
          "percent": 88
        }
      ],
      "roastWrong": "{n} picked {pick}, which the world has at {pp}%. The coin flip was the Marvel delay, at {w}%.",
      "answer": 2,
      "partial": {
        "0": 8
      }
    },
    {
      "id": "g12",
      "kind": "chance",
      "ours": false,
      "topic": "Sports",
      "emoji": "🐻",
      "extras": [
        "🏒",
        "🥅"
      ],
      "prompt": "The Boston Bruins make the playoffs",
      "short": "Bruins make the playoffs",
      "context": "Sixteen of the 32 NHL teams make the playoffs. The regular season ends in April.",
      "answer": 72,
      "roastHigh": "{n} gave the Bruins {g}%. That is a jersey talking. The world says {w}%.",
      "roastLow": "{n} gave the Bruins {g}%. Somewhere in Boston, somebody just felt a chill."
    },
    {
      "id": "g13",
      "kind": "pick",
      "flavor": "longshot",
      "ours": true,
      "topic": "Odd ones",
      "emoji": "🎯",
      "prompt": "Which of these is the longest shot?",
      "short": "The longest shot",
      "context": "Bryan Johnson is the tech founder trying not to age. The Elder Scrolls VI was announced in 2018. Ryanair is a budget airline based in Ireland.",
      "options": [
        {
          "label": "The Elder Scrolls VI is out before 2028",
          "short": "The Elder Scrolls VI",
          "emoji": "🗡️",
          "percent": 13
        },
        {
          "label": "Jenna Ortega hosts Saturday Night Live this season",
          "short": "Jenna Ortega hosting",
          "emoji": "📺",
          "percent": 31
        },
        {
          "label": "Elon Musk buys Ryanair this year",
          "short": "the Ryanair purchase",
          "emoji": "✈️",
          "percent": 1
        },
        {
          "label": "Bryan Johnson dunks a basketball before 2027",
          "short": "the dunk",
          "emoji": "⛹️",
          "percent": 16
        }
      ],
      "roastWrong": "{n} picked {pick}, at {pp}%. The world gives Elon Musk buying an airline {w}%.",
      "answer": 2,
      "partial": {
        "0": 8
      }
    },
    {
      "id": "g14",
      "kind": "chance",
      "ours": false,
      "topic": "Space and science",
      "emoji": "🤖",
      "extras": [
        "🔴",
        "👣"
      ],
      "prompt": "A humanoid robot walks on Mars before a human does",
      "short": "A robot walks on Mars first",
      "context": "No person has been to Mars. Rovers on wheels have. A walking robot has not.",
      "answer": 51,
      "roastHigh": "{n} said {g}%. {n} welcome{s} the robots. The world is split, at {w}%.",
      "roastLow": "{n} said {g}%. {n} still believe{s} in people. The world is split, at {w}%."
    }
  ]
};
