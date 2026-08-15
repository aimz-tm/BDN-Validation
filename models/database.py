import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Vessel(TimestampMixin, Base):
    __tablename__ = "vessels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imo: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mmsi: Mapped[str | None] = mapped_column(String(9), unique=True)
    vessel_type: Mapped[str | None] = mapped_column(String(80))
    flag: Mapped[str | None] = mapped_column(String(80))

    ais_positions: Mapped[list["AISPosition"]] = relationship(back_populates="vessel", cascade="all, delete-orphan")
    received_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="vessel",
        foreign_keys="Transaction.vessel_id",
    )
    barge_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="barge",
        foreign_keys="Transaction.barge_id",
    )

    __table_args__ = (
        CheckConstraint("imo ~ '^[0-9]{7}$'", name="ck_vessels_imo_format"),
        CheckConstraint("mmsi IS NULL OR mmsi ~ '^[0-9]{9}$'", name="ck_vessels_mmsi_format"),
    )


class AISPosition(Base):
    __tablename__ = "ais_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessels.id", ondelete="CASCADE"),
    )
    mmsi: Mapped[str] = mapped_column(String(9), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    speed_knots: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    course_degrees: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    heading_degrees: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    navigational_status: Mapped[str | None] = mapped_column(String(80))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vessel: Mapped[Vessel | None] = relationship(back_populates="ais_positions")

    __table_args__ = (
        CheckConstraint("mmsi ~ '^[0-9]{9}$'", name="ck_ais_positions_mmsi_format"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_ais_positions_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_ais_positions_longitude_range"),
        CheckConstraint("speed_knots IS NULL OR speed_knots >= 0", name="ck_ais_positions_speed_non_negative"),
        CheckConstraint(
            "course_degrees IS NULL OR course_degrees BETWEEN 0 AND 360",
            name="ck_ais_positions_course_range",
        ),
        CheckConstraint(
            "heading_degrees IS NULL OR heading_degrees BETWEEN 0 AND 360",
            name="ck_ais_positions_heading_range",
        ),
        UniqueConstraint("mmsi", "recorded_at", name="uq_ais_positions_mmsi_recorded_at"),
        Index("ix_ais_positions_vessel_recorded_at", "vessel_id", "recorded_at"),
        Index("ix_ais_positions_mmsi_recorded_at", "mmsi", "recorded_at"),
    )


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_reference: Mapped[str | None] = mapped_column(String(120), unique=True)
    vessel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id"), nullable=False)
    barge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id"))
    bdn_number: Mapped[str | None] = mapped_column(String(120))
    delivery_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    port: Mapped[str | None] = mapped_column(String(160))
    quantity_mt: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    density: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    sulphur_content: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    flashpoint: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    supplier: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    credibility_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB)
    validation_result: Mapped[dict | None] = mapped_column(JSONB)
    verdict_reason: Mapped[str | None] = mapped_column(Text)

    vessel: Mapped[Vessel] = relationship(back_populates="received_transactions", foreign_keys=[vessel_id])
    barge: Mapped[Vessel | None] = relationship(back_populates="barge_transactions", foreign_keys=[barge_id])

    __table_args__ = (
        CheckConstraint(
            "delivery_end_at IS NULL OR delivery_start_at IS NULL OR delivery_end_at >= delivery_start_at",
            name="ck_transactions_delivery_time_order",
        ),
        CheckConstraint("quantity_mt IS NULL OR quantity_mt >= 0", name="ck_transactions_quantity_non_negative"),
        CheckConstraint("density IS NULL OR density > 0", name="ck_transactions_density_positive"),
        CheckConstraint(
            "sulphur_content IS NULL OR sulphur_content >= 0",
            name="ck_transactions_sulphur_non_negative",
        ),
        CheckConstraint("flashpoint IS NULL OR flashpoint >= 0", name="ck_transactions_flashpoint_non_negative"),
        CheckConstraint(
            "classification IS NULL OR classification IN "
            "('VALID', 'SUSPICIOUS', 'HIGH_RISK', 'REVIEW_REQUIRED', 'REJECTED', 'MANUALLY_APPROVED')",
            name="ck_transactions_classification",
        ),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_transactions_confidence_range"),
        CheckConstraint(
            "credibility_score IS NULL OR credibility_score BETWEEN 0 AND 100",
            name="ck_transactions_credibility_score_range",
        ),
        Index("ix_transactions_vessel_delivery_start_at", "vessel_id", "delivery_start_at"),
        Index("ix_transactions_barge_delivery_start_at", "barge_id", "delivery_start_at"),
    )
