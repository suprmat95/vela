"""Coda dei job e finestra di quota (M5): jobs, quota_window, colonne della coda su orders.

`orders.total` diventa nullable: un ordine `queued` non conosce ancora l'importo reale
(RF-45, RF-46). `enqueued_at` dà la posizione FIFO (RF-48), `replacement_proposal_id` lega
l'ordine sostituito alla nuova proposta (RF-17). Tipi neutri e `batch_alter_table` perché la
migrazione giri anche su SQLite (test).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.alter_column("total", existing_type=sa.Numeric(12, 2), nullable=True)
        batch.add_column(sa.Column("enqueued_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("replacement_proposal_id", sa.String(36)))
        batch.create_index("ix_orders_replacement_proposal_id", ["replacement_proposal_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("step", sa.Integer, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
    )
    op.create_index("ix_jobs_order_id", "jobs", ["order_id"])
    op.create_index("ix_jobs_claim", "jobs", ["status", "kind", "run_after", "enqueued_at"])

    op.create_table(
        "quota_window",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_per_minute", sa.Integer, nullable=False),
        sa.Column("used", sa.Integer, nullable=False),
        sa.Column("needs_refresh", sa.Boolean, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("quota_window")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_index("ix_jobs_order_id", table_name="jobs")
    op.drop_table("jobs")
    # Un ordine in coda senza totale non è rappresentabile nello schema precedente.
    op.execute("DELETE FROM orders WHERE total IS NULL")
    with op.batch_alter_table("orders") as batch:
        batch.drop_index("ix_orders_replacement_proposal_id")
        batch.drop_column("replacement_proposal_id")
        batch.drop_column("enqueued_at")
        batch.alter_column("total", existing_type=sa.Numeric(12, 2), nullable=False)
