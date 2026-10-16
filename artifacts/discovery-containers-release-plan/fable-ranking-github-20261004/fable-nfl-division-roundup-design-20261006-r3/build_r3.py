# Revision 3 of the round-up card reference. Patches the revision 2 page and
# companion file; does not regenerate the card rules or the prototype images.
# Inputs (unchanged from R2): r2_page.html, r2.md, examples.json, roundup-card-fixture.json
import json, html, re

page = open('r2_page.html').read()
md = open('r2.md').read()
EX = {c['cid']: c for c in json.load(open('examples.json'))}

def rep(text, old, new, count=1):
    assert text.count(old) == count, (text.count(old), old[:70])
    return text.replace(old, new)

def cut(text, a, b, new):
    i = text.index(a); j = text.index(b, i); return text[:i] + new + text[j:]

# ---------- contrast, computed here so the number quoted is this script's own
def lum(hexv):
    v = [int(hexv[i:i+2], 16) / 255 for i in (1, 3, 5)]
    v = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
def contrast(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)
C_TAG = contrast('#4B5563', '#F0F0F2'); C_SEC = contrast('#6B7280', '#F0F0F2'); C_AGE = contrast('#9CA3AF', '#FFFFFF')
print('contrast tag ink #4B5563 on #F0F0F2: %.2f' % C_TAG)
print('contrast --text-secondary #6B7280 on #F0F0F2: %.2f' % C_SEC)
print('contrast age mark #9CA3AF on #FFFFFF: %.2f' % C_AGE)

# ---------- the product's age wording, transcribed from frontend/lib/sourceAge.ts
def age_words(seconds):
    mins = seconds // 60; hours = seconds // 3600; days = seconds // 86400
    if mins < 1: return 'just now'
    if mins < 60: return f'{mins}m ago'
    if hours < 24: return f'{hours}h ago'
    if days == 1: return 'yesterday'
    return f'{days}d ago'
FUTURES_OLD_AFTER_S = 6 * 3600
def is_old(seconds): return seconds > FUTURES_OLD_AFTER_S

from datetime import datetime, timezone
def ts(s): return int(datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
NOW = '2026-10-06T21:41:00Z'
AGE_CASES = {
 'old':   ['2026-10-06T13:55:00Z', '2026-10-06T14:10:00Z', '2026-10-06T14:20:00Z', '2026-10-06T14:38:00Z'],
 'mixed': ['2026-10-06T21:30:00Z', '2026-10-06T21:31:00Z', '2026-10-05T15:00:00Z', '2026-10-06T21:33:00Z'],
 'edge':  ['2026-10-06T15:41:00Z', '2026-10-06T21:30:00Z', '2026-10-06T21:30:00Z', '2026-10-06T21:30:00Z'],
}
def resolve(stamps):
    ages = [ts(NOW) - ts(s) for s in stamps]
    old = [is_old(a) for a in ages]
    if all(old): return dict(card=age_words(max(ages)), rows=[None] * len(ages))
    return dict(card=None, rows=[age_words(a) if o else None for a, o in zip(ages, old)])
RES = {k: resolve(v) for k, v in AGE_CASES.items()}
for k, v in RES.items(): print('age case', k, v)
assert RES['old'] == dict(card='7h ago', rows=[None] * 4)
assert RES['mixed'] == dict(card=None, rows=[None, None, 'yesterday', None])
assert RES['edge'] == dict(card=None, rows=[None] * 4)   # exactly six hours: no mark

def mark(words): return f'<span class="age"><i></i><span>{words}</span></span>'
def card(c, src, row_marks=None, card_mark=None):
    rows = ''
    for k, r in enumerate(c['rows']):
        m = row_marks[k] if row_marks else None
        label = html.escape(r['text'])
        t = f'<div class="t tl"><span>{label}</span>{mark(m)}</div>' if m else f'<div class="t">{label}</div>'
        rows += f'<div class="row"><div class="n num ">{r["num"]}<small>%</small></div>{t}<div class="meter" title="{label}: {r["num"]}%"><i style="width: {r["num"]}%;"></i></div></div>'
    tag = f'<span class="tag">{c["tag"]}</span>' if c.get('tag') else ''
    foot = f'<div class="src fl"><span>{src}</span>{mark(card_mark)}</div>' if card_mark else f'<div class="src">{src}</div>'
    return f'<article class="card"><div class="khead"><span class="kicker">Round-up</span>{tag}</div><h2 class="headline">{html.escape(c["headline"])}</h2><div class="rows">{rows}</div>{foot}</article>'
F8 = 'Bain Luck blend · the 4 closest of 8 divisions'
F3 = 'Bain Luck blend · 3 of 8 divisions'
FP = 'Bain Luck blend · the 4 closest of 6 covered divisions'
STATES = {
 'all8':    ('canonical', F8, None, None),
 'three3':  ('three', F3, None, None),
 'partial': ('canonical', FP, None, None),
 'old':     ('canonical', F8, None, RES['old']['card']),
 'mixed':   ('canonical', F8, RES['mixed']['rows'], None),
}
def spec(state, w=358):
    cid, src, rm, cm = STATES[state]
    return f'<div class="sp sp-light" data-state="{state}" style="--w:{w}px"><div class="slot">{card(EX[cid], src, rm, cm)}</div></div>'

# ---------- page: styles for the age mark (the product's existing mark, redrawn)
AGE_CSS = '''
/* the product's existing age mark (PriceAgeMark): a 5px dot and a 10px age, in the product's muted ink */
.sp .age{display:inline-flex;align-items:center;gap:4px;color:#9CA3AF;flex-shrink:0}
.sp .age i{display:block;width:5px;height:5px;border-radius:999px;background:rgba(156,163,175,.6)}
.sp .age span{font-size:10px;line-height:1;white-space:nowrap}
.sp .row .t.tl{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sp .row .t.tl>span:first-child{min-width:0}
.sp .src.fl{display:flex;justify-content:space-between;align-items:center;gap:10px}
.sp .src.fl>span:first-child{min-width:0}'''
anchor = '.sp .row .n small{font-size:.6em;font-weight:500;color:var(--ink3);letter-spacing:0;margin-left:1px}\n'
page = rep(page, anchor, anchor.rstrip('\n') + AGE_CSS + '\n')

page = rep(page, 'Fable for Alex · Tue Oct 6, 2026 · Card rules', 'Fable for Alex · Tue Oct 6, 2026 · Revision 3, 10:20pm PT · Card rules')

page = rep(page, '<li><b>Tapping the card opens a container.</b> The container shows an event card for each item in it. Rows are not separate links.</li>',
 '<li><b>Tapping the card opens a container.</b> The container shows a card for each item in it. Rows are not separate links.</li>'
 '<li><b>The container holds only what the card showed.</b> The same divisions, in the same order. It is the container this card opened, not the canonical one for NFL divisions. Containers will be made in large numbers and are not precious. The other divisions could later appear in a "related" section; that is not part of this slice.</li>')
page = rep(page, 'A tap opens the NFL divisions container.', 'A tap opens the container made for this card.')
page = rep(page, 'Product colors were read from <code>frontend/app/globals.css</code> in the main checkout on Oct 6 and should be confirmed against the release branch.',
 f'The coordinator reports confirming this mapping against release <code>master</code> at <code>6c77da6e</code> on Oct 6; Fable read the main checkout and did not confirm that revision itself. The tag ink has no product name. It is {C_TAG:.2f}:1 on the tag fill, against {C_SEC:.2f}:1 for <code>--text-secondary</code>. The coordinator recommends adding a name for it, <code>--text-secondary-strong</code>; that is not yet decided and nothing has been added.')

FOOT = f'''<h2>The footer line in the product</h2>
<p>The selection rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and the card must say so. The footer is the place for it. It uses the footer style above, unchanged, on one line.</p>
<div class="duo">
<figure class="fig">{spec('all8')}<figcaption>All eight divisions qualify. Wording accepted by Alex for now.</figcaption></figure>
<figure class="fig">{spec('three3')}<figcaption>Only three qualify. Wording accepted by Alex for now. Below three, no card is shown and the feed is unchanged.</figcaption></figure>
</div>
<div class="duo">
<figure class="fig">{spec('partial')}<figcaption><b>Proposed, not ruled.</b> Four to seven qualify. "Of 8" would claim a comparison that was not made, so the count is the number compared.</figcaption></figure>
</div>
<p>The headline stays "NFL division front-runners". It does not say "tightest", so it remains true when some divisions cannot be evaluated.</p>

<h2>When a number is old</h2>
<p>This replaces the old-numbers example in revision 2, which used the wrong trigger and wrong words. The card uses the product's existing age mark and rule, unchanged:</p>
<ul>
<li><b>Old means more than six hours</b> for these season-long questions. At exactly six hours, or with no usable time, there is no mark. A missing time is not shown as fresh; it is simply not marked.</li>
<li><b>The words are the product's:</b> <code>7h ago</code>, <code>yesterday</code>, <code>2d ago</code>. Hovering, and screen readers, get "Last number:" and the exact time.</li>
<li><b>The mark is the product's:</b> a 5px dot and a 10px age in the muted grey <code>#9CA3AF</code>.</li>
<li><b>A blended row is as old as its oldest contributing price.</b> A fresh price from one source does not hide an old one from another.</li>
</ul>
<div class="duo">
<figure class="fig">{spec('old')}<figcaption>Every row is old. One mark, at the right end of the footer, showing the oldest row's age. Rows carry no mark. The card height does not change.</figcaption></figure>
<figure class="fig">{spec('mixed')}<figcaption>One row is old. The mark sits on that row, at the right end of its label line. The footer carries no mark. Row height does not change.</figcaption></figure>
</div>
<p>The placements are Fable's proposal; the rule and wording are the product's. The product's grey is {C_AGE:.2f}:1 on white at 10px, which is faint. It is kept so the mark looks the same everywhere in the product; changing it is a product-wide question, not one for this card.</p>
'''
page = cut(page, '<h2>The footer line in the product</h2>', '<h3>Loading and errors</h3>', FOOT)

FIX = f'''<h3>Age cases</h3>
<p>For the two old-number examples, use the canonical rows with these times. "Now" is fixed at {NOW}.</p>
<pre>{html.escape(json.dumps(dict(now=NOW, old_after_hours=6, cases=[dict(id=k, observed_at=AGE_CASES[k], card_mark=RES[k]['card'], row_marks=RES[k]['rows']) for k in ('old', 'mixed', 'edge')]), indent=1))}</pre>
<p>The third case sits exactly at six hours and must show no mark.</p>

<h2>How a build is checked</h2>'''
page = rep(page, '<h2>How a build is checked</h2>', FIX)
page = rep(page, '<li>Place each image beside the matching reference image from this bundle.</li>',
 '<li>Place each image beside the matching reference image from this bundle. The product-footer and old-number states have their own images, named <code>r3_&lt;state&gt;_light_&lt;width&gt;.png</code>.</li>')
open('roundup-card-reference.html', 'w').write(page)
open('roundup-card-reference-standalone.html', 'w').write('<!doctype html><html lang="en"><head><meta charset="utf8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>' + page + '</body></html>')

# a bare render page for the new reference images
bare = '<!doctype html><html><head><meta charset="utf8"><style>body{margin:0;background:#F5F5F7}' + page[page.index('<style>') + 7:page.index('</style>')] + '.sp{border:0;border-radius:0}</style></head><body>' + ''.join(spec(s, w) for s in STATES for w in (340, 358, 448)) + '</body></html>'
open('r3_render.html', 'w').write(bare)

# ---------- fixture
fx = json.load(open('roundup-card-fixture.json'))
json.dump(dict(cards=fx, footers=dict(all_eight=F8, three=F3, four_to_seven_proposed=FP),
               age=dict(now=NOW, old_after_hours=6, applies_to='canonical', cases=[dict(id=k, observed_at=AGE_CASES[k], card_mark=RES[k]['card'], row_marks=RES[k]['rows']) for k in ('old', 'mixed', 'edge')])),
          open('roundup-card-fixture-r3.json', 'w'), indent=1)

# ---------- companion file
md = rep(md, "revised 9:35pm and 10:00pm PT after the coordinator's replies and Alex's rulings.", "revised 9:35pm, 10:00pm and 10:20pm PT after the coordinator's replies and Alex's rulings.")
md = rep(md, "This is revision 2. It supersedes `FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006.md`, `FABLE-ROUNDUP-CARD-DESIGN-REFERENCE-20261006.md` and their folders. The card images and fixture data are unchanged from those.",
 "This is revision 3. It supersedes revision 2 (`FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006-R2.md` and its folder) and the two earlier versions. The 24 prototype card images and the four fixture cards are unchanged.\n\n**What changed from revision 2:** the old-numbers state now uses the product's own rule, words and mark (revision 2 had the wrong trigger and wrong words); a mixed-age state is added; a footer for four to seven qualifying divisions is proposed; Alex's ruling on what the container holds is recorded; the color check against the release branch is recorded; 15 new reference images cover the product footers and old-number states.")
md = rep(md, 'fable-nfl-division-roundup-design-20261006-r2/roundup-card-reference-standalone.html', 'fable-nfl-division-roundup-design-20261006-r3/roundup-card-reference-standalone.html')
md = rep(md, '- **Tapping the card opens a container.** The container shows an event card for each item in it. Rows are not separate links.',
 '- **Tapping the card opens a container.** The container shows a card for each item in it. Rows are not separate links.\n- **The container holds only what the card showed.** The same divisions, in the same order. It is the container this card opened, not the canonical one for NFL divisions. Containers will be made in large numbers and are not precious. The other divisions could later appear in a "related" section; that is not part of this slice.')
md = rep(md, 'A tap opens the NFL divisions container.', 'A tap opens the container made for this card.')
md = rep(md, 'Product colors were read from `frontend/app/globals.css` in the main checkout on Oct 6 and should be confirmed against the release branch.',
 f'The coordinator reports confirming this mapping against release `master` at `6c77da6e` on Oct 6; Fable read the main checkout and did not confirm that revision itself. The tag ink has no product name. It is {C_TAG:.2f}:1 on the tag fill, against {C_SEC:.2f}:1 for `--text-secondary`. The coordinator recommends adding a name for it, `--text-secondary-strong`; that is not yet decided and nothing has been added.')
FOOT_MD = f'''## The footer line in the product

The selection rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and the card must disclose coverage and ordering. The footer carries it, in the footer style above, on one line.

- All eight qualify: `{F8}`. Accepted by Alex for now.
- Only three qualify: `{F3}`, with three rows. Accepted by Alex for now.
- Four to seven qualify: `{FP}` (the count is the number compared). **Proposed, not ruled.** "Of 8" would claim a comparison that was not made.
- Fewer than three: no card, and the feed is unchanged.

All three fit on one line at 340 wide and leave the card height unchanged (see `r3_measure.json`). The headline stays "NFL division front-runners" and does not say "tightest".

## When a number is old

This replaces the old-numbers example in revision 2. The card uses the product's existing age mark and rule (`PriceAgeMark`, `lib/sourceAge`), unchanged. Fable read both files in the main checkout on Oct 6; they agree with the coordinator's description.

- Old means more than six hours for these season-long questions (the "futures" setting). At exactly six hours, or with no usable time, there is no mark. A missing time is not shown as fresh; it is simply not marked.
- The words are the product's: `7h ago`, `yesterday`, `2d ago`. The tooltip and screen-reader text is "Last number:" and the exact time.
- The mark is the product's: a 5px dot and a 10px age, in the muted grey `#9CA3AF`, 4 apart.
- A blended row is as old as its oldest contributing price. This is the coordinator's requirement and Fable agrees with it.

Two states:

- **Every row is old:** one mark at the right end of the footer line, showing the oldest row's age. Rows carry no mark. Card height unchanged.
- **Some rows are old:** the mark sits on each old row, at the right end of its label line. The footer carries no mark. Row height unchanged.

The two placements are Fable's proposal; the rule and wording are the product's. The product's grey is {C_AGE:.2f}:1 on white at 10px, which is faint. It is kept so the mark looks the same everywhere; changing it is a product-wide question.

**Loading and errors** come from the feed, not the card: the existing loading placeholders, the existing feed-unavailable notice, and the last good cards kept on screen with a retry note.

'''
md = cut(md, '## The footer line in the product', '## Buttons and Details in the prototype', FOOT_MD)
md = rep(md, 'kept as fixed test content. The long and extremes cases are layout tests, not proposed cards.',
 f'kept as fixed test content. The long and extremes cases are layout tests, not proposed cards.\n\n`roundup-card-fixture-r3.json` adds the three footer lines and three age cases for the canonical card, with "now" fixed at {NOW}: `old` (all four rows 7 to 8 hours old; footer mark `7h ago`), `mixed` (one row a day old; that row marked `yesterday`), and `edge` (one row at exactly six hours; no mark).')
md = rep(md, '2. Place each image beside the matching reference image in `reference-images/` (named `proto_<case>_<theme>_<width>.png`, 2x).',
 '2. Place each image beside the matching reference image in `reference-images/` (named `proto_<case>_<theme>_<width>.png`, 2x). The product footers and old-number states are in `reference-images-r3/` (named `r3_<state>_light_<width>.png`, 2x; states `all8`, `three3`, `partial`, `old`, `mixed`).')
md = rep(md, '- The container a tap opens. Alex ruled that tapping the card opens a container showing an event card for each item. Its contents and layout are not designed here.',
 '- The container\'s layout, and the card it shows for each division. Alex said "an event card for each item". The coordinator reports that a division is a season-long question, so the product\'s familiar card for it is the futures card, not the game card. Which card is used is Alex\'s call and is not designed here. The coordinator also reports that container cards read one venue today, so they must be given the same blended number as the round-up.')
md = rep(md, '- The age rule that decides when numbers count as old. The product\'s existing rule applies.',
 '- Wording when four to seven divisions qualify, until Alex rules on the proposal above.\n- A name for the tag ink in the product\'s color set.')
md = cut(md, '## Files', '\x00', '') if False else md
i = md.index('## Files')
md = md[:i] + '''## Files

In `fable-nfl-division-roundup-design-20261006-r3/`: everything from revision 2 unchanged except `roundup-card-reference-standalone.html` (rebuilt), plus `build_r3.py`, `build_r3_output.txt`, `r3_shots.py`, `r3_measure.json`, `r3_render.html`, `r2_page.html` and `r2.md` (the inputs), `roundup-card-fixture-r3.json`, `reference-images-r3/` (15 images), and a new `MANIFEST.json`.
'''
assert 'last number 2 hours ago' not in md and 'last number 2 hours ago' not in page
open('FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006-R3.md', 'w').write(md)
print('page bytes', len(page), 'md bytes', len(md))
