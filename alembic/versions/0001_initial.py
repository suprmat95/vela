"""Migrazione iniziale vuota: crea solo alembic_version, prova che le migrazioni girano al boot.

Revision ID: 0001
Revises:
Create Date: 2026-09-25

"""
from typing import Sequence, Union

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
