"""
SQLAlchemy database models.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.database import Base


class Sport(Base):
    """Sports we track (NBA, NFL, etc.)."""
    
    __tablename__ = "sports"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    group: Mapped[Optional[str]] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    teams: Mapped[list["Team"]] = relationship(back_populates="sport")
    events: Mapped[list["Event"]] = relationship(back_populates="sport")


class Team(Base):
    """Teams or players."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    external_id: Mapped[Optional[str]] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(10))
    logo_url: Mapped[Optional[str]] = mapped_column(Text)

    # ESPN enrichment fields
    espn_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(7))  # Hex color e.g. #552583
    secondary_color: Mapped[Optional[str]] = mapped_column(String(7))
    logo_url_small: Mapped[Optional[str]] = mapped_column(String(512))
    logo_url_large: Mapped[Optional[str]] = mapped_column(String(512))
    alternate_names: Mapped[Optional[dict]] = mapped_column(JSONB)  # ["Lakers", "LA Lakers"]
    current_record: Mapped[Optional[str]] = mapped_column(String(20))  # "34-18"
    location: Mapped[Optional[str]] = mapped_column(String(100))  # ESPN "location" field (city/region/school)
    roster_players: Mapped[Optional[dict]] = mapped_column(JSONB)  # ["Jayson Tatum", "Jaylen Brown", ...]

    # Relationships
    sport: Mapped["Sport"] = relationship(back_populates="teams")
    home_events: Mapped[list["Event"]] = relationship(
        back_populates="home_team",
        foreign_keys="Event.home_team_id"
    )
    away_events: Mapped[list["Event"]] = relationship(
        back_populates="away_team",
        foreign_keys="Event.away_team_id"
    )
    favorited_by: Mapped[list["UserFavorite"]] = relationship(
        back_populates="team"
    )


class Event(Base):
    """Individual games/matches."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    home_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))

    # For quick lookups before team records exist
    home_team_name: Mapped[str] = mapped_column(String(200))
    away_team_name: Mapped[str] = mapped_column(String(200))

    commence_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)

    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)

    # Opening odds (set once when first odds received, never updated)
    # Used to detect favorite switches, score swings, etc.
    opening_home_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    opening_away_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    opening_home_spread: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    opening_over_under: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    opening_favorite: Mapped[Optional[str]] = mapped_column(String(10))  # 'home', 'away', 'even'

    # Game Excitement Index (GEI) - computed after game completion
    raw_gei: Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    gei_components: Mapped[Optional[str]] = mapped_column(Text)  # JSON of component scores
    gei_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # LLM metadata enrichment
    llm_gender: Mapped[Optional[str]] = mapped_column(String(20))  # men/women/mixed/unknown
    llm_level: Mapped[Optional[str]] = mapped_column(String(20))  # professional/college/amateur/youth
    llm_league: Mapped[Optional[str]] = mapped_column(String(50))  # NFL/NCAAF/NBA/etc
    llm_importance: Mapped[Optional[str]] = mapped_column(String(30))  # playoff/championship/regular_season

    # Normalized team names for better matching (ESPN, search, etc.)
    home_team_normalized: Mapped[Optional[str]] = mapped_column(String(200))  # Full canonical name
    away_team_normalized: Mapped[Optional[str]] = mapped_column(String(200))
    home_team_alt_names: Mapped[Optional[list]] = mapped_column(JSONB)  # ["Lakers", "LA Lakers", etc.]
    away_team_alt_names: Mapped[Optional[list]] = mapped_column(JSONB)

    # ESPN enrichment
    espn_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("venues.id"))
    broadcast_info: Mapped[Optional[str]] = mapped_column(String(255))  # "ESPN, ESPN+"
    game_clock: Mapped[Optional[str]] = mapped_column(String(20))  # "4:32"
    period: Mapped[Optional[str]] = mapped_column(String(100))  # "Q4", "2nd Half", "OT", or schedule info
    espn_win_prob_home: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))  # ESPN's model
    win_probability_sources: Mapped[Optional[dict]] = mapped_column(JSONB)  # {"espn": 0.65, "betting": 0.60}

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    sport: Mapped["Sport"] = relationship(back_populates="events")
    home_team: Mapped[Optional["Team"]] = relationship(
        back_populates="home_events",
        foreign_keys=[home_team_id]
    )
    away_team: Mapped[Optional["Team"]] = relationship(
        back_populates="away_events",
        foreign_keys=[away_team_id]
    )
    venue: Mapped[Optional["Venue"]] = relationship(back_populates="events")
    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship(
        back_populates="event"
    )
    espn_snapshots: Mapped[list["ESPNSnapshot"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan"
    )


class OddsSnapshot(Base):
    """Raw odds readings (high frequency, pruned after aggregation)."""
    
    __tablename__ = "odds_snapshots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        index=True
    )
    bookmaker: Mapped[str] = mapped_column(String(50))
    
    # Moneyline
    home_moneyline: Mapped[Optional[int]] = mapped_column(Integer)
    away_moneyline: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Spread
    home_spread: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    home_spread_odds: Mapped[Optional[int]] = mapped_column(Integer)
    away_spread_odds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Totals
    over_under: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    over_odds: Mapped[Optional[int]] = mapped_column(Integer)
    under_odds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Calculated fields (denormalized for query speed)
    home_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    away_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    projected_home_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    projected_away_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))

    # Deduplication fields
    # reading_count: how many times we polled and saw this exact same value
    # valid_until: last time we confirmed this value (for charting continuity)
    reading_count: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="odds_snapshots")


class OddsAggregated(Base):
    """Aggregated odds history (permanent storage)."""

    __tablename__ = "odds_aggregated"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    avg_home_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    min_home_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    max_home_win_prob: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    avg_projected_total: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("event_id", "period_start", name="uq_event_period"),
    )


class ESPNSnapshot(Base):
    """ESPN win probability history (captured every 60 seconds during live games)."""

    __tablename__ = "espn_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    # Win probability from ESPN's model
    home_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    away_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Game state at capture time
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    game_clock: Mapped[Optional[str]] = mapped_column(String(20))
    period: Mapped[Optional[str]] = mapped_column(String(100))

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="espn_snapshots")


class WinProbSnapshot(Base):
    """Win probability history from any source (ESPN, statistical model, etc.)."""

    __tablename__ = "win_prob_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30))  # "espn", "stat_model", "moneypuck", etc.
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    # Win probabilities
    home_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    away_win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    draw_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Source-specific game state (clock, period, score, etc.)
    game_state: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Deduplication (same pattern as OddsSnapshot)
    reading_count: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    event: Mapped["Event"] = relationship()


class User(Base):
    """Users (optional auth for personalization)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    firebase_uid: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    photo_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    favorites: Mapped[list["UserFavorite"]] = relationship(
        back_populates="user"
    )
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        back_populates="user", uselist=False
    )
    pins: Mapped[list["UserPin"]] = relationship(
        back_populates="user"
    )


class UserFavorite(Base):
    """User's team relationships (follow, local, alma_mater, rival)."""

    __tablename__ = "user_favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    relation_type: Mapped[str] = mapped_column(String(20), default="follow")  # follow, local, alma_mater, rival
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual, onboarding, inferred
    weight: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "team_id", "relation_type", name="uq_user_team_relation"),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="favorites")
    team: Mapped["Team"] = relationship(back_populates="favorited_by")


class UserPreference(Base):
    """User preferences from onboarding and settings."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    home_location: Mapped[Optional[str]] = mapped_column(String(100))
    sport_affinities: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_raw: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="preferences")


class UserPin(Base):
    """User's pinned events and futures (replaces localStorage for authenticated users)."""

    __tablename__ = "user_pins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pin_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'event' or 'future'
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "pin_type", "target_id", name="uq_user_pin"),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="pins")


class Tournament(Base):
    """Tournaments and championships."""
    
    __tablename__ = "tournaments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")
    
    # Relationships
    odds: Mapped[list["TournamentOdds"]] = relationship(
        back_populates="tournament"
    )


class TournamentOdds(Base):
    """Odds for tournament/championship winners."""

    __tablename__ = "tournament_odds"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    odds: Mapped[Optional[int]] = mapped_column(Integer)
    win_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Relationships
    tournament: Mapped["Tournament"] = relationship(back_populates="odds")


class ScoreSnapshot(Base):
    """Score history snapshots for live score progression tracking."""

    __tablename__ = "score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)

    # Relationships
    event: Mapped["Event"] = relationship()


class GEIPercentile(Base):
    """Percentile thresholds for Game Excitement Index scoring."""

    __tablename__ = "gei_percentiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # 'global', 'basketball_nba', etc.
    percentile: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-100
    raw_gei_threshold: Mapped[float] = mapped_column(Numeric(6, 4))  # Raw GEI value at this percentile
    sample_size: Mapped[int] = mapped_column(Integer)  # Number of events in this scope
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("scope", "percentile", name="uq_scope_percentile"),
    )


class Venue(Base):
    """Venue/arena information from ESPN."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    country: Mapped[Optional[str]] = mapped_column(String(50))
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    espn_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    events: Mapped[list["Event"]] = relationship(back_populates="venue")


class FuturesMarket(Base):
    """A futures market (e.g., 'NBA Championship 2025-26', 'Super Bowl Winner')."""

    __tablename__ = "futures_markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'odds_api', 'kalshi'
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)  # sport_key or event_ticker
    sport_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sports.id"), index=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id"), index=True)  # Game-level market → event link

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="championship")  # championship, mvp, division, prop
    llm_sport_category: Mapped[Optional[str]] = mapped_column(String(50))  # LLM-assigned sport category
    market_tier: Mapped[Optional[int]] = mapped_column(Integer)  # 1=championship, 2=conference, 3=awards, 4=division, 5=props/other

    # LLM metadata enrichment
    llm_gender: Mapped[Optional[str]] = mapped_column(String(20))  # men/women/mixed/unknown
    llm_level: Mapped[Optional[str]] = mapped_column(String(20))  # professional/college/amateur/youth
    llm_league: Mapped[Optional[str]] = mapped_column(String(50))  # NFL/NBA/EPL/etc

    # Cross-source matching key: {sport}:{league}:{category}:{season}
    # e.g., "basketball:NBA:championship:2025-26"
    canonical_market_key: Mapped[Optional[str]] = mapped_column(String(200), index=True)

    # Multi-category tags for cross-category discovery
    # e.g., ["basketball", "nba", "mvp"] or ["politics", "trump", "crypto"]
    category_tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")

    # For multi-outcome markets, whether exactly one outcome can win
    mutually_exclusive: Mapped[bool] = mapped_column(Boolean, default=True)

    # When the event/tournament begins (e.g., when the Masters starts)
    commence_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # When the market resolves (e.g., when the champion is crowned)
    resolution_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open, suspended, resolved

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_futures_source_external"),
    )

    # Relationships
    sport: Mapped[Optional["Sport"]] = relationship()
    event: Mapped[Optional["Event"]] = relationship()
    outcomes: Mapped[list["FuturesOutcome"]] = relationship(
        back_populates="market", cascade="all, delete-orphan"
    )


class FuturesOutcome(Base):
    """A single outcome in a futures market (e.g., 'Los Angeles Lakers')."""

    __tablename__ = "futures_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("futures_markets.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))  # outcome name or ticker

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))

    # Current consensus odds (denormalized for quick display)
    current_probability: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))  # 0.0-1.0
    current_american_odds: Mapped[Optional[int]] = mapped_column(Integer)

    # For Kalshi: store bid/ask spread (nullable for traditional books)
    current_yes_bid: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    current_yes_ask: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Opening odds (for detecting movement)
    opening_probability: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    opening_american_odds: Mapped[Optional[int]] = mapped_column(Integer)
    opening_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Movement tracking
    probability_change_24h: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    rank_change_24h: Mapped[Optional[int]] = mapped_column(Integer)

    # Resolution
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("market_id", "external_id", name="uq_outcome_market_external"),
    )

    # Relationships
    market: Mapped["FuturesMarket"] = relationship(back_populates="outcomes")
    team: Mapped[Optional["Team"]] = relationship()
    snapshots: Mapped[list["FuturesOddsSnapshot"]] = relationship(
        back_populates="outcome", cascade="all, delete-orphan"
    )


class FuturesOddsSnapshot(Base):
    """Historical odds snapshot for a futures outcome from a specific bookmaker."""

    __tablename__ = "futures_odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    outcome_id: Mapped[int] = mapped_column(ForeignKey("futures_outcomes.id"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(50))  # 'draftkings', 'fanduel', 'kalshi'

    # Normalized probability (always calculated)
    probability: Mapped[float] = mapped_column(Numeric(7, 6))

    # Source-specific raw data
    american_odds: Mapped[Optional[int]] = mapped_column(Integer)  # For traditional books
    yes_bid: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))  # For Kalshi
    yes_ask: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))  # For Kalshi
    last_price: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))  # For Kalshi

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Deduplication (same pattern as OddsSnapshot)
    reading_count: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    outcome: Mapped["FuturesOutcome"] = relationship(back_populates="snapshots")
