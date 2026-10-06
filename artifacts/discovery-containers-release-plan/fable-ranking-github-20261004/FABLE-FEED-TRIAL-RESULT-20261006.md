# Comparison Feed Trial: result

PILLARS: DISCOVER, TRUTH. Prepared by Fable for Alex, Tue 2026-10-06, 1:25pm PT. Follows `17-FABLE-FEED-TRIAL-AND-EVIDENCE.md` (my file 15, renamed by Root). Offline; nothing touched in the repository, production, GitHub or any lane. Founder evidence from one person on a prototype page. Not a ruling.

Exports: `fable-evidence-20261006-feed-result/` (signals, grades and run metadata as stored, one joined CSV, SHA-256 manifest).

## 1. What happened

Alex read all 26 cards and graded all 26. Conditions that limit the result:

- Window 950 by 1028 pixels, so a computer, not a phone. About two cards were on screen at once.
- The run spanned 10:22am to 1:02pm PT with several returns. Eight cards were seen in more than one visit.
- Grades were given in a separate round after the feed, on compact summaries that did not show the card.

Grades: 6 amazing, 17 fine, 3 no. In the feed he liked 14 cards and marked 2 "would share". He opened details on 4.

## 2. Findings

1. **Like tracked the later grade.** Liked: 5 of 6 amazing, 9 of 17 fine, 0 of 3 no.
2. **Both shares went to round-up cards**, the only two round-ups in the feed (the four MLB Division Series; NFL divisions whose favorite changed). Two cards is a lead, not a rate.
3. **Reading time did not track interest.** It rose with card length (rank correlation 0.44 with character count) and fell with grade (minus 0.64). Median reading time: amazing 4 seconds, fine 13, no 22. The amazing cards were the short ones.
4. **My reading-time measurement was also faulty.** Three cards recorded zero seconds despite being seen, two of them liked. Cause: time went only to the on-screen card showing the most pixels, which starves a short card beside a tall one on a tall window. Separately, returns to the page inflated early cards (72 and 80 seconds). Reading time from this run should not be used.
5. **Opening details looked like doubt as much as interest.** The four opens were on cards 8, 9, 10 and 11. Card 11 was graded "no" and has a confusing headline. Card 10 carries the Taylor Swift row in finding 8.
6. **Repeated questions hurt.** Six questions appeared on more than one card (one on three). Of the 7 cards carrying a row already seen earlier in the feed, none was graded amazing; 6 of the 19 others were. Alex raised this unprompted.
7. **Grades in this run are not comparable with earlier slates.** Movers went from 7 of 7 amazing to 0 of 7; checklists from 1 of 4 to 3 of 3. Alex's explanation: a second look is less interesting, and the grading list did not show the cards. In-feed likes by type: swings 3 of 3, round-ups 2 of 2, movers 4 of 7, checklists 2 of 3, boards 1 of 4. Confounded with the grading method: this run's movers were headed "Moves", not "Biggest moves", and several repeated rows.
8. **A truth failure reached a card.** Card 10 showed "Taylor Swift wears a Dior wedding dress, 72%, up 7 since yesterday". News reports say she married on about July 4, 2026 in a Dior dress. Kalshi's question (`KXSWIFTWEDDING-26DEC31`, Dior) was open at 10:02am PT at 71.5% with about $72,000 traded; it resolves if she is "documented wearing" a Dior dress at her first wedding ceremony. Why it is still open at that price is not verified. The card's sentence had no date and read as a future event. The independent checker noted the missing date and passed it. No step in the pipeline asks whether the event has already happened.

## 3. Alex's observations (his words, summarised)

1. Several markets appeared in multiple cards, which hurts likeability and shareability.
2. Why is there a live Taylor Swift wedding dress market when she married in July?
3. Rating after already seeing the cards biased ratings down, and the rating screen did not show the material.
4. Some cards might benefit from images.
5. He would click into cards more if the futures and props landing pages were not so broken. When he does click, he sees sparse charts with no interesting trend, no text context and clip-art-looking images. That trains a reader not to click.

## 4. What I take from it

- **Explicit, cheap reactions beat reading time** on this evidence. A like button was used on over half the cards. That is one person who was asked to use it.
- **Tap-through is not a clean interest signal.** I previously called it probably the strongest. It can mean doubt, and Alex's fifth point says weak destination pages suppress it. A ranking signal built on taps would partly measure destination quality.
- **A question should appear once per feed.** My cap of three per slate is wrong for a feed.
- **Round-ups are the best new lead**: both were liked and shared, and the MLB one was graded amazing.
- **The pipeline needs an "already happened" gate** that uses current information. My checkers run without network by design, so they cannot catch this class.
- **Do not grade in a separate round.** Use in-feed reactions.

## 5. Where this maps in GitHub (no new issues proposed)

| Point | Existing issue |
|---|---|
| Like, share, reading time, taps as signals | #5105, #2299 |
| One question per feed; repetition | #10356 |
| Round-up cards | #10346, #9237 stage 2 |
| Destination pages sparse, no context | #883 (futures detail redesign), #1763, #2605 |
| Images | #882, #9238, #3050 |
| Stale or already-decided questions on cards | #10353 evidence contract; "settled means settled" |

Mapped by title only: #883, #1763, #2605, #882, #9238, #3050.

## 6. Limits

One person, 26 cards, one run, a computer window, a prototype page, venue prices. Nothing here measures readers or the product.

Sources for finding 8: Irish Times, 4 July 2026, https://www.irishtimes.com/world/us/2026/07/04/taylor-swift-marries-travis-kelce-in-dress-designed-by-derrys-jonathan-anderson/ ; ABC7, https://abc7.com/post/taylor-swift-weds-travis-kelce-christian-dior-wedding-dress/19444387/ . Search results only; the articles were not opened.
