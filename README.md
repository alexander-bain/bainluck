# Bain Luck

Convert sports betting odds into intuitive win probabilities.

## What is this?

Bain Luck fetches live betting odds and translates them into easy-to-understand percentages. Instead of seeing "-150 / +130", you'll see "60% vs 40%".

**Features:**
- Real-time win probabilities for major sports
- Projected final scores based on betting lines
- Historical odds trending charts
- Game Excitement Index to find the best matchups
- Favorite teams with personalized views
- iOS app with widgets (coming soon)

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL
- Redis (optional, for background jobs)

### Setup

```bash
# Clone the repo
git clone https://github.com/alexander-bain/bainluck.git
cd bainluck

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
cd backend
pip install -r requirements.txt

# Set up environment
cp ../.env.example .env
# Edit .env with your credentials

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

### API Keys Needed

1. **The Odds API**: Get a free key at https://the-odds-api.com/

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application
│   │   ├── models/          # SQLAlchemy models
│   │   ├── routes/          # API endpoints
│   │   ├── services/        # Business logic
│   │   └── utils/           # Helpers (odds math, etc.)
│   ├── alembic/             # Database migrations
│   └── requirements.txt
├── frontend/                # Next.js web app (Phase 2)
├── ios/                     # SwiftUI app (Phase 4)
├── docs/
│   └── PRD.md              # Product requirements
└── .env.example            # Environment template
```

## Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL
- **Frontend**: Next.js (React)
- **iOS**: SwiftUI
- **Auth**: Firebase (Google/Apple sign-in)

## Documentation

- [Product Requirements Document](docs/PRD.md)

## License

MIT
