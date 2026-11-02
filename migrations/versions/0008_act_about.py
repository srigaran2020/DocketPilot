"""What each Act is about (India Code long title + summary), used to rank Acts for "which laws deal with X".

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("acts", sa.Column("about", sa.Text()))


def downgrade() -> None:
    op.drop_column("acts", "about")
