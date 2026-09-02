"""
SQLAlchemy database models.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.database import Base

# The one runtime allowlist for `discover_interactions.provenance`, imported
# rather than re-spelled: a second copy of this tuple is how the enum and its
# values drifted apart the first time. `app.utils.discover_provenance` imports
# nothing, so this cannot create a cycle.
from app.utils.discover_provenance import PROVENANCE_VALUES


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
    slug: Mapped[Optional[str]] = mapped_column(String(200), unique=True, index=True)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(20))
    logo_url: Mapped[Optional[str]] = mapped_column(Text)

    # ESPN enrichment fields
    espn_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    primary_color: Mapped[Optional[str]] = mapped_column(
        String(7)
    )  # Hex color e.g. #552583
    secondary_color: Mapped[Optional[str]] = mapped_column(String(7))
    logo_url_small: Mapped[Optional[str]] = mapped_column(String(512))
    logo_url_large: Mapped[Optional[str]] = mapped_column(String(512))
    alternate_names: Mapped[Optional[dict]] = mapped_column(
        JSONB
    )  # ["Lakers", "LA Lakers"]
    current_record: Mapped[Optional[str]] = mapped_column(String(20))  # "34-18"
    location: Mapped[Optional[str]] = mapped_column(
        String(100)
    )  # ESPN "location" field (city/region/school)
    roster_players: Mapped[Optional[dict]] = mapped_column(
        JSONB
    )  # ["Jayson Tatum", "Jaylen Brown", ...]

    # StatPal enrichment
    statpal_team_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    standings_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    standings_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    season_stats: Mapped[Optional[dict]] = mapped_column(JSONB)
    season_stats_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Relationships
    sport: Mapped["Sport"] = relationship(back_populates="teams")
    home_events: Mapped[list["Event"]] = relationship(
        back_populates="home_team", foreign_keys="Event.home_team_id"
    )
    away_events: Mapped[list["Event"]] = relationship(
        back_populates="away_team", foreign_keys="Event.away_team_id"
    )
    favorited_by: Mapped[list["UserFavorite"]] = relationship(back_populates="team")


class Event(Base):
    """Individual games/matches."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
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
    opening_favorite: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # 'home', 'away', 'even'

    # Closing line (last odds before commence_time, pre-computed by backfill)
    closing_home_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    closing_away_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    closing_home_spread: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    closing_home_spread_odds: Mapped[Optional[int]] = mapped_column(Integer)
    closing_away_spread_odds: Mapped[Optional[int]] = mapped_column(Integer)
    closing_over_under: Mapped[Optional[float]] = mapped_column(Numeric(5, 1))
    closing_over_odds: Mapped[Optional[int]] = mapped_column(Integer)
    closing_under_odds: Mapped[Optional[int]] = mapped_column(Integer)

    # Excitement Index (EI) — standard GEI: cumulative probability travel distance
    raw_ei: Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    ei_metadata: Mapped[Optional[str]] = mapped_column(
        Text
    )  # JSON: {raw_ei, lead_changes, comeback_factor}
    ei_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # LLM metadata enrichment
    llm_gender: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # men/women/mixed/unknown
    llm_level: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # professional/college/amateur/youth
    llm_league: Mapped[Optional[str]] = mapped_column(String(50))  # NFL/NCAAF/NBA/etc
    llm_importance: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # playoff/championship/regular_season

    # Normalized team names for better matching (ESPN, search, etc.)
    home_team_normalized: Mapped[Optional[str]] = mapped_column(
        String(200)
    )  # Full canonical name
    away_team_normalized: Mapped[Optional[str]] = mapped_column(String(200))
    home_team_alt_names: Mapped[Optional[list]] = mapped_column(
        JSONB
    )  # ["Lakers", "LA Lakers", etc.]
    away_team_alt_names: Mapped[Optional[list]] = mapped_column(JSONB)

    # ESPN enrichment
    espn_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("venues.id"))
    broadcast_info: Mapped[Optional[str]] = mapped_column(String(255))  # "ESPN, ESPN+"
    game_clock: Mapped[Optional[str]] = mapped_column(String(20))  # "4:32"
    period: Mapped[Optional[str]] = mapped_column(
        String(100)
    )  # "Q4", "2nd Half", "OT", or schedule info
    espn_win_prob_home: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4)
    )  # ESPN's model
    win_probability_sources: Mapped[Optional[dict]] = mapped_column(
        JSONB
    )  # {"espn": 0.65, "betting": 0.60}

    # StatPal enrichment
    statpal_fixture_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    statpal_end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    commence_time_source: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # 'odds_api', 'espn', 'statpal'

    # Authoritative game end time — set when any source confirms the game is over.
    # Sources (in priority): statpal_end_time > ESPN "post"/"final" > Odds API completed > staleness.
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ESPN box score data (populated after game completion)
    box_score_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Taxonomy tags (namespaced, e.g., ["sport:basketball", "tier:1", "signal:upset"])
    event_tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")

    # March Madness / NCAA tournament fields (nullable — only set for tournament games)
    tournament_seed_home: Mapped[Optional[int]] = mapped_column()
    tournament_seed_away: Mapped[Optional[int]] = mapped_column()
    tournament_region: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # "East", "West", "Midwest", "South"
    tournament_round: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # "First Four", "Round of 64", etc.
    tournament_type: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # "mens" or "womens"
    is_tournament_game: Mapped[Optional[bool]] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    sport: Mapped["Sport"] = relationship(back_populates="events")
    home_team: Mapped[Optional["Team"]] = relationship(
        back_populates="home_events", foreign_keys=[home_team_id]
    )
    away_team: Mapped[Optional["Team"]] = relationship(
        back_populates="away_events", foreign_keys=[away_team_id]
    )
    venue: Mapped[Optional["Venue"]] = relationship(back_populates="events")
    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship(back_populates="event")
    espn_snapshots: Mapped[list["ESPNSnapshot"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    scoring_plays: Mapped[list["ScoringPlay"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class ScoringPlay(Base):
    """Individual scoring plays from StatPal/ESPN for live games.

    Persistent, queryable play-by-play history. Used to correlate specific plays
    with odds movements for line-movement explanations ("Tatum three-pointer
    capped a 12-0 run — odds jumped 9%").

    Replaces the ephemeral "last 10 plays" JSONB pattern with full game history.
    """

    __tablename__ = "scoring_plays"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # "statpal" or "espn"

    # Game context
    period: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # "Q1", "1st Half", "Inning 5"
    game_clock: Mapped[Optional[str]] = mapped_column(String(20))  # "4:32", "02:15"

    # Play description
    description: Mapped[str] = mapped_column(Text)
    play_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "field_goal", "turnover"
    team_name: Mapped[Optional[str]] = mapped_column(String(100))
    player_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Score at time of play
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)

    # Timestamps
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationship
    event: Mapped["Event"] = relationship(back_populates="scoring_plays")


class GameMoment(Base):
    """A key in-game moment: a real-world event (score/home run/goal…) joined to a
    win-probability delta, carrying a confidence from the #871 explainability gate.

    THE MOMENTS ENGINE (#1168): an offline, per-event join detects prob deltas in a
    tracked WP series and attaches the nearest causal event within a window. Rows
    are precomputed and stored here (never computed at render); the event-history
    payload surfaces the confident subset as ``moments:[{ts,label,confidence}]``.
    MLB first — its scoring plays plus the MLB Stats API's per-play win probability
    let the join be validated against the source's own attribution.
    """

    __tablename__ = "game_moments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    # Wall-clock time of the moment, for chart placement. Nullable when only
    # game-state (inning/score) is known and no snapshot timestamp matched.
    ts: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )

    # Real-world EVENT stream
    moment_type: Mapped[str] = mapped_column(String(30))  # score/home_run/goal/…
    description: Mapped[str] = mapped_column(Text)
    actor_team: Mapped[Optional[str]] = mapped_column(String(100))
    actor_player: Mapped[Optional[str]] = mapped_column(String(100))
    period: Mapped[Optional[str]] = mapped_column(String(30))  # "Inning 5 (Top)"
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))  # "espn"/"mlb"/"statpal"

    # The JOIN result (#871 gate) — null until a cause attaches; the history payload
    # only surfaces rows above the confidence gate.
    prob_delta: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3))
    label: Mapped[Optional[str]] = mapped_column(String(200))

    # Event-scoped idempotent upsert key — dedups re-runs of the offline join.
    dedupe_key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    event: Mapped["Event"] = relationship()

    __table_args__ = (
        UniqueConstraint("event_id", "dedupe_key", name="uq_game_moment_event_key"),
        Index("ix_game_moments_event_conf", "event_id", "confidence"),
    )


class OddsSnapshot(Base):
    """Raw odds readings (high frequency, pruned after aggregation)."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
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

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_id", "period_start", name="uq_event_period"),
    )


class ESPNSnapshot(Base):
    """ESPN win probability history (captured every 60 seconds during live games)."""

    __tablename__ = "espn_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
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
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(
        String(30)
    )  # "espn", "stat_model", "kalshi", etc.
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Email compliance (CAN-SPAM) — per-type opt-in, all default False
    # Shape: {"digest": false, "bug_updates": false, "market_alerts": false}
    email_preferences: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="{}"
    )
    # Push notification preferences — per-type opt-in, all default True
    # Shape: {"daily_challenge": true, "big_moves": true}
    push_preferences: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="{}"
    )

    # HMAC-signed unsubscribe token — unique per user, generated on first email send
    unsubscribe_token: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True
    )

    # Relationships
    favorites: Mapped[list["UserFavorite"]] = relationship(back_populates="user")
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        back_populates="user", uselist=False
    )
    pins: Mapped[list["UserPin"]] = relationship(back_populates="user")


class UserFavorite(Base):
    """User's team relationships (follow, local, alma_mater, rival)."""

    __tablename__ = "user_favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    relation_type: Mapped[str] = mapped_column(
        String(20), default="follow"
    )  # follow, local, alma_mater, rival
    source: Mapped[str] = mapped_column(
        String(20), default="manual"
    )  # manual, onboarding, inferred
    weight: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id", "team_id", "relation_type", name="uq_user_team_relation"
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="favorites")
    team: Mapped["Team"] = relationship(back_populates="favorited_by")


class UserPreference(Base):
    """User preferences from onboarding and settings."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
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
    pin_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'event' or 'future'
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
    odds: Mapped[list["TournamentOdds"]] = relationship(back_populates="tournament")


class TournamentOdds(Base):
    """Odds for tournament/championship winners."""

    __tablename__ = "tournament_odds"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)

    # Relationships
    event: Mapped["Event"] = relationship()


class EIPercentile(Base):
    """Percentile thresholds for Excitement Index scoring."""

    __tablename__ = "ei_percentiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'global', 'basketball_nba', etc.
    percentile: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-100
    raw_ei_threshold: Mapped[float] = mapped_column(
        Numeric(6, 4)
    )  # Raw EI value at this percentile
    sample_size: Mapped[int] = mapped_column(Integer)  # Number of events in this scope
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'odds_api', 'kalshi'
    external_id: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # sport_key or event_ticker
    sport_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sports.id"), index=True)
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id"), index=True
    )  # Game-level market → event link

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(
        String(50), default="championship"
    )  # championship, mvp, division, prop
    llm_sport_category: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # LLM-assigned sport category
    market_tier: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # 1=championship, 2=conference, 3=awards, 4=division, 5=props/other
    market_type: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # Market SHAPE (Queue #194): claim | quantity | duel | field |
    # container_member | unshaped. Assigned by app.utils.market_shape from
    # outcome structure + names + group membership (backfill_market_shapes task).
    # side_kind + shape metadata live in market_metadata["shape"].

    # LLM metadata enrichment
    llm_gender: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # men/women/mixed/unknown
    llm_level: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # professional/college/amateur/youth
    llm_league: Mapped[Optional[str]] = mapped_column(String(50))  # NFL/NBA/EPL/etc

    # Cross-source matching key: {sport}:{league}:{category}:{season}
    # e.g., "basketball:NBA:championship:2025-26"
    canonical_market_key: Mapped[Optional[str]] = mapped_column(String(200), index=True)

    # Multi-category tags for cross-category discovery
    # e.g., ["basketball", "nba", "mvp"] or ["politics", "trump", "crypto"]
    category_tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")

    # Taxonomy tags (namespaced, e.g., ["sport:basketball", "tier:1", "category:championship"])
    market_tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")

    # Flexible metadata (leaderboard state, round history, source-specific data)
    market_metadata: Mapped[Optional[dict]] = mapped_column(
        "market_metadata", JSONB, nullable=True
    )

    # For multi-outcome markets, whether exactly one outcome can win
    mutually_exclusive: Mapped[bool] = mapped_column(Boolean, default=True)

    # When the event/tournament begins (e.g., when the Masters starts)
    commence_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # When the market resolves (e.g., when the champion is crowned).
    # Kalshi: max(close_time) — when trading actually stops (CAL-P989, #2660).
    resolution_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Kalshi's legal backstop, max(expiration_time) — the LATEST a market could
    # possibly expire, which is what resolution_date used to hold. Kept in its own
    # column so the switch to close_time loses nothing; see
    # app/utils/kalshi_resolution_window.py for why the backstop is the wrong
    # field to render or to run `past resolution_date` predicates against.
    expiration_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="open", index=True
    )  # open, suspended, resolved

    # Cross-source event grouping (e.g., "NBA Championship 2025-26" from multiple sources)
    group_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    group_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # championship, conference, division, award, game, prop
    group_position: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # Display order within group (e.g., by liquidity)

    # Discover feed enrichment
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500)
    )  # Unsplash/Pexels photo URL
    # True pixel size of the raster image_url returns. NOT derivable from the
    # URL: Pexels renders through imgix, so "?h=350" is 350 tall and whatever
    # width the aspect gives (measured live: 450-586px). Written beside
    # image_url and cleared whenever image_url changes — a dimension pair that
    # outlives its photo describes the wrong image. NULL = not measured yet;
    # consumers must fall back to their pre-existing conservative behaviour.
    # Derivation + safety direction: app/utils/image_dimensions.py.
    image_width: Mapped[Optional[int]] = mapped_column(Integer)
    image_height: Mapped[Optional[int]] = mapped_column(Integer)
    hook_description: Mapped[Optional[str]] = mapped_column(
        String(500)
    )  # LLM-generated context blurb
    hook_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    hook_leader_at_generation: Mapped[Optional[str]] = mapped_column(String(200))

    # Precomputed editorial recall flag — set during polling to avoid
    # 44-ILIKE scan on every /api/feed request.
    is_editorial_recall: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false"
    )

    # Curator score adjustment — accumulated from boost/demote signals
    curation_score_adj: Mapped[Optional[int]] = mapped_column(Integer, server_default="0")

    # Volume/liquidity from prediction markets (internal signal, never user-facing).
    # BigInteger: prod ALTER applied 2026-07-06 (#990) — World Cup volume exceeded
    # int32 (2.147B cap). Models synced to match; keep in lockstep with the DB type.
    volume: Mapped[Optional[int]] = mapped_column(
        BigInteger
    )  # Lifetime volume in contracts/dollars
    volume_24h: Mapped[Optional[int]] = mapped_column(BigInteger)  # 24-hour trading volume
    max_movement_24h: Mapped[Optional[float]] = mapped_column(Numeric(7, 4))  # MAX(ABS(outcome.probability_change_24h))
    open_interest: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # Currently open contracts (Kalshi)
    liquidity: Mapped[Optional[float]] = mapped_column(
        Numeric(14, 2)
    )  # Available liquidity in USD (Polymarket)
    volume_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

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
    current_probability: Mapped[Optional[float]] = mapped_column(
        Numeric(7, 6)
    )  # 0.0-1.0
    current_american_odds: Mapped[Optional[int]] = mapped_column(Integer)

    # For Kalshi: store bid/ask spread (nullable for traditional books)
    current_yes_bid: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    current_yes_ask: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Opening odds (for detecting movement)
    opening_probability: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    opening_american_odds: Mapped[Optional[int]] = mapped_column(Integer)
    opening_captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Pre-computed calibration price (closing line or settled price)
    calibration_probability: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))

    # Movement tracking
    probability_change_24h: Mapped[Optional[float]] = mapped_column(Numeric(7, 6))
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    rank_change_24h: Mapped[Optional[int]] = mapped_column(Integer)

    # Opening price derivation
    opening_source: Mapped[Optional[str]] = mapped_column(String(30))

    # Resolution.
    #
    # 🔴 NULLABLE ON PURPOSE, AND THE ANNOTATION IS THE WHOLE POINT (Alex,
    # `runner-inbox/calibration/910`). Production has always been
    # `is_nullable = YES` with a False default; the model said
    # ``Mapped[bool]``, from which SQLAlchemy infers ``nullable=False``, so
    # ``Base.metadata.create_all`` built the column **NOT NULL**. Every gate that
    # builds its schema from this model therefore ran against a database in
    # which "nobody graded this" was not expressible — and that distinction is
    # exactly what 12-CAL, gotcha #21 and Queue 299 rung 1b rest on: NULL is
    # UNKNOWN truth, False is an affirmative graded loss, and publishing the
    # first as the second corrupts the calibration curve.
    #
    # This is a SCHEMA-EXPRESSIVENESS fix, not a behaviour change. No production
    # column is altered (production is already nullable), no data moves, and
    # every writer keeps storing False for unsettled via the default below —
    # which still fires, including when ``None`` is passed explicitly.
    #
    # 🔴 THE `server_default` IS LOAD-BEARING AND IT IS THE HALF THAT WAS MISSING
    # (CERT-521 [P1]). Nullability alone is not parity. Production's DDL is
    # `boolean NULL DEFAULT false` — the migration that built it
    # (`add_futures_tables.py`) declared `server_default='false'` — while a
    # client-side `default=` only fires on an ORM insert. So with nullability
    # widened and no server default, a RAW `INSERT` that omits the column, which
    # is how every real-Postgres gate here seeds, would store NULL in the test
    # database and FALSE in production. That is the same test/prod semantic split
    # this column was widened to close, re-opened one layer down: a gate could
    # manufacture "ungraded truth" out of a field it merely forgot to name.
    # `tests/test_pg_gate_seed_completeness.py` states the asymmetry as its own
    # reason to exist — "a raw INSERT bypasses SQLAlchemy's Python-side
    # `default=` ... only a `server_default` is [excused]".
    is_winner: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=False, server_default=text("false")
    )
    resolution_source: Mapped[Optional[str]] = mapped_column(String(30))

    # Trading activity (from Kalshi settled events API, per sub-market)
    # NULL = not yet fetched, 0 = confirmed zero trading
    volume: Mapped[Optional[int]] = mapped_column(Integer)

    # TOUCH-STAMP. Written unconditionally by every poll, so it answers "when
    # did the poller last SEE this row", NOT "when did this price move".
    # `app/routes/playoffs.py` depends on exactly that reading as a liveness
    # gate — see `price_changed_at` below and #2024. Do not narrow it.
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # #2024. When the stored price last actually CHANGED, maintained by
    # `app/utils/price_change_stamp.py` on every price-writing poll path.
    #
    # A SEPARATE COLUMN RATHER THAN A NARROWED `last_updated`, and the UX-P106
    # consumer audit is what decided that: the two live readings of that column
    # CONFLICT (`playoffs.py` = poller alive, `admin_judgments.py` = price
    # fresh), so no single value can serve both, and making the touch-stamp
    # conditional would drop stable prices out of the playoff grid.
    #
    # NULLABLE, and it stays that way: the column is populated forward by the
    # polls, so every pre-existing row reads NULL until its market is next
    # polled. A consumer switching to it must decide what NULL means for its own
    # question rather than inheriting a fabricated value — gotcha #53's rule,
    # applied at the schema.
    price_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
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

    @property
    def probability(self) -> Optional[float]:
        """Backward-compatible alias for current_probability."""
        return self.current_probability

    @probability.setter
    def probability(self, value: Optional[float]) -> None:
        self.current_probability = value

    @property
    def american_odds(self) -> Optional[int]:
        """Backward-compatible alias for current_american_odds."""
        return self.current_american_odds

    @american_odds.setter
    def american_odds(self, value: Optional[int]) -> None:
        self.current_american_odds = value


class FuturesOddsSnapshot(Base):
    """Historical odds snapshot for a futures outcome from a specific bookmaker."""

    __tablename__ = "futures_odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    outcome_id: Mapped[int] = mapped_column(
        ForeignKey("futures_outcomes.id"), index=True
    )
    bookmaker: Mapped[str] = mapped_column(
        String(50)
    )  # 'draftkings', 'fanduel', 'kalshi'

    # RAW implied probability for THIS ONE BOOKMAKER — vig-inclusive.
    #
    # Normalized from American odds, and nothing more: it is NOT de-vigged and
    # NOT a consensus. A full column of these sums to 1.16-1.33 on a 30-outcome
    # futures market, not to 1.0. This comment used to read "Normalized
    # probability (always calculated)", and that wording is why #1844 shipped:
    # a reader took it for a de-vigged consensus and subtracted one of these
    # rows from a real one, publishing an all-red movers row for months.
    #
    # To get a distribution, de-vig the column first —
    # app/utils/odds_math.devig_consensus(). Never compare a raw row to a blend.
    probability: Mapped[float] = mapped_column(Numeric(7, 6))

    # Source-specific raw data
    american_odds: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # For traditional books
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


class LineMovementAnalysis(Base):
    """Cached LLM-generated explanations for significant line movements."""

    __tablename__ = "line_movement_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id"), index=True)

    # Movement data (snapshot of what triggered the analysis)
    movement_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    # Detected movements as JSON: [{timestamp, home_prob_before, home_prob_after, change, ...}]

    # LLM-generated explanation
    explanation: Mapped[Optional[str]] = mapped_column(Text)

    # Market disagreement explanation (when prediction markets diverge from sportsbooks)
    disagreement_explanation: Mapped[Optional[str]] = mapped_column(Text)
    disagreement_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    # {source, sportsbook_prob, prediction_market_prob, divergence}

    # Cache management
    analysis_type: Mapped[str] = mapped_column(String(30), default="line_movement")
    # "line_movement" or "market_disagreement"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Line movement explanations expire:
    # - Scheduled games: 1 hour (news can change quickly)
    # - Live games: 15 minutes
    # - Completed games: never (historical analysis)

    # Relationship
    event: Mapped[Optional["Event"]] = relationship()


class TeamIdentityMapping(Base):
    """Maps team identities across external data sources.

    Enables O(1) team lookups instead of fuzzy name matching on every poll.
    Each row links a Team record to one external identifier (ESPN ID, Kalshi
    abbreviation, Odds API name, etc.) scoped by sport_key.
    """

    __tablename__ = "team_identity_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(200))
    source_name: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    source_abbreviation: Mapped[Optional[str]] = mapped_column(String(20))
    sport_key: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    team: Mapped["Team"] = relationship()


class Entity(Base):
    """A1 (#1020) — Universal identity-graph entity (Layer 0).

    One store for every real-world thing markets can reference: **team**,
    **person** (players/fighters/golfers/drivers/candidates/nominees),
    **event_concept** (tournament/card/GP/award-ceremony/election-night), and
    **competition** (league/tour/promotion). Teams are the first kind, folded in
    from the existing ``teams`` table (``source_team_id`` bridges the two during
    the transition — the legacy team readers are UNTOUCHED, so team matching
    cannot regress; the L1-L4 audit is the guard). Downstream layers (A2 grammar
    adapters, A4 resolution engine) read ``entity_aliases`` to resolve a mention
    to an entity, and use ``date_window_*`` as a first-class match signal (a
    concept carries its own date window so time is a signature dimension).
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'team' | 'person' | 'event_concept' | 'competition'
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(300), index=True)

    # Competition/sport this entity belongs to (a team's league, a concept's
    # tour). sport_key is denormalized for fast grammar binding without a join.
    sport_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sports.id"), index=True
    )
    sport_key: Mapped[Optional[str]] = mapped_column(String(50), index=True)

    # Transition bridge for kind='team': points back to the folded-in teams row
    # so existing team consumers can be migrated onto the registry incrementally.
    source_team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )

    # Date-windows as first-class match signals (event-concepts carry their own
    # window: a tournament's dates, a card's night, an election night).
    date_window_start: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_window_end: Mapped[Optional[date]] = mapped_column(Date)

    # External anchor for concepts/competitions (Kalshi series ticker, Poly event
    # id, etc.) so a source's own identifier can pin the entity.
    external_ref: Mapped[Optional[str]] = mapped_column(String(200), index=True)

    entity_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), server_default="1.0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list["EntityAlias"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_entities_kind_sport_key", "kind", "sport_key"),
        Index("ix_entities_date_window", "date_window_start", "date_window_end"),
    )


class EntityAlias(Base):
    """A1 (#1020) — a typed, provenance-tagged name for an :class:`Entity`.

    The resolution read path matches on ``alias_norm`` (normalized: lowercased,
    diacritics/punct stripped) so "resolve mention -> entity" is an indexed O(1)
    lookup for the grammar adapters (A2) and the resolution engine (A4). Alias
    types: ``canonical``, ``common_name``, ``abbreviation``, ``source_name`` (a
    source's own label, e.g. Odds API team name), ``ticker_token`` (a Kalshi
    ticker fragment). ``source`` records where the alias came from and
    ``confidence`` how trustworthy it is.
    """

    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    alias_norm: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    # 'canonical' | 'common_name' | 'abbreviation' | 'source_name' | 'ticker_token'
    alias_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), server_default="1.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entity: Mapped["Entity"] = relationship(back_populates="aliases")

    __table_args__ = (
        # Idempotent seeding/annotation: the same normalized alias of the same
        # type from the same source collapses to one row per entity.
        UniqueConstraint(
            "entity_id",
            "alias_norm",
            "alias_type",
            "source",
            name="uq_entity_alias_norm_type_source",
        ),
        Index("ix_entity_aliases_norm_type", "alias_norm", "alias_type"),
    )


class OscarsPool(Base):
    """A private Oscars prediction pool (e.g., family competition)."""

    __tablename__ = "oscars_pools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(
        String(8), unique=True, nullable=False, index=True
    )
    ceremony_year: Mapped[int] = mapped_column(Integer, default=2026)
    created_by_name: Mapped[str] = mapped_column(String(50), nullable=False)
    picks_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # JSON list of bonus market questions set by pool creator
    bonus_markets: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    # JSON dict of category_key -> winner_name for scoring
    results: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relationships
    members: Mapped[list["OscarsPoolMember"]] = relationship(
        back_populates="pool", cascade="all, delete-orphan"
    )


class OscarsPoolMember(Base):
    """A participant in an Oscars pool."""

    __tablename__ = "oscars_pool_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(
        ForeignKey("oscars_pools.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar_emoji: Mapped[str] = mapped_column(String(10), default="🎬")
    member_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("pool_id", "display_name", name="uq_pool_member_name"),
    )

    # Relationships
    pool: Mapped["OscarsPool"] = relationship(back_populates="members")
    picks: Mapped[list["OscarsPoolPick"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class OscarsPoolPick(Base):
    """A single category pick by a pool member."""

    __tablename__ = "oscars_pool_picks"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("oscars_pool_members.id", ondelete="CASCADE"), index=True
    )
    category_key: Mapped[str] = mapped_column(String(50), nullable=False)
    nominee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    probability_at_pick: Mapped[float] = mapped_column(Numeric(7, 6), nullable=False)
    is_confidence_pick: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    points_earned: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    picked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("member_id", "category_key", name="uq_member_category_pick"),
    )

    # Relationships
    member: Mapped["OscarsPoolMember"] = relationship(back_populates="picks")


class MatchingOverride(Base):
    """Admin-curated matching overrides for championship grids.

    Stores human decisions about team name merges, team inclusions/exclusions,
    and market-to-column assignments. Applied during grid building to ensure
    matching accuracy across all playoff grids.

    Inspired by Google Photos face-matching: the system surfaces uncertain
    matches, the admin approves/rejects, and decisions persist.
    """

    __tablename__ = "matching_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_slug: Mapped[str] = mapped_column(String(50), index=True)
    override_type: Mapped[str] = mapped_column(String(50))
    # Types:
    #   "team_alias"   — source_name is an alias for target_name (merge them)
    #   "team_exclude" — source_name should be excluded from the grid
    #   "team_include" — source_name must appear in the grid
    #   "market_column"— source_name is a market ID, target_name is the column key
    #   "source_trust" — source_name is "source:column", trust_level in context

    source_name: Mapped[str] = mapped_column(String(300))
    target_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    decision: Mapped[str] = mapped_column(String(20), default="approved")
    # "approved" or "rejected"

    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Freeform metadata: reason, who decided, confidence, etc.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "league_slug", "override_type", "source_name", name="uq_override_key"
        ),
    )


class GolfLeaderboardSnapshot(Base):
    """Start-of-day leaderboard snapshot for computing "today" deltas.

    Stores full leaderboard state (position, score, win probability per player)
    at a point in time — typically the start of each tournament day. The
    leaderboard endpoint uses this to compute position_change and win_prob_change.
    """

    __tablename__ = "golf_leaderboard_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tour: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(300), nullable=False)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="start_of_day"
    )
    # JSONB array of {player_name, position, total_score, win_prob, ...}
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tour", "snapshot_date", "snapshot_type", name="uq_golf_snapshot"
        ),
    )


class UserPrediction(Base):
    """Tracks Higher/Lower guesses from the Discover feed."""

    __tablename__ = "user_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    market_id: Mapped[int] = mapped_column(Integer, nullable=False)
    guess: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSeenMarket(Base):
    """Tracks which markets/events a user has seen in the Discover feed."""

    __tablename__ = "user_seen_markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    item_type: Mapped[str] = mapped_column(String(10), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DiscoverInteraction(Base):
    """Append-only interaction events from web and native Discover surfaces."""

    __tablename__ = "discover_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    surface: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    item_name: Mapped[Optional[str]] = mapped_column(String(300))
    score: Mapped[Optional[int]] = mapped_column(Integer)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    # Queue 310 — canonical market shape at interaction time, mirroring
    # FuturesMarket.market_type (claim | quantity | duel | field |
    # container_member | unshaped). Nullable: every row written before this
    # column existed predates the signal, and there is no backfill — a null
    # here means "not recorded", never "unshaped".
    market_type: Mapped[Optional[str]] = mapped_column(String(20))
    # Pre-training gate — who/what produced this row, so Alex's 250 labels
    # do not train on warmer/sentinel echo. Nullable pre-column: NULL is
    # treated as unknown at read time (silent-default lesson: absence must
    # not impersonate the valuable class). Historical NULLs are re-estimated
    # by a separate dry-run heuristic (89% / 23.6% fingerprints) — never
    # unattended rewrites. See add_disc_interactions_provenance migration.
    #
    # THE TYPE IS THE NAMED POSTGRES ENUM, NOT `String`. It was `String(20)`
    # from 2026-08-18 to 2026-08-29, and that one word cost every interest
    # signal the product received in those eleven days.
    #
    # `add_disc_int_provenance` created a real `CREATE TYPE discover_provenance`
    # and added the column as that type. The model kept saying `String`, so
    # SQLAlchemy compiled the bind as `$13::VARCHAR`, and PostgreSQL refuses
    # varchar -> enum without a cast:
    #
    #   DatatypeMismatchError: column "provenance" is of type
    #   discover_provenance but expression is of type character varying
    #
    # Every INSERT into this table therefore 500ed. `POST /api/feed/interactions`
    # is the only writer, the browser sends it `keepalive` inside a
    # `.catch(() => {})`, and nothing reads the table on a request path — so the
    # rail failed in total silence. The last row banked 2026-08-18T19:34Z; the
    # next eleven days produced zero. This is the mirror of the defect
    # `app/utils/discover_provenance.py` documents one layer up ("the ORM took a
    # value the database would reject"): there the VALUE list drifted from the
    # enum, here the COLUMN TYPE did, and only the second one was fatal.
    #
    # No test caught it because the recording double does not enforce types and
    # there is no local Postgres. `tests/test_discover_interaction_write_path.py`
    # closes that by compiling the INSERT against the real asyncpg dialect and
    # reading the cast, which needs no database at all.
    #
    # Generic `sa.Enum` and not `postgresql.ENUM`: it renders the named type on
    # Postgres (what production has) and VARCHAR on SQLite (what most of the
    # suite runs), so `Base.metadata.create_all` keeps working on both. The
    # value order is `PROVENANCE_VALUES` because enum ordinals are what
    # `ORDER BY provenance` means, and that tuple is asserted equal to the
    # migration chain's order by `tests/test_discover_provenance.py`.
    provenance: Mapped[Optional[str]] = mapped_column(
        Enum(
            *PROVENANCE_VALUES,
            name="discover_provenance",
            # The type is created by the migration on production and by
            # `create_all` on a fresh test database; never let the ORM invent a
            # second definition with a different label order.
            create_constraint=False,
            validate_strings=False,
        ),
        nullable=True,
        index=True,
        server_default="unknown",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index(
            "ix_discover_interactions_rollup",
            "created_at",
            "surface",
            "category",
            "action",
        ),
        Index("ix_discover_interactions_item", "item_type", "item_id", "created_at"),
    )


class SearchQueryLog(Base):
    """Append-only log of /api/events/search queries (#239 Item 4).

    Lightweight instrumentation to see what people actually search for, whether it
    returns results, and which result leads — feeding the Instant Answers program
    (search miss = the #1 reliability failure class) and the search-sentinel gold
    set. Written fire-and-forget so it never adds latency to the search path;
    identity is best-effort (user_id when signed in, session_id from x-session-id)."""

    __tablename__ = "search_query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    query: Mapped[str] = mapped_column(String(300), nullable=False)
    result_count: Mapped[Optional[int]] = mapped_column(Integer)
    top_result_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DiscoverReviewDecision(Base):
    """Admin decisions on aggregate Discover engagement signals."""

    __tablename__ = "discover_review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    item_name: Mapped[Optional[str]] = mapped_column(String(300))
    category: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    surface: Mapped[Optional[str]] = mapped_column(String(20))
    auth_segment: Mapped[Optional[str]] = mapped_column(String(20))
    family_key: Mapped[Optional[str]] = mapped_column(String(300))
    archetype: Mapped[Optional[str]] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    features: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index(
            "ix_discover_review_decisions_item", "item_type", "item_id", "created_at"
        ),
    )


class DiscoverGroundTruthDiagnostic(Base):
    """Persisted Discover ground-truth hit/miss diagnostics."""

    __tablename__ = "discover_ground_truth_diagnostics"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_group: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(500), nullable=False)
    feed_name: Mapped[Optional[str]] = mapped_column(String(500))
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    probability: Mapped[Optional[str]] = mapped_column(String(250))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[str]] = mapped_column(String(50))
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    quality_class: Mapped[Optional[str]] = mapped_column(String(40))
    archetype: Mapped[Optional[str]] = mapped_column(String(80))
    family_key: Mapped[Optional[str]] = mapped_column(String(300))
    story_key: Mapped[Optional[str]] = mapped_column(String(300))
    triage_bucket: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    matched_market_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    trace_status: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    trace_summary: Mapped[Optional[str]] = mapped_column(Text)
    db_match_count: Mapped[Optional[int]] = mapped_column(Integer)
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index(
            "ix_discover_gt_diag_run_group",
            "run_id",
            "source_group",
            "status",
        ),
        Index(
            "ix_discover_gt_diag_captured",
            "captured_at",
            "source_group",
            "triage_bucket",
        ),
    )


class DiscoverCandidateSnapshot(Base):
    """Daily snapshot of the pre-ranking Discover candidate pool (#142/RANK-2).

    One row per scored futures candidate per run. Persists the served rank plus
    the per-candidate interestingness features and RANK-1 score anatomy so the
    offline replay runner can re-rank a frozen pool under a different config and
    diff top-K vs (i) the served ordering, (ii) the human-label gold set, and
    (iii) classifier metrics. Bounded per run and purged after ~30 days.
    """

    __tablename__ = "discover_candidate_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    market_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="futures")
    served_rank: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(500))
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    quality_class: Mapped[Optional[str]] = mapped_column(String(40))
    family_key: Mapped[Optional[str]] = mapped_column(String(300))
    story_key: Mapped[Optional[str]] = mapped_column(String(300))
    # served ordering value (post interestingness blend, uncapped float — #141)
    rank_score: Mapped[Optional[float]] = mapped_column(Float)
    # served capped display score
    display_score: Mapped[Optional[int]] = mapped_column(Integer)
    # anonymous pre-blend uncapped ranking score (from the tracer) — the base the
    # replay runner re-blends a different interestingness weight/blend against
    pre_blend_rank_score: Mapped[Optional[float]] = mapped_column(Float)
    # category base term, so replay can apply a base-score override cleanly
    category_base: Mapped[Optional[float]] = mapped_column(Float)
    interestingness_score: Mapped[Optional[float]] = mapped_column(Float)
    # MarketInterestingnessInputs source dict (for recomputing under new weights)
    features: Mapped[Optional[dict]] = mapped_column(JSONB)
    # full RANK-1 score_anatomy for explainability
    anatomy: Mapped[Optional[dict]] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_discover_candidate_snap_run", "run_id", "served_rank"),
        Index("ix_discover_candidate_snap_captured", "captured_at", "market_id"),
    )


class ExternalCuratorGroundTruthItem(Base):
    """Reviewed external-curator/social ground-truth rows for Discover audits."""

    __tablename__ = "external_curator_ground_truth_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    probability: Mapped[Optional[str]] = mapped_column(String(250))
    hook: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[str]] = mapped_column(String(50))
    platform: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    handle: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    engagement: Mapped[Optional[str]] = mapped_column(String(100))
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    extraction_notes: Mapped[Optional[str]] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", index=True
    )
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_external_curator_gt_source_date",
            "source",
            "published_at",
        ),
    )


class BugReport(Base):
    """User-submitted bug reports via rage shake."""

    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255))
    session_id: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    screenshot_base64: Mapped[Optional[str]] = mapped_column(Text)
    app_state: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    category: Mapped[Optional[str]] = mapped_column(String(30))
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    backlog_ref: Mapped[Optional[str]] = mapped_column(String(20))
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text)
    notification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PredictionChallenge(Base):
    """Friend challenge: shareable Higher/Lower prediction link."""

    __tablename__ = "prediction_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    creator_session_id: Mapped[Optional[str]] = mapped_column(String(100))
    challenge_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    market_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("futures_markets.id"), nullable=False
    )
    market_name: Mapped[Optional[str]] = mapped_column(Text)
    creator_guess: Mapped[str] = mapped_column(String(10), nullable=False)
    creator_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    friend_guess: Mapped[Optional[str]] = mapped_column(String(10))
    friend_session_id: Mapped[Optional[str]] = mapped_column(String(100))
    actual_probability: Mapped[Optional[float]] = mapped_column(Numeric)
    creator_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    friend_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    market: Mapped["FuturesMarket"] = relationship()
    creator: Mapped[Optional["User"]] = relationship()


class DeviceToken(Base):
    """APNS/FCM device tokens for push notifications."""

    __tablename__ = "device_tokens"
    __table_args__ = (UniqueConstraint("device_token", name="uq_device_tokens_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "ios" or "macos"
    # Which KIND of token this row holds (Queue 311 / #1159). "apns" is a raw
    # APNS hex token, which FCM's messaging.send() REJECTS; "fcm" is a Firebase
    # registration token, the only kind that can actually be sent to. The server
    # default makes every pre-existing row self-describe correctly as the
    # unsendable APNS token it is — no backfill script needed.
    #
    # Deliberately its own column rather than an overloaded platform="ios_fcm":
    # that fits in String(10) and would work, which is what makes it tempting,
    # but it destroys `platform` as a platform axis (gotcha #40's class of "one
    # column means two things").
    #
    # NOTE: one device legitimately produces TWO rows here — an apns row and an
    # fcm row — because they are two different tokens and the unique constraint
    # is on the token. Anything counting DEVICES must count distinct
    # (user_id, platform), never rows.
    token_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="apns", default="apns"
    )  # "apns" or "fcm"
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship()


class FeaturedMarketCapture(Base):
    """Daily capture of Kalshi/Polymarket front-page/featured markets.

    Used as advisory ground truth for Discover ranking review.
    Captures are based on top-volume markets since neither API
    exposes a dedicated "featured" endpoint.
    """

    __tablename__ = "featured_market_captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )  # kalshi_featured, polymarket_featured, manual
    captured_date: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )  # YYYY-MM-DD
    market_name: Mapped[str] = mapped_column(String(500), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(200), index=True
    )  # Kalshi ticker or Polymarket condition_id
    matched_market_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("futures_markets.id"), index=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    url: Mapped[Optional[str]] = mapped_column(Text)
    rank: Mapped[Optional[int]] = mapped_column(Integer)  # 1-based rank by volume
    volume_24h: Mapped[Optional[float]] = mapped_column(Numeric)
    probability: Mapped[Optional[float]] = mapped_column(Numeric)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    matched_market: Mapped[Optional["FuturesMarket"]] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "source", "captured_date", "external_id",
            name="uq_featured_capture_source_date_ext",
        ),
        Index(
            "ix_featured_capture_source_date",
            "source",
            "captured_date",
        ),
    )


class DiscoverPairwiseLabel(Base):
    """Pairwise preference label for Discover card ranking calibration.

    An admin reviewer sees two Discover cards side by side and picks which
    is more interesting. These explicit editorial preferences can later
    be used to calibrate feed ranking scores.
    """

    __tablename__ = "discover_pairwise_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    card_a_market_id: Mapped[int] = mapped_column(
        ForeignKey("futures_markets.id"), nullable=False
    )
    card_b_market_id: Mapped[int] = mapped_column(
        ForeignKey("futures_markets.id"), nullable=False
    )
    card_a_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    card_b_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    choice: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'a', 'b', 'both', 'neither', 'skip'
    pair_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    pair_strategy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    surface: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ranking_error: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    card_a_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    card_b_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    card_a_market: Mapped["FuturesMarket"] = relationship(
        foreign_keys=[card_a_market_id]
    )
    card_b_market: Mapped["FuturesMarket"] = relationship(
        foreign_keys=[card_b_market_id]
    )


class RankingJudgment(Base):
    """Human judgment on a feed card from the Discover admin review.

    Labels (love/fine/bad/kill) with reason tags and optional pairwise
    comparisons. Captures the scoring context at review time so judgments
    can be used for scorer regression tests.
    """

    __tablename__ = "ranking_judgments"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    surface: Mapped[str] = mapped_column(String(50), default="discover")
    rank_seen: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_type: Mapped[str] = mapped_column(String(20), default="futures")
    market_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("futures_markets.id"), nullable=True
    )
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    market_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label: Mapped[str] = mapped_column(String(10), nullable=False)
    reason_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), default=[])
    better_than: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worse_than: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score_at_review: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category_at_review: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    archetype_at_review: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quality_class_at_review: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    headline_at_review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feed_request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    label_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fixable_interesting: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    repair_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    repair_target_entity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repair_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(100), default="alex")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CurationSignal(Base):
    """Quick boost/demote signal from the curator (iOS Share Sheet or admin)."""

    __tablename__ = "curation_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_platform: Mapped[Optional[str]] = mapped_column(String(30))
    market_ticker: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source_device: Mapped[Optional[str]] = mapped_column(String(30))
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    market_id: Mapped[Optional[int]] = mapped_column(ForeignKey("futures_markets.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DiscoverLabelEvalRun(Base):
    """Persisted offline eval runs for human-labeled Discover ranking data."""

    __tablename__ = "discover_label_eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    eval_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="discover_label_gold_set"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok", index=True)
    input_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dataset_window_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    surface: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tapworthy_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    boring_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duplicate_family_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unclear_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bad_explanation_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bad_image_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    broad_appeal_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fixable_interest_rate_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tapworthy_recall_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metric_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    category_breakdowns: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notable_regressions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    eval_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_discover_label_eval_name_captured", "eval_name", "captured_at"),
        Index("ix_discover_label_eval_status_captured", "status", "captured_at"),
    )


class DurableStateSnapshot(Base):
    """Cross-process last-good state that must outlive Redis (Queue 298, #1512).

    ONE narrow row per artifact identity — the calibration payload and each
    sentinel's verdict scorecard. Deliberately generic and deliberately small:
    C117 found no existing durable-state primitive to reuse, and ruled that the
    domain JSONB tables must not be repurposed for it.

    Not a history table. Each identity keeps exactly its latest trustworthy
    generation, replaced in one atomic statement guarded by ``generation``, so a
    slow/failed writer can never destroy a newer good copy (see
    ``app.services.durable_snapshots.publish_snapshot``).
    """

    __tablename__ = "durable_state_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Stable artifact name, e.g. ``calibration:main`` / ``sentinel:flow``.
    identity: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    #: The PAYLOAD's contract version (calibration's population_version, a
    #: sentinel's scorecard version) — not the envelope format version.
    schema_version: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Monotonic build ordering; epoch-ms of ``generated_at`` (see
    #: ``durable_state.generation_for``). Guards the atomic replace.
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: sha256 of the canonical payload — catches a torn write that still parses.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    #: False means "do not serve this": a partial build that was recorded but is
    #: not a trustworthy answer.
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Producer that wrote it, for provenance on the served payload.
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TypeaheadIndex(Base):
    """Option D (#1866): ONE narrow searchable row per entity, so the typeahead
    working set FITS IN THE POOL.

    THE MECHANISM, which is a residency argument and not a read-volume one.
    LAT-P062 cut DB-wide physical reads 79.1 -> 34.50 MB/s (a 56% cut against a
    predicted 21%) and the typeahead tail did not move at all — bootstrap 95% CI
    [+25.9%, +111.7%], 0.00% of resamples reaching the 30% that would have
    halted. Freeing 44.6 MB/s moved the tail NOT AT ALL. The binding constraint
    is that the typeahead trigram surface is 688.6 MB against a 1 GiB
    ``shared_buffers`` that also serves every other query in the product — 67.2%
    of the pool, evicted continuously by everything. This table is the same
    recall over a working set small enough that the clock-sweep keeps it.

    WHY EVERY COLUMN IS THE WIDTH IT IS. The heap width IS the feature; a wide
    row here is not a style preference, it is the mechanism failing. The sketch
    in ``docs/audits/latency/lat-p063-option-d-mechanism-and-prediction.md``
    assumed ~120 B/row => ~46 MB heap. This schema is honestly ~177 B/row =>
    **~67 MB** at ~380k rows (see the migration docstring for the arithmetic).
    That is a real +21 MB against the registered sketch and it is recorded
    rather than quietly absorbed: D3's bar (< 200 MB total, HALT at > 350 MB)
    still passes, with less margin than the sketch implied.

    Two width decisions are load-bearing:

    * ``content_hash`` is a **BIGINT**, not the sha256 hex a hash column usually
      is. 64 hex chars would cost 64 B/row — **24 MB of pure drift-detection
      overhead**, more than a third of the heap this table is trying to be. A
      64-bit digest is ample for detecting an entity's projection changing.
    * ``rank_hint`` is ``REAL`` (4 B), not ``Float``/double (8 B). It is a
      ranking nudge, never an arithmetic result.

    THIS TABLE IS A SECOND COPY OF TRUTH, so it ships with a sentinel or it does
    not ship (D4, and it is not negotiable). #1866's whole history is
    instruments that reported success while doing nothing: a trade backfill that
    recorded SUCCESS every 6 h for ten weeks while recovering nothing
    (gotcha #53), a warmer whose ``fresh`` skip could never fire, two tests that
    passed while asserting a model production had refuted. A denormalised index
    that silently goes stale is a WORSE defect than the slow query it replaced,
    because the slow query was at least correct. See
    ``app.tasks.typeahead_index``.

    NOTHING READS THIS TABLE YET, and that is deliberate, not unfinished. The
    registered D3 halt says "> 350 MB ⇒ the sizing model is wrong; re-derive
    **before building the read path**" — so the read path is gated on a
    measurement that cannot be taken until this table exists and is populated in
    production. Building it now would be building through a halt gate.
    """

    __tablename__ = "typeahead_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Which source table this row projects. One of
    #: ``app.tasks.typeahead_index.ENTITY_TYPES``.
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    #: The source row's primary key, as text. Text because concepts and hubs are
    #: slug-keyed while teams/events/markets are integer-keyed, and one column
    #: that means "the source id" beats two nullable ones that drift apart.
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)

    #: What the dropdown shows. Never matched against — see ``search_text``.
    display_text: Mapped[str] = mapped_column(String(300), nullable=False)
    #: The lowercased haystack the trigram GIN indexes: name + aliases +
    #: abbreviation + (for events) both team names. Matching reads ONLY this, so
    #: recall equivalence with the surface it replaces is a property of the
    #: BUILDER, and it is what D2's 46 armed gold probes prove.
    search_text: Mapped[str] = mapped_column(Text, nullable=False)

    #: Denormalised for cheap filtering/ordering; nullable because concepts and
    #: cross-sport markets legitimately have none.
    sport_key: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    #: Prominence nudge for ordering the candidate pool. REAL on purpose (4 B).
    rank_hint: Mapped[float] = mapped_column(Float(precision=24), nullable=False, default=0.0)

    #: 64-bit digest of the projected content (see ``project_*`` in the builder).
    #: Equal hash => the projection is unchanged => the row is not rewritten and
    #: the sentinel counts it clean. This is the drift signal.
    content_hash: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: False = tombstoned (the source row went away or left the searchable set).
    #: Kept rather than deleted so a reconcile pass is idempotent and so the
    #: sentinel can tell "removed on purpose" from "never built".
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Last time the builder confirmed this row against its source — whether or
    #: not it changed. The sentinel's staleness read is over THIS, not over
    #: ``updated_at``-style "last write", because a row that is correct and
    #: re-verified is fresh while a row that is correct and unvisited is not.
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_typeahead_index_entity"),
        # The reconcile cursor's ordering, and the sentinel's staleness scan.
        Index("ix_typeahead_index_type_refreshed", "entity_type", "refreshed_at"),
    )


class SettlementCapture(Base):
    """What a settlement source SAID, recorded before its retention window closes.

    Queue 389 Item 1 (#2077). Append-only, additive, and deliberately **write-only
    with respect to grading**: nothing in the capture path may write
    ``futures_outcomes.is_winner``. The capture answers "what did the source say,
    and when did we ask" — a separate, later, reviewable step decides what to do
    about it.

    WHY A TABLE AND NOT A JSONB COLUMN. Three reasons, in order of weight:

    1. **The population is the point.** C-CLIFF-CENSUS-1 dates the whole burn-down
       (273,682 verifiable-missing across five buckets, the oldest expiring
       2026-08-28 and the largest 2026-11-03). Answering "which buckets have we
       saved" is a GROUP BY, and a JSONB blob hanging off ``futures_markets``
       cannot be grouped without a scan of the table we are auditing.
    2. **Captures are plural per market.** A market probed at 60 days remaining and
       re-probed at 10 produces two records, and the second must not overwrite the
       first — an ``AMBIGUOUS_EMPTY`` that later resolves to ``SETTLED`` is exactly
       the history the audit needs.
    3. **``DurableStateSnapshot`` is explicitly not this.** It is one latest row per
       identity, and C117 ruled that domain JSONB tables must not be repurposed as
       durable-state primitives. The same reasoning forbids the reverse.

    The row records the **raw response**, not just the parse. A parse can be wrong;
    a recorded body lets a later reader re-derive the verdict without re-probing a
    source that may by then have purged the record. That is the whole insurance
    policy: the capture window closes permanently, so what we fail to store today
    is not recoverable at any price tomorrow.
    """

    __tablename__ = "settlement_captures"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: The market whose settlement we probed. Indexed for the per-market history
    #: read; NOT unique, because re-probes are the point (see reason 2 above).
    market_id: Mapped[int] = mapped_column(
        ForeignKey("futures_markets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: ``kalshi`` / ``polymarket`` / ``datagolf``.
    source: Mapped[str] = mapped_column(String(40), nullable=False)

    #: The EXACT settlement key used — the full Kalshi ticker or the Polymarket
    #: ``conditionId``/event id. Recorded rather than re-derived because
    #: C-WINNER-TRUTH-1 got a false mismatch rate from a truncated ticker, and a
    #: capture whose key cannot be reproduced cannot be re-checked.
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    #: One of ``app.utils.settlement_truth.Disposition``. Stored as text rather
    #: than a PG enum so adding a disposition is a code change, not a migration —
    #: the vocabulary is expected to grow as new response shapes are met.
    disposition: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    #: The source's own winning-outcome label, verbatim and un-normalised.
    #: **NULL unless ``disposition == 'settled'``** — enforced by a CHECK
    #: constraint below, so the invariant survives a caller that forgets it.
    winning_outcome: Mapped[Optional[str]] = mapped_column(Text)

    #: Which HTTP channel actually answered (``kalshi_market``, ``kalshi_event``,
    #: ``gamma``, ``clob``). Provenance: a Gamma claim and a CLOB claim have
    #: different retention and different reliability.
    answered_by: Mapped[Optional[str]] = mapped_column(String(40))

    #: Every channel consulted with its HTTP status, in order. This is what makes
    #: the gotcha #53 disambiguation auditable rather than merely asserted.
    channels: Mapped[Optional[dict]] = mapped_column(JSONB)

    #: The raw bodies, keyed by channel, truncated by the writer. Constraint (a).
    raw_response: Mapped[Optional[dict]] = mapped_column(JSONB)

    #: Human-readable WHY, always populated for a non-settled disposition.
    reason: Mapped[Optional[str]] = mapped_column(Text)

    #: Why this market entered the sweep — one of
    #: ``settlement_truth.CANDIDATE_REASONS``. A candidate reason is a reason to
    #: LOOK, never evidence: ``scores_derivable`` in particular is a guess wearing
    #: arithmetic, because closed events keep frozen mid-game scores.
    candidate_reason: Mapped[str] = mapped_column(String(40), nullable=False)

    #: Days of retention left at the moment of capture, per
    #: ``kalshi_retention.days_until_purge``. Negative means we probed past the
    #: measured cliff on purpose. This is the column the burn-down groups on.
    days_remaining_at_capture: Mapped[Optional[int]] = mapped_column(Integer)

    #: Which sweep run wrote this, so a bad run is identifiable and excludable
    #: wholesale without guessing from timestamps.
    sweep_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    #: Version of the PROBE PROTOCOL that produced the disposition. If the
    #: classifier's rules change, old rows must not be silently re-read under the
    #: new vocabulary — they were produced by a different question.
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        # The invariant of the whole design, enforced by the DATABASE and not only
        # by the dataclass: a settlement may exist only under the disposition that
        # licenses it. A caller that bypasses the writer still cannot record a
        # winner it was not told.
        CheckConstraint(
            "(disposition = 'settled') = (winning_outcome IS NOT NULL)",
            name="ck_settlement_capture_winner_requires_settled",
        ),
        # The burn-down read: "what have we saved, per bucket, per source".
        Index("ix_settlement_captures_sweep_disp", "sweep_id", "disposition"),
        # The re-probe read: newest capture per market.
        Index("ix_settlement_captures_market_time", "market_id", "captured_at"),
    )


class EventProviderAnchor(Base):
    """One provider id, one event — the channel ruling 048's drain clause needs.

    The table shipped EMPTY on 2026-08-24 (migration ``anchors_and_captures``,
    #1946 / #2119 / #2114) and had no ORM model, so nothing could read or write
    it from application code. That is why the measured state on 2026-08-25 was
    **0 rows**, and why gotcha #32's bounding clause — *"id-keyed reconciliation
    drains the duplicate when an id arrives"* — was still prose eleven months
    after it was written.

    WHAT A ROW MEANS. Exactly one thing: *provider ``source`` calls this event
    ``source_id``, and that id is of kind ``id_kind``.* It is a correspondence
    record, not a merge instruction and not a claim of quality. The registry
    reads it as cascade Step 2 (cross-source id), which is ruling 048 **arm A**
    — a SHARED id — reached through the channel instead of through one of the
    three id columns that happen to exist on ``events``. Arm A never needed
    ``schedule_derived`` and still does not; this widens nothing.

    WHY ``id_kind`` IS THE LOAD-BEARING COLUMN. **Only ``id_kind='game'`` may
    anchor an absorption.** A Kalshi player-prop ticker and a Polymarket
    ``conditionId`` are ``market``; a Polymarket event id is ``container``. All
    three are worth recording, because they are how an anchor is *discovered* —
    but only one of them asserts "these two rows are the same game". A table
    that stored all three without saying which kind they are would rebuild
    ruling 048's original defect with better indexing.

    WHY THE UNIQUE INDEX IS ALSO THE DUPLICATE DETECTOR. ``(source, source_id,
    id_kind)`` is unique, so a second event trying to claim an id that is
    already bound cannot succeed. The conflict is not an error to swallow — it
    is the *first* moment the system holds proof that two rows are one game,
    keyed on an id rather than guessed from names and a time window. The writer
    in ``app/services/anchor_channel.py`` reads that conflict deliberately and
    reports ``COLLISION``.

    ``source_id`` IS NAMESPACE-QUALIFIED, NEVER BARE. It is a plain
    ``VARCHAR(200)`` with no per-provider structure, so two different games can
    collide on one key unless the writer qualifies it. Alex ruled the Kalshi
    instance on 2026-08-21 (#1946 Item 7): a bare game-id token collides at
    0.0404%, so a Kalshi anchor is written only as ``sport_key:game_id``.
    ``app/utils/provider_anchor_keys.py`` applies that rule to every provider,
    including the StatPal namespace split (6-digit vs 10-digit fixture ids under
    one column name) that produced the 21 conflicting duplicate groups on #2213.
    Callers must build keys with that module. Never hand-format a ``source_id``.
    """

    __tablename__ = "event_provider_anchors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: The event this provider id names. ``CASCADE`` on delete: an anchor to a
    #: row that no longer exists is not history, it is a dangling assertion that
    #: a later absorption would act on.
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: ``odds_api`` | ``espn`` | ``statpal`` | ``kalshi`` | ``polymarket``.
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    #: The namespace-qualified id. See the class docstring — never bare.
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)

    #: ``game`` | ``market`` | ``container``. Only ``game`` may anchor.
    id_kind: Mapped[str] = mapped_column(String(32), nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    #: Provenance of the claim that attached this anchor — which call site, and
    #: whether that claim was schedule-derived. Recorded because an anchor that
    #: cannot say who wrote it cannot be selectively withdrawn when a call site
    #: turns out to have been wrong, and ruling 048 exists because two call
    #: sites were wrong for months.
    claim_context: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        # Identity, and the duplicate detector. ``id_kind`` is IN the key so one
        # value may legitimately appear as both a ``market`` and a ``container``
        # without colliding. Name matches the migration exactly.
        Index(
            "uq_anchor_source_id", "source", "source_id", "id_kind", unique=True
        ),
    )
