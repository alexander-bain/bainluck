#!/usr/bin/env python3
"""crop.py <in.png> <out-prefix> <slice_height> [start] [end] — slice a tall shot into readable bands."""
import sys
from PIL import Image
src, prefix = sys.argv[1], sys.argv[2]
h = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
im = Image.open(src)
W, H = im.size
start = int(sys.argv[4]) if len(sys.argv) > 4 else 0
end = int(sys.argv[5]) if len(sys.argv) > 5 else H
i = 0
y = start
while y < end:
    box = (0, y, W, min(y + h, end))
    im.crop(box).save(f"{prefix}-{i:02d}.png")
    print(f"{prefix}-{i:02d}.png  y={y}..{min(y+h,end)}")
    y += h
    i += 1
print(f"source {W}x{H}")
