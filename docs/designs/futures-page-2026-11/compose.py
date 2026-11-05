"""Mechanical screenshot comparison only; no UI is drawn or reconstructed."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import argparse
p=Path(__file__).parent
font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
font=ImageFont.truetype(font_path,14)
small=ImageFont.truetype(font_path,11)
refs={'duel':('duel','NBA in-game capture'), 'field':('field','Oscars before awards'), 'ladder':('weather','New York before the day'), 'participation':('qualification','Lacrosse qualification · no trades'), 'one-leg':('economics','Unity Bancorp earnings · reported'), 'settled':('nba','NBA final result')}
parser=argparse.ArgumentParser();parser.add_argument('--local',action='store_true');args=parser.parse_args()
suffix='-local' if args.local else ''
for key,(ref,label) in refs.items():
    canvas=Image.new('RGB',(828,1848),'#ffffff');d=ImageDraw.Draw(canvas)
    d.text((20,15),key.replace('-',' ').title()+' · atlas family comparison',font=font,fill='#111827')
    d.text((20,43),'ATLAS · '+label,font=small,fill='#4b5563')
    d.text((428,43),'FUTURES · '+('local' if args.local else 'Vercel preview')+' · 390 px',font=small,fill='#4b5563')
    for row,state in enumerate(['phone','body']):
        y=72+row*885
        source=Image.open(p/'screenshots/raw'/f'atlas-{ref}-{state}.jpg').convert('RGB')
        # Remove only the atlas runtime's status/home chrome. App pixels stay intact.
        source=source.crop((0,54,source.width,source.height-30))
        source=source.resize((390,round(source.height*390/source.width)),Image.Resampling.LANCZOS)
        target=Image.open(p/'screenshots/raw'/f'{key}-{state}{suffix}.jpg').convert('RGB')
        canvas.paste(source,(20,y));canvas.paste(target,(428,y))
        d.rectangle((19,y-1,410,y+845),outline='#e5e7eb');d.rectangle((427,y-1,818,y+845),outline='#e5e7eb')
        d.text((20,y+852),'Headline + journey' if row==0 else 'Scrolled story / details access',font=small,fill='#6b7280')
    d.text((20,1828),'Real browser captures. Different real payloads; shared grammar. Crops and labels only.',font=small,fill='#6b7280')
    canvas.save(p/'screenshots'/f'{key}-comparison{suffix}.png')
