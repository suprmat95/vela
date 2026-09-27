"""Un solo job `booking` attivo per ordine, garantito dal database (task/booking-race).

M13b ha misurato due job `booking` per lo stesso ordine quando checkout e verifica del
pagamento chiamano insieme `mark_paid`: il controllo "c'è già un job attivo?" e l'inserimento
non sono atomici. Indice unico parziale su `jobs(order_id)` per i job `booking` `pending` o
`running`. Prima di crearlo, gli eventuali doppioni attivi già in tabella diventano `dead`:
resta il più vecchio (`enqueued_at`, poi `id`), che prenota lo stesso itinerario.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE_BOOKING = "kind = 'booking' AND status IN ('pending', 'running')"


def upgrade() -> None:
    op.execute(
        "UPDATE jobs SET status = 'dead', "
        "last_error = 'doppione di un altro job booking attivo (migrazione 0009)' "
        "WHERE " + ACTIVE_BOOKING + " AND EXISTS ("
        "SELECT 1 FROM jobs AS older WHERE older.order_id = jobs.order_id "
        "AND older.kind = 'booking' AND older.status IN ('pending', 'running') "
        "AND (older.enqueued_at < jobs.enqueued_at "
        "OR (older.enqueued_at = jobs.enqueued_at AND older.id < jobs.id)))")
    op.create_index("uq_jobs_active_booking", "jobs", ["order_id"], unique=True,
                    postgresql_where=sa.text(ACTIVE_BOOKING), sqlite_where=sa.text(ACTIVE_BOOKING))


def downgrade() -> None:
    op.drop_index("uq_jobs_active_booking", table_name="jobs")
