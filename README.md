# Bain Luck

[![CI](https://github.com/alexander-bain/bainluck/actions/workflows/ci.yml/badge.svg)](https://github.com/alexander-bain/bainluck/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

**Probability, not betting. The world's honest guess about what happens next.**

Bain Luck aggregates prediction markets, sportsbook lines, and statistical models into one blended probability per question. You always see a probability like "60%", never a price like "-150" or "+3000". It started with sports and now covers politics, economics, entertainment, tech, geopolitics, and weather.

**[Live Site](https://bainluck.com)** · **[Discover Feed](https://bainluck.com/discover)** · **[Calibration](https://bainluck.com/calibration)** · **[API Docs](https://api.bainluck.com/docs)**

---

## Why

> At the 2026 Australian Open, Carlos Alcaraz beat Alexander Zverev in a five-set tennis semifinal. So why did his odds run from 98% up two sets to 14%, the brink of elimination, before he won?

That swing (an adductor injury, a near-collapse, a fifth-set comeback) is the story of the match, and it's invisible in the final score. Bain Luck gives every question one honest number and shows you how that number moved.

It isn't just sports. The same probability lines tracked who would stand in Taylor Swift's wedding party ahead of her July 2026 wedding, how many rate cuts the Fed delivers this year, and which movie tops Netflix this week. If the world is guessing about it, there's a number, and the way the number moves is the story.

## What makes it different

- **One number per question.** Sources are blended with fitted-skill weighting into a single probability. When sources disagree, that's a data problem to fix, not a feature to display.
- **Public calibration.** The [calibration page](https://bainluck.com/calibration) shows how often our probabilities were right, across more than a million resolved outcomes, broken out by category. It's the scoreboard we hold ourselves to.
- **No gambling formats.** Prices like -140 or +3000 never appear anywhere. Every number is a probability.
- **Honest charts.** No smoothing and a fixed 0-100 axis. Real movement is the product.

## Features

- **Discover feed**: ranked, story-grouped prediction cards across every category, with Today's Challenge
- **Probability-first event pages**: blended win probability charts, market maps, player props, championship paths
- **Cross-source aggregation**: 12+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models
- **Championship grids**: visual probability grids for NBA, NHL, MLB, NFL, and Golf
- **Multi-platform**: web (Next.js), iOS and macOS (shared SwiftUI), Apple Watch prototype
- **Real-time**: live game updates, ESPN win probability, score tracking
- **Tested**: 9,300+ backend (pytest), 1,000+ frontend (Jest), and 300+ native (XCTest) tests

## Under the hood

- **Stories, not markets.** The feed ranks stories: a golf tournament is one story with forty markets inside it, not forty competing cards. Ranking the story is what keeps a just-ended World Cup above a routine Tuesday slate.
- **Fitted-skill blending.** Source weights aren't hand-picked. They're fitted from each source's measured historical accuracy, per category, and re-fit as the record grows.
- **Calibration as infrastructure.** Every resolved outcome (1.28M and counting) is graded against a registered settlement authority, with provenance tiers and versioned populations, so the public accuracy page can survive a skeptical audit.
- **Eval-gated changes.** A fenced eval workshop turns hard-won definitions (what counts as "stale," what counts as "settled") into versioned fixture corpora that gate CI, and adversarial audit passes review the riskiest shipped diffs.

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+) | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS | SwiftUI (shared codebase) | TestFlight |
| watchOS | SwiftUI (prototype) | Direct install |

**Data Sources:** The Odds API, Kalshi, Polymarket, ESPN, DataGolf, MLB Stats API

## How it's built

This repo is developed by one person orchestrating multiple AI agent lanes running in parallel: a backend lane, a frontend/iOS lane, a read-only production verification lane, and a fenced adversarial audit lane, all coordinated through file-based work queues, with automated sentinels watching production and filing issues. Product judgment stays human. Taste, ranking, and calibration calls are made by the maintainer and recorded as standing rulings in [docs/PRODUCT-BRAIN.md](docs/PRODUCT-BRAIN.md). The GitHub Issues board is the single source of priority.

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/              # SQLAlchemy models
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients
│   │   ├── tasks/               # Celery tasks (incl. sentinels)
│   │   └── utils/               # Pure logic
│   ├── alembic/                 # Database migrations
│   └── tests/                   # Backend test suite
├── frontend/
│   ├── app/                     # Next.js app router
│   ├── components/              # React components
│   └── lib/                     # API client, types
├── ios/Bain Luck/               # iOS + macOS + watchOS (SwiftUI)
├── scripts/                     # Operational scripts
└── docs/                        # Documentation
```

## Documentation

| Doc | Purpose |
|-----|---------|
| [Architecture](docs/architecture-reference.md) | System design, aggregation, resilience |
| [Product Brain](docs/PRODUCT-BRAIN.md) | Standing product rulings and the reasoning behind them |
| [Feature Reference](docs/feature-reference.md) | Detailed feature documentation |
| [Design System](docs/design-system.md) | Colors, typography, components |
| [Completed Features](docs/completed-features.md) | Shipped features log |
| [Gotchas](docs/gotchas-reference.md) | Known pitfalls and workarounds |
| [GitHub Issues](https://github.com/alexander-bain/bainluck/issues) | The single source of priority |

## API

The API is documented at [api.bainluck.com/docs](https://api.bainluck.com/docs) (Swagger UI).

Key endpoints:
- `GET /api/events` lists events with probabilities
- `GET /api/events/{id}` returns event detail with full history
- `GET /api/feed` serves the Discover feed (events + futures)
- `GET /api/events/typeahead` powers search suggestions
- `GET /api/calibration` returns calibration data by category

## License

[MIT](LICENSE)
