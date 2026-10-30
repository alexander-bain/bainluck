# Comparison Feed Two: result

PILLARS: DISCOVER. Prepared by Fable for Alex, Tue 2026-10-06, 5:15pm PT. Follows `FABLE-FEED-TWO-20261006.md`. Offline prototype; nothing touched in the repository, production, GitHub or any lane. One person on a prototype page. Not a ruling.

Exports: `fable-evidence-20261006-feed-two-result/` (signal records and run record as stored, one joined CSV, the script that prints every number here and its output, SHA-256 manifest verified after writing).

## 1. What happened

Alex scrolled all 21 cards in about 4 minutes, 4:56 to 5:00pm PT, in a 950 by 1028 window on a computer. He reacted to every card.

- Liked 16. Shared 3, all three also liked. Not for me 5. No card left without a reaction.
- Details opened on none.
- Every card recorded reading time. None recorded zero. Two cards were visited twice.

## 2. Findings

1. **"Not for me" was the informative button.** Like went to 16 of 21 cards, so it separates little. The five "not for me" cards were: the closest Senate races, the Nevada governor race, a week's movers led by the Senate Democratic leader election, Spain's soccer title, and an end-of-October board. Three of the five are state or congressional politics and one is soccer. That reads as topic, not card quality, which is what a personalization signal should capture.
2. **Round-ups were shared again.** Two of the three shares were round-ups (Division Series; NFL awards). Across both trials, 4 of 5 shares went to round-ups, and the Division Series card was shared both times. The third share was the tipping-point card on OpenAI announcing AGI.
3. **A round-up is not liked for being a round-up.** Four of five were liked; the Senate one was "not for me". The subject still decides.
4. **Reading time now points the right way, weakly.** Median first-visit time was 10.3 seconds on liked cards and 5.5 on "not for me" cards. Rank correlation between first-visit time and reaction is +0.47. Leaving out the first and last cards, which each sat on screen for 34 seconds beside the intro and the end note, it falls to +0.27, about the same as the +0.28 with card length. With 19 cards that is a direction, not a result.
5. **The timer fix worked, with one flaw left.** No zero-second cards in the same window that produced three last time. One card recorded a 0.3-second first visit because its first visit was shared with a taller neighbour; total time for that card was 6.1 seconds. First-visit time should require a minimum share before it is closed.
6. **The chart look is inconclusive.** All three chart cards were liked. Of the three two-outcome cards without a chart, one was liked and two were "not for me", but those two were the soccer card and the Nevada card. Topic explains it at least as well as the chart.
7. **Nothing was opened.** Zero detail opens against four last time. Consistent with Alex's point that he opens details when in doubt, and with fewer doubtful cards in this feed.

## 3. What I take from it

- For a small feed and one reader, the explicit negative is the most useful signal, and it describes the topic. A ranking that learns from it should learn "less state politics, less soccer", not "fewer swing cards".
- Like is close to a default when the cards are good. It may separate better across many readers than within one.
- Round-ups remain the strongest type for sharing. The next round-up work is subject choice.
- Reading time needs many more impressions before it can carry weight, and the first and last positions should be excluded.
- Everyone reacting to every card is not how a feed is used. Alex described it as grading. Real use will leave most cards without a reaction, so the implicit signals will matter more there than here.

## 4. Where this maps in GitHub (no new issues proposed)

| Point | Existing issue |
|---|---|
| "Not for me" as a topic signal; like, share, reading time | #5105, #2299 |
| Round-up cards and subject choice | #10346, #9237 stage 2 |
| One question per feed held with no complaint of repetition | #10356 |
| Already-happened check caught 2 of 106 before display | #10353 |

## 5. Limits

One person, 21 cards, one run of four minutes, a computer window, a prototype page, venue prices. Every card got a reaction because the reader treated it as a grading task. Nothing here measures readers or the product.
