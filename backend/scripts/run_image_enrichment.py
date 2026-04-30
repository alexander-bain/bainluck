#!/usr/bin/env python3
"""One-shot script to populate market images from Pexels."""
import asyncio
from app.tasks.enrich_markets import enrich_market_images
print(asyncio.run(enrich_market_images(limit=100)))
