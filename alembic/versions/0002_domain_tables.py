"""Tabelle del dominio M2: products, intents, proposals, orders, rejections.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("short_description", sa.Text, nullable=False),
        sa.Column("sport", sa.String(16), nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("destination", sa.Text),
        sa.Column("country", sa.String(2)),
        sa.Column("venue", sa.Text),
        sa.Column("hotel", sa.Text),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("min_pax", sa.Integer),
        sa.Column("max_pax", sa.Integer),
        sa.Column("min_date", sa.Date),
        sa.Column("max_date", sa.Date),
        sa.Column("availabilities", sa.JSON, nullable=False),
        sa.Column("duration_days", sa.Integer),
        sa.Column("hofj_updated_at", sa.String(40)),
        sa.Column("raw", sa.JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bookable", sa.Boolean, nullable=False),
        sa.Column("bookable_checked_at", sa.DateTime(timezone=True)),
        sa.Column("archived", sa.Boolean, nullable=False),
        sa.Column("provider_id", sa.String(32)),
    )
    op.create_table(
        "intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("criteria", sa.JSON, nullable=False),
        sa.Column("profile", sa.JSON, nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("pax", sa.Integer, nullable=False),
        sa.Column("price_from", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_proposals_intent_id", "proposals", ["intent_id"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("pax", sa.Integer, nullable=False),
        sa.Column("price_from", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("traveler", sa.JSON, nullable=False),
        sa.Column("itinerary_id", sa.Text),
        sa.Column("payment_url", sa.Text),
        sa.Column("payment_ref", sa.Text),
        sa.Column("booking_code", sa.Text),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("proposal_id", name="uq_orders_proposal_id"),
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table(
        "rejections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("intents.id"), nullable=False),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("proposal_id", name="uq_rejections_proposal_id"),
    )
    op.create_index("ix_rejections_intent_id", "rejections", ["intent_id"])


def downgrade() -> None:
    op.drop_table("rejections")
    op.drop_table("orders")
    op.drop_table("proposals")
    op.drop_table("intents")
    op.drop_table("products")
