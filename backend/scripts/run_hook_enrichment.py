#!/usr/bin/env python3
"""One-shot script to generate LLM hook descriptions for markets."""
import asyncio
from app.tasks.enrich_markets import enrich_market_hooks
print(asyncio.run(enrich_market_hooks(limit=100)))
