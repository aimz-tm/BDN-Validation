"""create core tables

Revision ID: 202605230001
Revises:
Create Date: 2026-05-23 00:01:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "202605230001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "vessels",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("imo", sa.String(length=7), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mmsi", sa.String(length=9), nullable=True),
        sa.Column("vessel_type", sa.String(length=80), nullable=True),
        sa.Column("flag", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("imo ~ '^[0-9]{7}$'", name="ck_vessels_imo_format"),
        sa.CheckConstraint("mmsi IS NULL OR mmsi ~ '^[0-9]{9}$'", name="ck_vessels_mmsi_format"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("imo"),
        sa.UniqueConstraint("mmsi"),
    )

    op.create_table(
        "ais_positions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mmsi", sa.String(length=9), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("speed_knots", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("course_degrees", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("heading_degrees", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("navigational_status", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("course_degrees IS NULL OR course_degrees BETWEEN 0 AND 360", name="ck_ais_positions_course_range"),
        sa.CheckConstraint("heading_degrees IS NULL OR heading_degrees BETWEEN 0 AND 360", name="ck_ais_positions_heading_range"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_ais_positions_latitude_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_ais_positions_longitude_range"),
        sa.CheckConstraint("mmsi ~ '^[0-9]{9}$'", name="ck_ais_positions_mmsi_format"),
        sa.CheckConstraint("speed_knots IS NULL OR speed_knots >= 0", name="ck_ais_positions_speed_non_negative"),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mmsi", "recorded_at", name="uq_ais_positions_mmsi_recorded_at"),
    )
    op.create_index("ix_ais_positions_mmsi_recorded_at", "ais_positions", ["mmsi", "recorded_at"], unique=False)
    op.create_index("ix_ais_positions_vessel_recorded_at", "ais_positions", ["vessel_id", "recorded_at"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("transaction_reference", sa.String(length=120), nullable=True),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("barge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bdn_number", sa.String(length=120), nullable=True),
        sa.Column("delivery_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("port", sa.String(length=160), nullable=True),
        sa.Column("quantity_mt", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("density", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("sulphur_content", sa.Numeric(precision=5, scale=3), nullable=True),
        sa.Column("flashpoint", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("classification", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("credibility_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verdict_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("classification IS NULL OR classification IN ('VALID', 'SUSPICIOUS', 'HIGH_RISK')", name="ck_transactions_classification"),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_transactions_confidence_range"),
        sa.CheckConstraint("credibility_score IS NULL OR credibility_score BETWEEN 0 AND 100", name="ck_transactions_credibility_score_range"),
        sa.CheckConstraint("delivery_end_at IS NULL OR delivery_start_at IS NULL OR delivery_end_at >= delivery_start_at", name="ck_transactions_delivery_time_order"),
        sa.CheckConstraint("density IS NULL OR density > 0", name="ck_transactions_density_positive"),
        sa.CheckConstraint("flashpoint IS NULL OR flashpoint >= 0", name="ck_transactions_flashpoint_non_negative"),
        sa.CheckConstraint("quantity_mt IS NULL OR quantity_mt >= 0", name="ck_transactions_quantity_non_negative"),
        sa.CheckConstraint("sulphur_content IS NULL OR sulphur_content >= 0", name="ck_transactions_sulphur_non_negative"),
        sa.ForeignKeyConstraint(["barge_id"], ["vessels.id"]),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_reference"),
    )
    op.create_index("ix_transactions_barge_delivery_start_at", "transactions", ["barge_id", "delivery_start_at"], unique=False)
    op.create_index("ix_transactions_vessel_delivery_start_at", "transactions", ["vessel_id", "delivery_start_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_transactions_vessel_delivery_start_at", table_name="transactions")
    op.drop_index("ix_transactions_barge_delivery_start_at", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_ais_positions_vessel_recorded_at", table_name="ais_positions")
    op.drop_index("ix_ais_positions_mmsi_recorded_at", table_name="ais_positions")
    op.drop_table("ais_positions")
    op.drop_table("vessels")
