// SET THREE for /guess: THREE STEPS (430: A).
//
// GENERATED from a public read of Bain Luck's own pages taken Wed Nov 25, 8:12 PM PT. Every
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
  "id": "2026-11-25-c",
  "code": "c1",
  "asOf": "Wed Nov 25, 8:12 PM PT",
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
    0,
    0,
    0,
    1,
    1,
    1,
    3,
    3,
    1,
    0,
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
      "topic": "Sports",
      "emoji": "⛳",
      "extras": [
        "🇺🇸",
        "🏆"
      ],
      "prompt": "Team USA wins the 2027 Ryder Cup",
      "short": "USA wins the Ryder Cup",
      "context": "Europe has won the last two. The 2027 matches are in Ireland, and a tie is possible.",
      "answer": 40,
      "id": "t1"
    },
    {
      "kind": "versus",
      "flavor": "versus",
      "ours": true,
      "topic": "Sports",
      "emoji": "🤼",
      "prompt": "Which is more likely?",
      "short": "Brady in the WWE, or Rondo at the Olympics",
      "context": "Brady won seven Super Bowls. Rondo won NBA titles with the Celtics and the Lakers. Flag football joins the Olympics in 2028.",
      "options": [
        {
          "label": "Rajon Rondo plays flag football at the 2028 Olympics",
          "short": "Rondo at the Olympics",
          "emoji": "🏈",
          "percent": 15
        },
        {
          "label": "Tom Brady fights in the WWE before 2028",
          "short": "Brady in the WWE",
          "emoji": "🤼",
          "percent": 29
        }
      ],
      "id": "t2"
    },
    {
      "kind": "side",
      "flavor": "side",
      "ours": false,
      "topic": "Stars",
      "emoji": "💒",
      "extras": [
        "🎤",
        "🎬"
      ],
      "prompt": "Harry Styles and Zoë Kravitz are married before 2027",
      "short": "Styles and Kravitz marry this year",
      "context": "The singer and the actor were first linked in 2025. The year has five weeks left.",
      "answer": 18,
      "id": "t3"
    },
    {
      "kind": "versus",
      "flavor": "versus",
      "ours": true,
      "topic": "Odd stuff",
      "emoji": "🌋",
      "prompt": "Which is more likely?",
      "short": "A supervolcano, or a Rihanna album",
      "context": "Rihanna’s last album, Anti, came out in 2016. The last supervolcano eruption was about 26,000 years ago.",
      "options": [
        {
          "label": "A supervolcano erupts before 2050",
          "short": "A supervolcano",
          "emoji": "🌋",
          "percent": 31
        },
        {
          "label": "Rihanna releases an album this year",
          "short": "A Rihanna album",
          "emoji": "💿",
          "percent": 2
        }
      ],
      "id": "t4"
    },
    {
      "kind": "side",
      "flavor": "side",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "❄️",
      "extras": [
        "🌨️",
        "🏙️"
      ],
      "prompt": "Boston gets more than two inches of snow in December",
      "short": "Two inches of snow in Boston",
      "context": "All the snow measured in Boston over the whole month counts.",
      "answer": 62,
      "id": "t5"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "📺",
      "extras": [
        "🏃",
        "💯"
      ],
      "prompt": "IShowSpeed reaches 100 million YouTube subscribers before 2029",
      "short": "IShowSpeed hits 100 million",
      "context": "IShowSpeed is a streamer. Only a few channels have ever passed 100 million subscribers.",
      "answer": 51,
      "options": [
        12,
        25,
        38,
        51
      ],
      "id": "t6"
    },
    {
      "kind": "leader",
      "flavor": "leader",
      "ours": false,
      "topic": "Stars",
      "emoji": "🎤",
      "prompt": "Who is most likely to perform at the Super Bowl halftime show?",
      "sub": "Not counting Jay-Z, who is all but certain.",
      "short": "Halftime show guests",
      "independent": true,
      "context": "The show is on February 14, 2027. More than one of these four can be on that stage.",
      "options": [
        {
          "label": "Eminem",
          "short": "Eminem",
          "emoji": "🎧",
          "percent": 24
        },
        {
          "label": "Justin Timberlake",
          "short": "Timberlake",
          "emoji": "🕺",
          "percent": 40
        },
        {
          "label": "Beyoncé",
          "short": "Beyoncé",
          "emoji": "👑",
          "percent": 70
        },
        {
          "label": "Pharrell Williams",
          "short": "Pharrell",
          "emoji": "🎩",
          "percent": 43
        }
      ],
      "id": "t7"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Sports",
      "emoji": "🏈",
      "extras": [
        "🧢",
        "🏟️"
      ],
      "prompt": "The New England Patriots make the playoffs",
      "short": "Patriots make the playoffs",
      "context": "Fourteen of the 32 NFL teams get in. The regular season ends in early January.",
      "answer": 30,
      "options": [
        30,
        45,
        60,
        75
      ],
      "id": "t8"
    },
    {
      "kind": "leader",
      "flavor": "leader",
      "ours": false,
      "topic": "Sports",
      "emoji": "🏈",
      "prompt": "Who is the favorite to win the NFC South?",
      "short": "NFC South favorite",
      "independent": false,
      "context": "Four teams, one division title. The regular season ends in early January.",
      "options": [
        {
          "label": "Falcons",
          "short": "Falcons",
          "emoji": "🦅",
          "percent": 10
        },
        {
          "label": "Panthers",
          "short": "Panthers",
          "emoji": "🐆",
          "percent": 53
        },
        {
          "label": "Saints",
          "short": "Saints",
          "emoji": "⚜️",
          "percent": 8
        },
        {
          "label": "Buccaneers",
          "short": "Buccaneers",
          "emoji": "🏴‍☠️",
          "percent": 27
        }
      ],
      "id": "t9"
    },
    {
      "kind": "four",
      "flavor": "four",
      "ours": false,
      "topic": "Stars",
      "emoji": "🎬",
      "extras": [
        "🌟",
        "🏆"
      ],
      "prompt": "Zendaya is nominated for Best Actress at the Oscars",
      "short": "Zendaya gets an Oscar nomination",
      "context": "Nominations for the 99th Academy Awards come out in January.",
      "answer": 36,
      "options": [
        8,
        22,
        36,
        57
      ],
      "id": "t10"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars",
      "emoji": "👯",
      "extras": [
        "📸",
        "🤝"
      ],
      "prompt": "Blake Lively and Taylor Swift are seen together in public this year",
      "short": "Lively and Swift seen together",
      "context": "The two were close friends for years. The year has five weeks left.",
      "answer": 9,
      "roastHigh": "{n} said {g}%. {n} still believe{s} in best friends forever. The world says {w}%.",
      "id": "t11"
    },
    {
      "kind": "chance",
      "flavor": "straight",
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
      "answer": 71,
      "roastHigh": "{n} said {g}%. {n} {has} already cleared the calendar for May.",
      "roastLow": "{n} said {g}%. Nobody tell Boston what {n} said.",
      "id": "t12"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Stars",
      "emoji": "💍",
      "extras": [
        "🎬",
        "🎵"
      ],
      "prompt": "Sydney Sweeney and Scooter Braun get engaged this year",
      "short": "Sweeney and Braun get engaged",
      "context": "The actor and the music manager were first linked in 2025. The year has five weeks left.",
      "answer": 24,
      "roastHigh": "{n} said {g}%. {n} {has} already picked an outfit for the wedding.",
      "roastLow": "{n} said {g}%. {n} think{s} love is dead. The world says {w}%.",
      "id": "t13"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Sports",
      "emoji": "👑",
      "extras": [
        "🏀",
        "⏳"
      ],
      "prompt": "LeBron James retires before the 2027–28 NBA season",
      "short": "LeBron retires after this season",
      "context": "James turns 42 on December 30. He entered the NBA in 2003.",
      "answer": 42,
      "roastHigh": "{n} said {g}%. {n} {has} been calling it his last year since 2020.",
      "roastLow": "{n} said {g}%. {n} think{s} he plays until his grandkids are in the league.",
      "id": "t14"
    },
    {
      "kind": "chance",
      "flavor": "straight",
      "ours": false,
      "topic": "Odd stuff",
      "emoji": "🎮",
      "extras": [
        "🖥️",
        "🚗"
      ],
      "prompt": "Grand Theft Auto VI comes out on PC before 2028",
      "short": "GTA VI on PC before 2028",
      "context": "Rockstar has announced GTA VI for consoles only so far. Its last two big games took more than a year to reach PC.",
      "answer": 90,
      "roastLow": "{n} said {g}%. {n} think{s} PC players can wait. They always do. The world says {w}%.",
      "id": "t15"
    }
  ]
};
