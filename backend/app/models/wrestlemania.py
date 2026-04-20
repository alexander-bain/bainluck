"""WrestleMania 42 prediction game models — throwaway after event."""

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


class WrestlemaniaMatch(Base):
    __tablename__ = "wrestlemania_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_order: Mapped[int] = mapped_column(Integer, nullable=False)
    night: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    match_type: Mapped[str] = mapped_column(String(100), nullable=False)
    participants: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    lock_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")
    polymarket_event_id: Mapped[Optional[str]] = mapped_column(String(200))
    polymarket_condition_id: Mapped[Optional[str]] = mapped_column(String(200))
    storyline: Mapped[Optional[str]] = mapped_column(Text)
    winner_outcome_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wrestlemania_outcomes.id", use_alter=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    outcomes: Mapped[list["WrestlemaniaOutcome"]] = relationship(
        back_populates="match", foreign_keys="WrestlemaniaOutcome.match_id"
    )


class WrestlemaniaOutcome(Base):
    __tablename__ = "wrestlemania_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("wrestlemania_matches.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    polymarket_token_id: Mapped[Optional[str]] = mapped_column(String(200))
    wikipedia_image_url: Mapped[Optional[str]] = mapped_column(Text)
    case_text: Mapped[Optional[str]] = mapped_column(Text)
    probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    decimal_odds: Mapped[Optional[float]] = mapped_column(Numeric(8, 3))
    is_winner: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["WrestlemaniaMatch"] = relationship(
        back_populates="outcomes", foreign_keys=[match_id]
    )


class WrestlemaniaOddsSnapshot(Base):
    __tablename__ = "wrestlemania_odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    outcome_id: Mapped[int] = mapped_column(
        ForeignKey("wrestlemania_outcomes.id"), nullable=False
    )
    probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="seed")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WrestlemaniaPlayer(Base):
    __tablename__ = "wrestlemania_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    player_token: Mapped[str] = mapped_column(String(64), nullable=False)
    bankroll: Mapped[float] = mapped_column(Numeric(12, 2), default=1_000_000)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WrestlemaniaPick(Base):
    __tablename__ = "wrestlemania_picks"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("wrestlemania_players.id"), nullable=False
    )
    outcome_id: Mapped[int] = mapped_column(
        ForeignKey("wrestlemania_outcomes.id"), nullable=False
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("wrestlemania_matches.id"), nullable=False
    )
    stake: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    decimal_odds_at_pick: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    result: Mapped[Optional[str]] = mapped_column(String(20))
    payout: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("player_id", "outcome_id", name="uq_one_pick_per_outcome"),
    )
