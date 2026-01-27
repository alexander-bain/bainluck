# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

OddsTracker converts sports betting odds into win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy 2.0 (async)
- **Task Queue**: Celery + Redis
- **Frontend**: Next.js (planned)
- **iOS**: SwiftUI (planned)

## Project Structure

```
odds-tracker/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── models/          # SQLAlchemy models
│   │   ├── routes/          # API endpoints
│   │   ├── services/        # Business logic, external APIs
│   │   └── utils/           # Helpers (odds_math.py)
│   ├── alembic/             # Database migrations
│   └── requirements.txt
├── docs/PRD.md              # Full product requirements
└── docker-compose.yml       # Local dev environment
```

## Key Files

- `backend/app/utils/odds_math.py` - Odds conversion algorithms
- `backend/app/services/odds_api.py` - The Odds API integration
- `backend/app/models/models.py` - Database schema
- `docs/PRD.md` - Complete product requirements document

## Development Commands

```bash
# Start local environment
docker-compose up -d

# Run API locally (without Docker)
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Database migrations
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run tests
pytest
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:
- `ODDS_API_KEY` - From the-odds-api.com
- `DATABASE_URL` - PostgreSQL connection string

## API Design Principles

1. All probabilities returned as decimals (0.0-1.0)
2. Timestamps in ISO 8601 format with timezone
3. Use descriptive error messages
4. Paginate list endpoints

## Current Status

### Completed
- [x] Project structure
- [x] Database models
- [x] Odds conversion utilities
- [x] The Odds API integration
- [x] Basic API endpoints

### Next Steps
1. Create initial Alembic migration
2. Add background job for polling odds
3. Build basic web UI
4. Add authentication (Firebase)

## Code Style

- Use type hints everywhere
- Format with Black
- Lint with Ruff
- Write docstrings for public functions

## Testing

Tests go in `backend/tests/`. Run with:
```bash
pytest backend/tests/ -v
```
