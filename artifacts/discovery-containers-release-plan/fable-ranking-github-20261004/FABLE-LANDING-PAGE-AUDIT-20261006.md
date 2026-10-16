# Landing pages behind the feed cards: audit

PILLARS: FORMATTING, TRUTH, MATCHING. Prepared by Fable for Alex, Tue 2026-10-06, 2:50pm PT. Evidence for #883. Read-only: I opened public pages and the public data they load. Nothing was changed in the repository, production, GitHub or any lane. Findings and suggestions, not rulings.

## The question

Alex said, after the feed trial: when he taps into a futures or props page he sees a sparse chart with no interesting trend, no text, and clip-art-looking images, and that this trains a reader not to tap. Is that what the live pages show, and why?

## Verdict

Yes on all three, and the first has a specific cause that looks cheap to fix.

1. **Sparse chart.** The first reader to open a page gets a thin chart. The fuller chart data arrives about two minutes later, and the page never asks for it again.
2. **No text.** None of the 21 pages has a sentence saying what the question means, why it moved or how it resolves.
3. **Images.** No page has a picture for the question. The only images are 24-pixel thumbnails beside outcome names.

Three further things turned up that Alex did not ask about: the Taylor Swift wedding dress question is live in the product, some questions have two separate pages, and the one caption under the chart often contradicts the chart.

## What I looked at

21 live futures pages for questions that appeared on my feed trial cards, plus two game props pages by data only. Observed Tue 10/6, 2:13 to 2:37pm PT, in Chrome on Alex's Mac at a desktop window 1,504 pixels wide. For each page I read the rendered page and saved the public data it loads.

Not inspected: the phone-width web layout and the iPhone app. My cloud browser is blocked from www.bainluck.com and the site refuses to be framed, so I could not render it at phone width. One page (the Kalshi Anthropic IPO page) was checked by data only.

## Findings

### 1. The first reader gets a thin chart. Demonstrated defect.

**What fails.** On the first request, 17 of 21 pages answered with thin chart data and a note that a fuller history had been requested. In the one-week view the leading outcome had a median of 28 points, about one every six hours. 13 of 21 pages had fewer than 30. The Rays–Yankees series page had 6 points and a 25-hour gap. Both Comeback Player pages had 25 and 10.

**Why it stays thin.** The page asks for chart data once. I watched one page for 60 seconds after loading and it made no second request. The fuller history was ready 99 to 219 seconds after the first request. On a later request, 12 of the 13 pages that filled went from 6–45 points to between 55 and 279. The thirteenth kept 10 points because its leading outcome had already settled.

**Under what conditions.** Whenever nobody has opened that page recently. I did not measure how long a filled chart stays filled. My requests came in a burst, so a single reader may wait less than two minutes, but still longer than a reader stays.

**Never filled.** 7 of 21 pages did not fill. Three of those already hold hourly data (130 to 143 points). The other four stayed at 10 to 77 points: both Comeback Player pages, Best Actor, and the Kalshi National League page.

**User impact.** A reader who taps a card is very likely the first visitor in a while. He sees a few dots joined by dashes. This matches "super sparse charts".

**Smallest next action (suggestion).** Either have the page ask again while the answer says the fuller history is on its way, or fill the history for questions as they enter Discover, before anyone taps.

Props: the two props pages I checked by data had 6 and 14 points in total for the week, across all outcomes, and no text.

### 2. The movement is in the data, but the page does not show or say it. Design gap.

- The leader moved 10 or more points over the month on 15 of 21 pages, and 15 or more on 11. "Fed holds in October" rose 28 points in a week. The trend exists.
- At a 1,504-pixel window the chart is drawn 730 pixels wide and 140 pixels tall for the full 0 to 100 range. It uses 52% of the width available to it. One point is 1.4 pixels, so the Senate's 3-point week is a 4-pixel wiggle. The fixed 0 to 100 axis is Alex's standing chart rule and I am not proposing to change it. The plot could be larger within that rule.
- The only sentence about movement is "X up N pts from opening", with no date. On 7 of 18 pages with that caption, it points the opposite way from the chart above it. Examples: "Claude up 21.2 pts from opening" under a week in which Claude fell 25.6 points; "Hottest up 29.0 pts from opening" under a month in which it fell 28.8.
- Discover cards already do this better. They say "up 20.3 points since Feb 2" and "down 4 points today".

**Smallest next action (suggestion).** Replace "from opening" with a dated move that matches the range on screen. This depends on the same verified dated baseline that #10626 will provide.

### 3. No text context. Confirmed.

- The description field is empty on 21 of 21 pages. The hook field is empty on 21 of 21, and marked withheld on 17.
- No page says what the question means or how it resolves.
- Some headlines cannot be read without that: "95% November 30" under "GTA VI released?", "53% Hottest", "67% November 30, 2026" under "Anthropic IPO?", "12% Max Martin" under "Who will attend Taylor Swift and Travis Kelce's wedding?".
- What does exist and helps: "Games This Week" on sports pages, a "More in this category" block, the ladder bars on the marijuana page, and honest gap labels such as "No numbers for 25 hours in this stretch".

### 4. Images. Confirmed for the web.

- No picture for the question on any of the 20 pages I rendered.
- Outcome rows show a 24-pixel Wikipedia thumbnail or a grey circle with initials. Best Actor has portraits for most names and initials for Andrew Scott and Robert Pattinson.
- The thumbnails are looked up by bare name. The movie page requested a file named for the 1969 "Dune Messiah" novel cover and one named "Fragment Odyssee". I read the file names only; at 24 pixels I could not confirm what they show.
- 19 of 21 questions carry a stored image that is a generic Pexels stock photo. The web page does not display it. I did not establish where it is shown.
- Web Discover shows small icon tiles on futures cards, not photos.

### 5. The Taylor Swift wedding dress question is live in the product. Demonstrated; severity is Alex's call.

- [Taylor Swift: Wedding Dress](https://www.bainluck.com/futures/52755900) is served as open: Dior 67%, 30 outcomes, "Resolves Dec 30, 2026", findable in search.
- Bain Luck's own [wedding guest page](https://www.bainluck.com/futures/113799) marks 9 of 16 guests as won and settled, "as of Oct 5". The product already holds evidence that the wedding took place.
- The dress page says nothing about that. It reads as a future event.
- Kalshi still lists the question as open. Why is not verified.
- This answers one point the coordinator left open: the question does exist in production. Whether it has appeared in the Discover feed I did not establish.

### 6. The same question has two pages. Demonstrated.

- Three questions I opened each have a Kalshi page and a separate Polymarket page: Senate control, NFL Comeback Player, National League champion. Two more pairs appeared in search and were not opened (American League champion; midterm balance of power).
- All 21 pages list exactly one venue. On these pages the reader is not seeing a blend.
- The pair disagree: Mahomes is 64% on one page and 67% on the other. One National League page says "Milwaukee up 36.0 pts from opening"; its twin says "Milwaukee Brewers down 12.6 pts from opening".
- The two Senate pages carry different resolution dates: Feb 1, 2027 on one and early November 2026 on the other.
- This touches "the blend is the product". Whether it is already tracked is the coordinator's to map.

### 7. Smaller defects. Nonblocking.

- **Venue noise drawn as movement.** On the Last Unbeaten Team page the Chiefs line reads 38.5, 39, 35, 39, 35, 37.5, 43, 37.5, 46.5, 48.5, 47 within 24 minutes. The chart draws that as a zigzag. Alex's chart rule treats ugly movement as a data bug.
- **Resolution date.** Best Actor shows "Resolves Dec 31, 2027". The ceremony is in early 2027 as far as I know; I did not check the date today.
- **Slow first paint.** Twice a page showed no chart 6 to 9 seconds after loading. Observed, not measured.

### 8. What held up

- **Headline numbers are fresh.** Of 20 outcome rows compared against the latest venue observation the site holds, 18 were within 1 point. The largest gap was 3.5 points, on a thinly traded question.
- **Gaps are labelled, not papered over.** Missing stretches are drawn dashed with a plain note.
- **Settled outcomes are marked settled** on the guest page.

## The 21 pages

Points are for the leading outcome in the one-week view. K is Kalshi, P is Polymarket.

| Page | Venue | Points, first visit | Points, after fill | Month move | Caption under the chart |
|---|---|---|---|---|---|
| [Best AI at the end of 2026?](https://www.bainluck.com/futures/109596) | K | 132 | 132 | −12 | Claude up 21.2 pts from opening. |
| [Which party will win the U.S. Senate?](https://www.bainluck.com/futures/108620) | K | 130 | 130 | +17 | Democratic Party up 25.0 pts from opening. |
| [Which party will win the Senate in 2026?](https://www.bainluck.com/futures/112902) | P | 45 | 279 | +13 | Democratic Party up 24.0 pts from opening. |
| [Comeback Player of the Year Winner?](https://www.bainluck.com/futures/15203993) | K | 25 | 25 | +29 | none |
| [AP Comeback Player of the Year Winner](https://www.bainluck.com/futures/56933330) | P | 10 | 10 | +16 | Patrick Mahomes up 35.5 pts from opening. |
| [NFC North Champion](https://www.bainluck.com/futures/2279147) | P | 29 | 269 | +20 | Minnesota Vikings down 11.5 pts from opening. |
| [Who Will Win Series? Rays vs. Yankees](https://www.bainluck.com/futures/63849278) | P | 6 | 246 | +35 | Rays up 34.5 pts from opening. |
| [MLB: 2026 National League Champion](https://www.bainluck.com/futures/199050) | P | 34 | 273 | +17 | Milwaukee Brewers down 12.6 pts from opening. |
| [National League Champion](https://www.bainluck.com/futures/270) | K | 77 | 77 | +18 | Milwaukee up 36.0 pts from opening. |
| [Oscar Winner: Best Actor](https://www.bainluck.com/futures/5869749) | K | 25 | 25 | +20 | none |
| [Which movie has biggest opening week in 2026?](https://www.bainluck.com/futures/11415154) | P | 29 | 267 | +12 | Spider-Man: Brand New Day up 21.5 pts from opening. |
| [Fed decision in Oct 2026?](https://www.bainluck.com/futures/109946) | K | 143 | 143 | +15 | Fed maintains rate up 11.0 pts from opening. |
| [When will Anthropic officially announce an IPO?](https://www.bainluck.com/futures/8430022) | K | 25 | 55 | −6 | not read |
| [Anthropic IPO?](https://www.bainluck.com/futures/30635376) | P | 335 | 337 | −7 | November 30, 2026 down 12.5 pts from opening. |
| [Taylor Swift: Wedding Dress](https://www.bainluck.com/futures/52755900) | K | 25 | 227 | +4 | Dior down 33.2 pts from opening. |
| [Who will attend the Swift–Kelce wedding?](https://www.bainluck.com/futures/113799) | P | 10 | 10 | 0 | Max Martin down 46.6 pts from opening. |
| [Will marijuana be rescheduled?](https://www.bainluck.com/futures/112827) | K | 25 | 101 | +2 | Before 2028 down 16.0 pts from opening. |
| [Where will Waymo operate in 2026?](https://www.bainluck.com/futures/25923984) | K | 24 | 197 | −11 | Denver, CO up 18.0 pts from opening. |
| [GTA VI released?](https://www.bainluck.com/futures/27594646) | P | 30 | 270 | +4 | November 30 up 3.7 pts from opening. |
| [Will 2026 be the hottest year ever?](https://www.bainluck.com/futures/109358) | K | 28 | 268 | −29 | Hottest up 29.0 pts from opening. |
| [Last Unbeaten Team](https://www.bainluck.com/futures/62239632) | P | 10 | 250 | +20 | Kansas City Chiefs up 20.0 pts from opening. |

"Month move" is for the outcome with the highest probability, which on three pages is not the outcome named in the caption.

## Limits

- 21 pages chosen because my feed cards used those questions. Not a random sample of the product.
- One afternoon, one desktop window. Phone web and the iPhone app were not inspected.
- "First visit" means the first request made in this audit. I cannot see whether another reader had opened a page shortly before.
- I describe what the public data and pages show. I did not read the code, so I do not state causes beyond what the responses themselves report.
- No screenshots are in the bundle. The browser tool saved them outside the connected folders. Every page is linked above.

## Evidence

`fable-evidence-20261006-landing/`:

- `raw.tar.gz`: every public response saved, with `_fetchlog.json` (URL, status, size, fetch time for each).
- `observed_pages.json`: the text I read from each rendered page, the chart geometry, and what was not inspected.
- `audit_stats.py` and `audit_stats_output.txt`: the script that prints every number in this file from the bundle alone, and its output.
- `metrics.json`, `pull.py`, `analyze.py`.
- `MANIFEST.json`: SHA-256 hashes, verified after writing.
