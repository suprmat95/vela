"""Tabelle del dominio (RF-05, RF-25, RF-28) sul `metadata` condiviso di `db.py`.

Tipi neutri (JSON, Numeric, String, Date, DateTime): `tests/test_migrations.py` applica le
migrazioni anche su SQLite. Postgres è l'unico backend di produzione (RNF-01).
"""
from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Table, Text, UniqueConstraint)

from vela.adapters.db import metadata

products_t = Table(
    "products", metadata,
    Column("id", String(32), primary_key=True),
    Column("title", Text, nullable=False),
    Column("slug", Text, nullable=False),
    Column("short_description", Text, nullable=False, default=""),
    Column("sport", String(16), nullable=False),
    Column("category", Text),
    Column("destination", Text),
    Column("country", String(2)),
    Column("venue", Text),
    Column("hotel", Text),
    Column("price", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("min_pax", Integer),
    Column("max_pax", Integer),
    Column("min_date", Date),
    Column("max_date", Date),
    Column("availabilities", JSON, nullable=False),
    Column("duration_days", Integer),
    Column("hofj_updated_at", String(40)),
    Column("raw", JSON, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("bookable", Boolean, nullable=False, default=True),
    Column("bookable_checked_at", DateTime(timezone=True)),
    Column("archived", Boolean, nullable=False, default=False),
    Column("provider_id", String(32)),
)

intents_t = Table(
    "intents", metadata,
    Column("id", String(36), primary_key=True),
    Column("text", Text, nullable=False),
    Column("criteria", JSON, nullable=False),
    Column("profile", JSON, nullable=False),
    Column("language", String(2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

proposals_t = Table(
    "proposals", metadata,
    Column("id", String(36), primary_key=True),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False, index=True),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("pax", Integer, nullable=False),
    Column("price_from", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

orders_t = Table(
    "orders", metadata,
    Column("id", String(36), primary_key=True),
    Column("proposal_id", String(36), ForeignKey("proposals.id"), nullable=False),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("status", String(24), nullable=False, index=True),
    Column("pax", Integer, nullable=False),
    Column("price_from", Numeric(12, 2), nullable=False),
    Column("total", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("traveler", JSON, nullable=False),
    Column("itinerary_id", Text),
    Column("payment_url", Text),
    Column("payment_ref", Text),
    Column("booking_code", Text),
    Column("failure_reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("paid_at", DateTime(timezone=True)),
    UniqueConstraint("proposal_id", name="uq_orders_proposal_id"),   # RNF-03: un ordine per proposta
)

rejections_t = Table(
    "rejections", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("intent_id", String(36), ForeignKey("intents.id"), nullable=False, index=True),
    Column("proposal_id", String(36), ForeignKey("proposals.id"), nullable=False),
    Column("product_id", String(32), ForeignKey("products.id"), nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("proposal_id", name="uq_rejections_proposal_id"),
)
