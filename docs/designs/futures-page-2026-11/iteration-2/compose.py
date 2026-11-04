"""Join unaltered browser captures: event left, futures right, same viewport."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 14)
cases = ['duel', 'field', 'ladder', 'participation', 'one-leg', 'settled-today', 'one-leg-open', 'one-leg-settled']
for width, height in [(390, 1400), (1280, 1200)]:
    for slug in cases:
        live = slug in ['duel', 'field', 'ladder', 'participation', 'one-leg-open']
        reference = 'live-event-15341108' if live else 'event-15341089'
        event = Image.open(root / 'raw' / f'{reference}-{width}.jpg').convert('RGB')
        assert event.size == (width, height), event.size
        future = Image.open(root / 'raw' / f'{slug}-{width}.jpg').convert('RGB')
        assert future.size == event.size, (slug, future.size)
        pair = Image.new('RGB', (width * 2 + 2, height + 36), 'white')
        pair.paste(event, (0, 36))
        pair.paste(future, (width + 2, 36))
        draw = ImageDraw.Draw(pair)
        draw.rectangle((width, 0, width + 1, height + 35), fill='#e5e7eb')
        event_name = 'UNLV / N. Arizona' if live else 'Canucks / Ducks'
        draw.text((10, 10), f'EVENT · {event_name} · {width}px', font=font, fill='#111827')
        draw.text((width + 12, 10), f'FUTURES · {slug} · {width}px', font=font, fill='#111827')
        pair.save(root / f'{slug}-{width}.png', optimize=True)

# An overview only; the full-size pairs above preserve every screenshot pixel.
thumb_width = 390
thumb_height = round(1436 * thumb_width / 782)
overview = Image.new('RGB', (thumb_width * 3, thumb_height * 2), 'white')
for i, slug in enumerate(cases[:6]):
    thumb = Image.open(root / f'{slug}-390.png').resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
    overview.paste(thumb, ((i % 3) * thumb_width, (i // 3) * thumb_height))
overview.save(root / 'overview-390.png', optimize=True)
print(f'Created {len(cases) * 2} full-resolution pairs and one overview.')
