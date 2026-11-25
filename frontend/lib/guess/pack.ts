// SET TWO for /guess (429: A).
//
// GENERATED from a public read of Bain Luck's own pages taken Wed Nov 25, 12:02 PM PT. Every
// number below was looked up by market and outcome when the set was built;
// none was typed. Two answers are worked out from looked-up numbers: the "none
// of the favorites" card is the rest of a field that adds to exactly 100, and
// the count card counts teams above 50% with none on the line. The sentences,
// the context lines and the roasts are written by hand. A set is a dated
// edition: its numbers stay as they were read, and the page says when that was.
//
// EVERY CARD IS A SLIDER. Ten restate one market (`flavor: "straight"`), kept
// because the odd subjects are the fun. Four are ours (`ours: true`) and put
// markets side by side: given this, guess that; none of the favorites; how
// many of the 32; two numbers on one card. The marks people give at the end of
// a round are kept with the flavor, and the share of ours goes up only as
// those marks say it should.
//
// `__tests__/guess/guessPack.test.ts` holds this file to its rules.

import type { GamePack } from "./types";

export const GUESS_PACK: GamePack = {
  "id": "2026-11-25-b",
  "code": "b1",
  "asOf": "Wed Nov 25, 12:02 PM PT",
  "perRound": 7,
  "topics": [
    "Sports",
    "Screen and games",
    "Stars and sky"
  ],
  "cards": [
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Screen and games",
      "emoji": "🏎️",
      "extras": [
        "🔥",
        "👨‍👩‍👧‍👦"
      ],
      "prompt": "A new Fast & Furious film is officially announced in 2026",
      "short": "A new Fast & Furious film",
      "context": "The last main Fast & Furious film, Fast X, came out in 2023.",
      "answer": 5,
      "roastHigh": "{n} said {g}%. {n} believe{s} in one thing: family. The world says {w}%.",
      "id": "h1"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "🦬",
      "extras": [
        "🏈",
        "❄️"
      ],
      "prompt": "The Buffalo Bills finish as the AFC’s top seed",
      "short": "Bills get the AFC’s top seed",
      "context": "The top seed gets a week off, then home games in the playoffs.",
      "answer": 52,
      "roastHigh": "{n} said {g}%. Buffalo thanks {n}, and reminds {n} how January usually goes.",
      "roastLow": "{n} said {g}%. {n} {has} seen how Buffalo’s Januarys end and {is} getting in early.",
      "id": "h2"
    },
    {
      "kind": "chance",
      "flavor": "given",
      "ours": true,
      "topic": "Screen and games",
      "emoji": "🎮",
      "extras": [
        "📖",
        "🏆"
      ],
      "given": {
        "text": "The same game is 94% to win Game of the Year.",
        "percent": 94,
        "label": "Game of the Year",
        "answerLabel": "Best Narrative"
      },
      "prompt": "Grand Theft Auto VI wins Best Narrative at The Game Awards",
      "short": "GTA VI wins Best Narrative",
      "context": "The Game Awards hand out both in December. Best Narrative is the prize for story.",
      "answer": 81,
      "roastLow": "{n} said {g}%. {n} skip{s} the cutscenes. The world says {w}%.",
      "id": "h3"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars and sky",
      "emoji": "🚀",
      "extras": [
        "🔴",
        "🧑‍🚀"
      ],
      "prompt": "Starship carries people to Mars before 2030",
      "short": "Starship takes people to Mars",
      "context": "Starship is SpaceX’s giant rocket. No person has ever been to Mars.",
      "answer": 12,
      "roastHigh": "{n} said {g}%. {n} {has} already picked a window seat.",
      "id": "h4"
    },
    {
      "kind": "count",
      "flavor": "count",
      "ours": true,
      "topic": "Sports",
      "emoji": "🏒",
      "prompt": "How many of the 32 NHL teams are above 50% to make the playoffs?",
      "short": "NHL teams above 50%",
      "context": "Sixteen of the 32 teams make the playoffs. The regular season ends in April.",
      "answer": 14,
      "max": 32,
      "step": 2,
      "noun": "teams",
      "roastLow": "{n} said {g}. The world is sure of {w}. {n} trust{s} nobody.",
      "roastHigh": "{n} said {g}. There are 16 playoff spots, {n}.",
      "id": "h5"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars and sky",
      "emoji": "🌊",
      "extras": [
        "💿",
        "🎧"
      ],
      "prompt": "Frank Ocean releases a new album in 2027",
      "short": "A Frank Ocean album in 2027",
      "context": "His last album, Blonde, came out in 2016.",
      "answer": 29,
      "roastHigh": "{n} said {g}%. {n} {has} been saying that since 2016.",
      "roastLow": "{n} said {g}%. {n} {has} been hurt before.",
      "id": "h6"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "🏈",
      "extras": [
        "🌉",
        "🥇"
      ],
      "prompt": "The San Francisco 49ers finish as the NFC’s top seed",
      "short": "49ers get the NFC’s top seed",
      "context": "The top seed gets a week off, then home games in the playoffs.",
      "answer": 69,
      "roastLow": "{n} said {g}%. The world says {w}%. {n} {has} a grudge, and it is showing.",
      "roastHigh": "{n} said {g}%. {n} {has} already taken the week off with them.",
      "id": "h7"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars and sky",
      "emoji": "💍",
      "extras": [
        "🎬",
        "💄"
      ],
      "prompt": "Timothée Chalamet and Kylie Jenner get engaged in 2026",
      "short": "Chalamet and Jenner get engaged",
      "context": "The actor and the makeup mogul were first linked in 2023.",
      "answer": 11,
      "roastHigh": "{n} said {g}%. The year is nearly over, {n}. That is a fast ring.",
      "id": "h8"
    },
    {
      "kind": "chance",
      "flavor": "rest",
      "ours": true,
      "topic": "Sports",
      "emoji": "🏀",
      "extras": [
        "🏆",
        "🤷"
      ],
      "prompt": "The NBA champion is not the Spurs, the Thunder or the 76ers",
      "sub": "Those are the three favorites.",
      "short": "None of the three NBA favorites",
      "context": "Thirty teams are playing for it. The three favorites together come to less than half.",
      "answer": 57,
      "parts": [
        {
          "label": "Spurs",
          "percent": 20
        },
        {
          "label": "Thunder",
          "percent": 12
        },
        {
          "label": "76ers",
          "percent": 11
        }
      ],
      "roastLow": "{n} said {g}%. Three teams, {n}. Twenty-seven others are also trying.",
      "roastHigh": "{n} said {g}%. The Spurs would like a word with {n}.",
      "id": "h9"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "🐯",
      "extras": [
        "🏈",
        "🎯"
      ],
      "prompt": "Joe Burrow leads the NFL in passing touchdowns",
      "short": "Burrow leads in passing touchdowns",
      "context": "Burrow is the Cincinnati Bengals’ quarterback. The regular season ends in early January.",
      "answer": 78,
      "roastLow": "{n} said {g}%. {n} {has} not looked at a box score since September. The world says {w}%.",
      "roastHigh": "{n} said {g}%. {n} would like the season stopped now, please.",
      "id": "h10"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars and sky",
      "emoji": "❄️",
      "extras": [
        "🎄",
        "🌆"
      ],
      "prompt": "It snows in Chicago on Christmas Day",
      "short": "Snow in Chicago on Christmas",
      "context": "Any measurable snowfall in Chicago on December 25 counts.",
      "answer": 33,
      "roastHigh": "{n} said {g}%. {n} {is} dreaming of a white Christmas. The world is awake.",
      "roastLow": "{n} said {g}%. It is Chicago, in December, {n}.",
      "id": "h11"
    },
    {
      "kind": "duo",
      "flavor": "duo",
      "ours": true,
      "topic": "Screen and games",
      "emoji": "🎬",
      "prompt": "Avengers: Doomsday. One movie, two chances.",
      "sub": "Slide both.",
      "short": "Avengers: Doomsday, twice",
      "context": "The movie opens in mid-December. Google usually publishes its list of the year’s top searches in early December.",
      "parts": [
        {
          "label": "It has the biggest opening weekend of 2026",
          "short": "the opening weekend",
          "emoji": "🍿",
          "answer": 92
        },
        {
          "label": "It is Google’s most-searched movie of 2026",
          "short": "the Google one",
          "emoji": "🔎",
          "answer": 6
        }
      ],
      "roastFlip": "{n} had it winning Google but not the weekend. The world has that the other way round.",
      "roastFar": "{n} missed {part} by {d}. Doomsday came early for {n}.",
      "id": "h12"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "☘️",
      "extras": [
        "🏀",
        "🪑"
      ],
      "prompt": "Payton Pritchard wins Sixth Man of the Year",
      "short": "Pritchard wins Sixth Man",
      "context": "Pritchard plays for the Boston Celtics. He won this award in 2025.",
      "answer": 20,
      "roastHigh": "{n} said {g}%. {n} would also like him to start.",
      "roastLow": "{n} said {g}%. Somebody tell {n} he already has one.",
      "id": "h13"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars and sky",
      "emoji": "🎤",
      "extras": [
        "📰",
        "✨"
      ],
      "prompt": "Taylor Swift is named Time’s Person of the Decade",
      "short": "Swift is Person of the Decade",
      "context": "She was Time’s Person of the Year in 2023.",
      "answer": 14,
      "roastHigh": "{n} said {g}%. {n} {has} been making friendship bracelets about it.",
      "id": "h14"
    }
  ]
};
