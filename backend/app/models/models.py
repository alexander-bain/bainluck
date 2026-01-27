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
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    home_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))
    
    # For quick lookups before team records exist
    home_team_name: Mapped[str] = mapped_column(String(200))
    away_team_name: Mapped[str] = mapped_column(String(200))
    
    commence_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    
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
    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship(
        back_populates="event"
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


class User(Base):
    """Users (optional auth for personalization)."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    firebase_uid: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    
    # Relationships
    favorites: Mapped[list["UserFavorite"]] = relationship(
        back_populates="user"
    )


class UserFavorite(Base):
    """User's favorite teams."""
    
    __tablename__ = "user_favorites"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_user_team"),
    )
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="favorites")
    team: Mapped["Team"] = relationship(back_populates="favorited_by")


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
