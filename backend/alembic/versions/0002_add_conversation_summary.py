from alembic import op
import sqlalchemy as sa


revision = "0002_add_conversation_summary"
down_revision = "0001_platform_v2"


def upgrade():
    op.add_column("conversations", sa.Column("summary", sa.Text(), server_default="", nullable=False))


def downgrade():
    op.drop_column("conversations", "summary")
