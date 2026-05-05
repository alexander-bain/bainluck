# Bain Luck

[![CI](https://github.com/alexander-bain/bainluck/actions/workflows/ci.yml/badge.svg)](https://github.com/alexander-bain/bainluck/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

**The most engaging way to explore what the world thinks will happen.**

Bain Luck translates prediction markets and betting odds into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130". Started with sports odds, now covers economics, politics, tech, culture, weather, and more.

**[Live Site](https://bainluck.com)** · **[Discover Feed](https://bainluck.com/discover)** · **[API Docs](https://api.bainluck.com/docs)**

---

## Features

- **Probability-first event pages** — Multi-source win probability charts, market maps, player props, championship path
- **Discover feed** — Social prediction market feed with Higher/Lower guess games, images, LLM context hooks
- **Cross-source aggregation** — Combine odds from 12+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models
- **Championship grids** — Visual probability grids for NBA, NHL, MLB, NFL, Golf
- **Multi-platform** — Web (Next.js), iOS, macOS (shared SwiftUI codebase), Apple Watch prototype
- **Real-time updates** — Live game odds with 32-second polling, ESPN win probability, score tracking
- **Weather & Economics** — Polymarket + Kalshi markets for temperature, rain, oil prices, S&P 500
- **3,350+ tests** — Comprehensive backend test suite

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+) | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS | SwiftUI (shared codebase) | TestFlight |
| watchOS | SwiftUI (prototype) | Direct install |

**Data Sources:** The Odds API, Kalshi, Polymarket, ESPN, StatPal, DataGolf, MLB Stats API

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL
- Redis (for background jobs)
- Node.js 18+ (for frontend)

### Backend

```bash
git clone https://github.com/alexander-bain/bainluck.git
cd bainluck/backend

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example .env
# Edit .env with your API keys

alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
python3 -m pytest tests/test_startup.py -v    # Smoke test (<1s)
python3 -m pytest tests/ -x -q                # Full suite (3,350+ tests)
```

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/              # SQLAlchemy models (26 models)
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients
│   │   ├── tasks/               # Celery tasks (23 modules)
│   │   └── utils/               # Pure logic
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 3,350+ tests
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages)
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
| [Feature Reference](docs/feature-reference.md) | Detailed feature documentation |
| [Design System](docs/design-system.md) | Colors, typography, components |
| [Backlog](docs/backlog.md) | Outstanding work items |
| [Completed Features](docs/completed-features.md) | Shipped features log |
| [Gotchas](docs/gotchas-reference.md) | Known pitfalls and workarounds |

## API

The API is documented at [api.bainluck.com/docs](https://api.bainluck.com/docs) (Swagger UI).

Key endpoints:
- `GET /api/events` — List events with probabilities
- `GET /api/events/{id}` — Event detail with full history
- `GET /api/feed` — Discover feed (events + futures)
- `GET /api/events/typeahead` — Search suggestions
- `GET /api/weather/{type}` — Weather prediction markets

## License

[MIT](LICENSE)
