// #8167 — TWO IDENTICAL, COMPLETELY UNLABELLED LADDER CARDS.
//
// lane1b/517 photographed this at 390px on production `83a20bc7`, on two
// independent boards. `/futures/59319183` ("San Diego vs Atlanta: Spread")
// draws two stacked cards, each reading exactly `≥ 1.5 runs / ≥ 2.5 runs /
// ≥ 3.5 runs`, with no heading on either. One is Atlanta's ladder and one is
// San Diego's and nothing on the page says which. Settled, every leg prices at
// `0`, so the two cards are literally pixel-alike.
//
// The identity was in the payload the whole time. `GET /api/futures/groups/
// kalshi:KXMLBSPREAD-26JUL201915SDATL` served, verbatim:
//
//     stem 'atlanta wins by over #'    Atlanta wins by over 1.5 / 2.5 / 3.5 runs
//     stem 'san diego wins by over #'  San Diego wins by over 1.5 / 2.5 / 3.5 runs
//     group_title 'San Diego vs Atlanta: Spread'   (=== the page <h1>)
//
// Every existing refusal fires in turn and correctly: the stems hold `#`
// (#7398), the group title echoes the `<h1>` (#7398), and #8019's rule finds no
// `": "` separator. The gap is that a spread board states its subject as prose.
//
// These are the real strings, not paraphrases.

import {
  ladderDistinguishingSubjects,
  ladderSubjectHeading,
  thresholdLadderTitle,
  thresholdLadderTitles,
} from "@/lib/futuresLadder";

const SD_ATL_H1 = "San Diego vs Atlanta: Spread";
const ATLANTA = [
  "Atlanta wins by over 1.5 runs",
  "Atlanta wins by over 2.5 runs",
  "Atlanta wins by over 3.5 runs",
];
const SAN_DIEGO = [
  "San Diego wins by over 1.5 runs",
  "San Diego wins by over 2.5 runs",
  "San Diego wins by over 3.5 runs",
];

// The second board in the filing — a two-word subject on BOTH sides of the
// strip, so it catches an off-by-one in "how many trailing words are shared".
const PIT_CHC_H1 = "Pittsburgh vs Chicago C: Spread";
const PITTSBURGH = [
  "Pittsburgh wins by over 1.5 runs",
  "Pittsburgh wins by over 2.5 runs",
  "Pittsburgh wins by over 3.5 runs",
];
const CHICAGO_C = [
  "Chicago C wins by over 1.5 runs",
  "Chicago C wins by over 2.5 runs",
  "Chicago C wins by over 3.5 runs",
];

describe("#8167 — the two sides of a spread board are told apart", () => {
  test("the filing's own board yields Atlanta and San Diego", () => {
    expect(ladderDistinguishingSubjects([ATLANTA, SAN_DIEGO])).toEqual([
      "Atlanta",
      "San Diego",
    ]);
  });

  test("the second board yields Pittsburgh and Chicago C", () => {
    expect(ladderDistinguishingSubjects([PITTSBURGH, CHICAGO_C])).toEqual([
      "Pittsburgh",
      "Chicago C",
    ]);
  });

  test("end to end: the second board's two cards get their two team names", () => {
    // The lib-level assertion above proves the strip; this one proves the
    // second board also survives the two refusals `thresholdLadderTitles`
    // applies after it — its `group_title` echoes its own `<h1>` exactly as
    // the first board's does, which is the condition that blanked both cards.
    expect(
      thresholdLadderTitles(
        [
          { stem: "pittsburgh wins by over #", outcomeNames: PITTSBURGH },
          { stem: "chicago c wins by over #", outcomeNames: CHICAGO_C },
        ],
        PIT_CHC_H1,
        PIT_CHC_H1,
      ),
    ).toEqual(["Pittsburgh", "Chicago C"]);
  });

  test("the casing is the payload's, never the lowercased stem", () => {
    // The stems are `san diego wins by over #`. A subject read off the stem
    // would print "san diego" as a heading.
    const [, sd] = ladderDistinguishingSubjects([ATLANTA, SAN_DIEGO]);
    expect(sd).toBe("San Diego");
    expect(sd).not.toBe("san diego");
  });

  test("end to end: the two cards on the real board get the two team names", () => {
    expect(
      thresholdLadderTitles(
        [
          { stem: "atlanta wins by over #", outcomeNames: ATLANTA },
          { stem: "san diego wins by over #", outcomeNames: SAN_DIEGO },
        ],
        SD_ATL_H1,
        SD_ATL_H1,
      ),
    ).toEqual(["Atlanta", "San Diego"]);
  });

  test("the whole point: the two headings differ", () => {
    // The defect is not "no heading", it is "the same nothing twice". A repair
    // that gave both cards one identical heading would pass every assertion
    // above that only checks for non-emptiness.
    const [a, b] = thresholdLadderTitles(
      [
        { stem: "atlanta wins by over #", outcomeNames: ATLANTA },
        { stem: "san diego wins by over #", outcomeNames: SAN_DIEGO },
      ],
      SD_ATL_H1,
      SD_ATL_H1,
    );
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(a).not.toBe(b);
  });

  test("the verb phrase is stripped, not printed", () => {
    // The common prefix of one group is "Atlanta wins by over". Printing THAT
    // as a heading is the naive repair, and it is prose on a card.
    const [atl] = ladderDistinguishingSubjects([ATLANTA, SAN_DIEGO]);
    expect(atl).toBe("Atlanta");
    expect(atl).not.toContain("wins");
  });
});

describe("#8167 — what it refuses", () => {
  test("a single ladder gets nothing: there is no sibling to tell it from", () => {
    expect(ladderDistinguishingSubjects([ATLANTA])).toEqual([undefined]);
  });

  test("two groups with the SAME subject distinguish nothing, so neither is named", () => {
    const over = ["Atlanta wins by over 1.5 runs", "Atlanta wins by over 2.5 runs"];
    const under = ["Atlanta wins by over 4.5 runs", "Atlanta wins by over 5.5 runs"];
    expect(ladderDistinguishingSubjects([over, under])).toEqual([undefined, undefined]);
  });

  test("a subject with no subject in it is refused, not shortened to a verb", () => {
    // One side's payload omits its name, so its prefix IS the shared verb
    // phrase. Stripping maximally empties it and the group is refused. The
    // tempting guard — "never strip the last word" — instead labels these two
    // cards "wins" and "Atlanta wins", which is worse than the blank it fixes.
    const bare = ["wins by over 1.5 runs", "wins by over 2.5 runs"];
    expect(ladderDistinguishingSubjects([bare, ATLANTA])).toEqual([
      undefined,
      undefined,
    ]);
  });

  test("the WORD cap alone refuses, with every subject inside the char cap", () => {
    // 5 words, 17 chars. Trips only the word ceiling — so this is what proves
    // that ceiling exists. The two caps mask each other on any specimen that
    // breaks both.
    const a = ["Win by a lot more than 1", "Win by a lot more than 2"];
    const b = ["Lose by a bit less than 1", "Lose by a bit less than 2"];
    const [x] = ladderDistinguishingSubjects([a, b]);
    expect(x).toBeUndefined();
  });

  test("the CHAR cap alone refuses, with every subject inside the word cap", () => {
    // 2 words, 33 chars. Trips only the character ceiling.
    const a = [
      "Borussia Moenchengladbach-Reserve wins 1",
      "Borussia Moenchengladbach-Reserve wins 2",
    ];
    const b = ["Koeln wins 1", "Koeln wins 2"];
    expect(ladderDistinguishingSubjects([a, b])).toEqual([undefined, undefined]);
  });

  test("the shared trailing phrase is matched regardless of casing", () => {
    // Venue naming is not consistent about capitalising a verb phrase. A
    // case-SENSITIVE compare stops stripping at the first differing case and
    // leaves prose on the card.
    const a = ["Atlanta Wins By Over 1.5 runs", "Atlanta Wins By Over 2.5 runs"];
    const b = ["San Diego wins by over 1.5 runs", "San Diego wins by over 2.5 runs"];
    expect(ladderDistinguishingSubjects([a, b])).toEqual(["Atlanta", "San Diego"]);
  });

  test("three ladders where TWO collide are all refused, not two-thirds labelled", () => {
    // The pair strips to "Atlanta" twice while the third gives "San Diego". A
    // rule that only asks for two DIFFERENT subjects passes this and prints the
    // reported defect — two identical headings — on the colliding pair.
    const atlantaOver = ["Atlanta wins 1", "Atlanta wins 2"];
    const atlantaUnder = ["Atlanta wins 3", "Atlanta wins 4"];
    const sanDiego = ["San Diego wins 1", "San Diego wins 2"];
    expect(
      ladderDistinguishingSubjects([atlantaOver, atlantaUnder, sanDiego]),
    ).toEqual([undefined, undefined, undefined]);
  });

  test("three ladders that all differ are all named", () => {
    // The both-directions half: the rule above must not refuse a healthy board.
    expect(
      ladderDistinguishingSubjects([
        ["Atlanta wins 1", "Atlanta wins 2"],
        ["San Diego wins 1", "San Diego wins 2"],
        ["Boston wins 1", "Boston wins 2"],
      ]),
    ).toEqual(["Atlanta", "San Diego", "Boston"]);
  });

  test("prose is refused rather than printed as a heading", () => {
    // Nothing shared to strip, so the remainder is the whole common prefix —
    // a sentence, not a subject. 24 chars / 4 words is the ceiling.
    const a = [
      "Will the Federal Reserve cut rates in March 2027",
      "Will the Federal Reserve cut rates in April 2027",
    ];
    const b = [
      "Some entirely different long question about policy 1",
      "Some entirely different long question about policy 2",
    ];
    expect(ladderDistinguishingSubjects([a, b])).toEqual([undefined, undefined]);
  });

  test("a group whose names share no leading word at all is refused", () => {
    expect(
      ladderDistinguishingSubjects([["Alpha one", "Beta two"], SAN_DIEGO]),
    ).toEqual([undefined, undefined]);
  });

  test("empty and blank names are refused, not turned into an empty heading", () => {
    expect(ladderDistinguishingSubjects([[], SAN_DIEGO])).toEqual([undefined, undefined]);
    expect(ladderDistinguishingSubjects([["", "  "], SAN_DIEGO])).toEqual([
      undefined,
      undefined,
    ]);
  });

  test("a subject that echoes the page <h1> is still refused (#7398 is not bypassed)", () => {
    const left = ["Boston 1 run", "Boston 2 runs"];
    const right = ["Boston 3 runs", "Boston 4 runs"];
    // Same subject both sides ⇒ refused before the echo test even matters; the
    // clause that matters is that `thresholdLadderTitles` routes subjects
    // through `printableHeading`, asserted directly below.
    expect(thresholdLadderTitles(
      [
        { stem: "boston #", outcomeNames: left },
        { stem: "boston #", outcomeNames: right },
      ],
      null,
      "Boston",
    )).toEqual([undefined, undefined]);
  });

  test("a derived subject identical to the <h1> is dropped", () => {
    expect(
      thresholdLadderTitles(
        [
          { stem: "atlanta wins by over #", outcomeNames: ATLANTA },
          { stem: "san diego wins by over #", outcomeNames: SAN_DIEGO },
        ],
        null,
        "Atlanta",
      ),
    ).toEqual([undefined, "San Diego"]);
  });
});

describe("#8167 — nothing that reads correctly today moves", () => {
  test("#8019's colon board is decided by #8019's rule, unchanged", () => {
    // `thresholdLadderTitle` answers first, so the page-level rule never runs.
    const buffalo = ["Buffalo: 1 or more wins", "Buffalo: 2 or more wins"];
    const pitt = ["Pittsburgh: 1 or more wins", "Pittsburgh: 2 or more wins"];
    expect(ladderSubjectHeading(buffalo)).toBe("Buffalo");
    expect(
      thresholdLadderTitles(
        [
          { stem: "buffalo: # or more wins", outcomeNames: buffalo },
          { stem: "pittsburgh: # or more wins", outcomeNames: pitt },
        ],
        "Pro Football: Team Wins in First 8 Weeks",
        "Pro Football: Team Wins in First 8 Weeks",
      ),
    ).toEqual(["Buffalo", "Pittsburgh"]);
  });

  test("a real group title that says something new still wins", () => {
    // #7398's keep-clause: a cross-market group title is real context.
    expect(
      thresholdLadderTitles(
        [
          { stem: "# or below", outcomeNames: ["Above 70", "Above 74"] },
          { stem: "above #", outcomeNames: ["Above 80", "Above 84"] },
        ],
        "30Y Treasury yield, all venues",
        "How low will the 30Y US Treasury yield get by Sep 30, 2026?",
      ),
    ).toEqual(["30Y Treasury yield, all venues", "30Y Treasury yield, all venues"]);
  });

  test("the single-argument rule is untouched for every input #7398 pinned", () => {
    expect(thresholdLadderTitle("# or below", null, "Treasury")).toBeUndefined();
    expect(thresholdLadderTitle("above #", "Treasury", "Treasury")).toBeUndefined();
    expect(thresholdLadderTitle("Grouped rounds", null, "Treasury")).toBe("Grouped rounds");
  });
});
