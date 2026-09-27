"""Tabelle del dominio (RF-05, RF-25, RF-28) sul `metadata` condiviso di `db.py`.

Tipi neutri (JSON, Numeric, String, Date, DateTime): `tests/test_migrations.py` applica le
migrazioni anche su SQLite. Postgres è l'unico backend di produzione (RNF-01).
"""
from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
                        Numeric, String, Table, Text, UniqueConstraint, text)

from vela.adapters.db import metadata

ACTIVE_BOOKING_SQL = "kind = 'booking' AND status IN ('pending', 'running')"

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
    Column("brand", String(64)),
    Column("featured", Boolean, nullable=False, default=False),        # 0010 (M21-B)
    Column("special_offer", Boolean, nullable=False, default=False),   # 0010 (M21-B)
    Column("max_pax_per_room", Integer),                                # 0011 (M21-D)
    Column("levels", JSON, nullable=False, default=list),               # 0012 (M21-C)
    Column("levels_exclusive", Boolean, nullable=False, default=False),  # 0012 (M21-C)
    Column("coaching", Boolean, nullable=False, default=False),         # 0012 (M21-C)
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
    Column("total", Numeric(12, 2)),
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
    Column("enqueued_at", DateTime(timezone=True)),
    Column("replacement_proposal_id", String(36), index=True),
    Column("orphan_itineraries", Integer, nullable=False, server_default="0"),   # M18
    Column("rooms", Integer, nullable=False, server_default="1"),                # 0011 (M21-D)
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

# M5: coda dei job (RF-50) e finestra di quota condivisa (RF-36, RF-47).
jobs_t = Table(
    "jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("order_id", String(36), ForeignKey("orders.id"), nullable=False, index=True),
    Column("status", String(16), nullable=False),
    Column("step", Integer, nullable=False, default=0),
    Column("attempts", Integer, nullable=False, default=0),
    Column("enqueued_at", DateTime(timezone=True), nullable=False),
    Column("run_after", DateTime(timezone=True), nullable=False),
    Column("locked_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Index("ix_jobs_claim", "status", "kind", "run_after", "enqueued_at"),
    # Un solo job `booking` attivo per ordine (RF-51, migrazione 0009).
    Index("uq_jobs_active_booking", "order_id", unique=True,
          postgresql_where=text(ACTIVE_BOOKING_SQL), sqlite_where=text(ACTIVE_BOOKING_SQL)),
)

quota_window_t = Table(
    "quota_window", metadata,
    Column("id", Integer, primary_key=True),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("window_end", DateTime(timezone=True), nullable=False),
    Column("limit_per_minute", Integer, nullable=False),
    Column("needs_refresh", Boolean, nullable=False, default=False),
    Column("tokens", Float, nullable=False),                  # token bucket (M18), può essere negativo
    Column("refilled_at", DateTime(timezone=True), nullable=False),
)
